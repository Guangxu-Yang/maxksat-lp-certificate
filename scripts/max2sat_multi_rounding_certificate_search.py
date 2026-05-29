#!/usr/bin/env python3
"""Certificate LP for the maximum of several Max-2SAT rounding functions.

For fixed bucket partition, unary weight, and rounding curves p^(t), the
guarantee of

    max_t R_{p^(t)}(Snap)

can still be certified by a linear program.  The dual searches for a convex
combination sum_t alpha_t R_{p^(t)} plus the usual bucket-bias multipliers.
Strong duality says this is exactly the finite certificate value for the max
of the listed linear snapshot functionals.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csc_matrix, hstack

from max2sat_weighted_certificate_search import SparseCertificateModel, load_intervals, load_p


def solve_multi(L: int, unary_weight: float, p_list: list[np.ndarray], intervals: np.ndarray | None = None):
    base = SparseCertificateModel(L, unary_weight, intervals)
    rhs_cols = [base.rhs(p) for p in p_list]
    rmat = csc_matrix(np.column_stack(rhs_cols))
    A = hstack([base.A, -rmat], format="csr")
    b = np.zeros(base.A.shape[0], dtype=float)

    n_base = base.n_vars
    t = len(p_list)
    c = np.zeros(n_base + t, dtype=float)
    c[0] = -1.0
    bounds = [(0.0, 1.0)] + [(0.0, None)] * base.n_lambdas + [(0.0, 1.0)] * t
    A_eq = np.zeros((1, n_base + t), dtype=float)
    A_eq[0, n_base:] = 1.0
    b_eq = np.array([1.0], dtype=float)

    res = linprog(
        c,
        A_ub=A,
        b_ub=b,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if not res.success:
        return {
            "success": False,
            "message": res.message,
            "L": L,
            "unary_weight": unary_weight,
            "rho": 0.0,
            "alphas": [],
            "min_slack": None,
            "min_row": None,
        }

    slacks = b - A.dot(res.x)
    min_row = int(np.argmin(slacks))
    return {
        "success": True,
        "message": res.message,
        "L": L,
        "unary_weight": unary_weight,
        "intervals": [[float(a), float(b)] for a, b in base.intervals],
        "rho": float(res.x[0]),
        "alphas": [float(x) for x in res.x[n_base:]],
        "min_slack": float(slacks[min_row]),
        "min_row": min_row,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--L", type=int, required=True)
    parser.add_argument("--unary-weight", type=float, required=True)
    parser.add_argument("--intervals-json", default=None)
    parser.add_argument("--power", type=float, default=None)
    parser.add_argument("--focus", type=float, default=None)
    parser.add_argument("--focus-strength", type=float, default=2.0)
    parser.add_argument("--focus-sigma", type=float, default=0.05)
    parser.add_argument(
        "--focus-component",
        action="append",
        default=None,
        help="additional density component focus:strength:sigma; may be repeated",
    )
    parser.add_argument(
        "--p-json",
        nargs="+",
        required=True,
        help="JSON files containing p arrays or previous result objects.",
    )
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args()

    if args.focus_component:
        from max2sat_weighted_certificate_search import parse_focus_component

        args.focus_component = [parse_focus_component(value) for value in args.focus_component]
    intervals = load_intervals(args)
    p_list = [load_p(path, args.L, intervals) for path in args.p_json]
    result = solve_multi(args.L, args.unary_weight, p_list, intervals)
    result["sources"] = args.p_json

    print("success:", result["success"], result["message"])
    print(f"L = {result['L']}")
    print(f"unary_weight = {result['unary_weight']:.15g}")
    print(f"rho = {result['rho']:.15f}")
    print("alphas =", "[" + ", ".join(f"{a:.8f}" for a in result["alphas"]) + "]")
    print(f"min_slack = {result['min_slack']} at row {result['min_row']}")

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
