#!/usr/bin/env python3
"""Exact rational verifier for the Max-2SAT 450-bucket companion certificate."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction as Q
from itertools import product
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WITNESS = ROOT / "artifacts/max2sat/multirounding_L450_exact_witness.json"
DEFAULT_CURVES = ROOT / "artifacts/max2sat/multirounding_L450_9_rounding_curves.json"
DEFAULT_RHO = Q(18563, 25000)


def rat(value: Any) -> Q:
    if isinstance(value, Q):
        return value
    if isinstance(value, int):
        return Q(value, 1)
    if isinstance(value, str):
        return Q(value)
    return Q(str(value))


def read_json_exact(path: Path) -> Any:
    return json.loads(path.read_text(), parse_float=str, parse_int=str)


def lit_sat(sign: int, bit: int) -> bool:
    return (sign == 0 and bit == 1) or (sign == 1 and bit == 0)


def extract_curves(data: dict[str, Any]) -> list[list[Q]]:
    if "curves" in data:
        return [[rat(x) for x in curve["p"]] for curve in data["curves"]]
    if "p" in data:
        return [[rat(x) for x in data["p"]]]
    raise ValueError("rounding data must contain either curves[].p or p")


def extract_alphas(primary: dict[str, Any], fallback: dict[str, Any], profile_count: int) -> list[Q]:
    if "alphas" in primary:
        alphas = [rat(x) for x in primary["alphas"]]
    elif "alphas" in fallback:
        alphas = [rat(x) for x in fallback["alphas"]]
    elif "curves" in fallback and all("alpha" in curve for curve in fallback["curves"]):
        alphas = [rat(curve["alpha"]) for curve in fallback["curves"]]
    else:
        raise ValueError("certificate must provide convex weights alphas")

    if len(alphas) != profile_count:
        raise ValueError(f"expected {profile_count} alphas, got {len(alphas)}")
    if any(alpha < 0 for alpha in alphas):
        raise ValueError("alphas must be nonnegative")
    total = sum(alphas, Q(0))
    if total <= 0:
        raise ValueError("alpha sum must be positive")
    return [alpha / total for alpha in alphas]


def validate_intervals(intervals: list[list[Q]], L: int) -> None:
    if len(intervals) != L:
        raise ValueError(f"expected {L} intervals, got {len(intervals)}")
    if intervals[0][0] != -1 or intervals[-1][1] != 1:
        raise ValueError("intervals must cover [-1,1] exactly")
    for i, (lo, hi) in enumerate(intervals):
        if lo >= hi:
            raise ValueError(f"interval {i} is empty or reversed")
        if i + 1 < L and hi != intervals[i + 1][0]:
            raise ValueError(f"intervals {i} and {i + 1} are not exactly contiguous")


def lambda_index(bucket: int, bit: int, kind: int) -> int:
    return (bucket * 2 + bit) * 2 + kind


def endpoint_dual(
    lambdas: list[Q],
    intervals: list[list[Q]],
    endpoint_weight: Q,
    sign: int,
    bucket: int,
    bit: int,
) -> Q:
    lo, hi = intervals[bucket]
    signed_weight = endpoint_weight if sign == 0 else -endpoint_weight
    g_lower = lo * endpoint_weight - signed_weight
    g_upper = signed_weight - hi * endpoint_weight
    return (
        lambdas[lambda_index(bucket, bit, 0)] * g_lower
        + lambdas[lambda_index(bucket, bit, 1)] * g_upper
    )


def check_certificate(
    curves_data: dict[str, Any],
    dual_data: dict[str, Any],
    target_rho: Q,
) -> dict[str, Any]:
    curves = extract_curves(curves_data)
    L = int(dual_data.get("L", curves_data.get("L", len(curves[0]))))
    unary_weight = rat(dual_data.get("unary_weight", curves_data.get("unary_weight", "67/20")))
    intervals = [[rat(a), rat(b)] for a, b in dual_data.get("intervals", curves_data["intervals"])]
    if "intervals" in dual_data and "intervals" in curves_data:
        curve_intervals = [[rat(a), rat(b)] for a, b in curves_data["intervals"]]
        if curve_intervals != intervals:
            raise ValueError("dual witness intervals do not match rounding-curve intervals")
    if "unary_weight" in dual_data and "unary_weight" in curves_data:
        if rat(dual_data["unary_weight"]) != rat(curves_data["unary_weight"]):
            raise ValueError("dual witness unary weight does not match rounding-curve unary weight")
    lambdas = [rat(x) for x in dual_data.get("lambdas", [])]
    alphas = extract_alphas(dual_data, curves_data, len(curves))

    if any(len(curve) != L for curve in curves):
        raise ValueError("each rounding profile must have length L")
    if len(lambdas) != 4 * L:
        raise ValueError(f"expected {4 * L} dual multipliers, got {len(lambdas)}")
    if any(lam < 0 for lam in lambdas):
        raise ValueError("dual multipliers must be nonnegative")
    validate_intervals(intervals, L)
    for t, curve in enumerate(curves):
        for bucket, p in enumerate(curve):
            if p < 0 or p > 1:
                raise ValueError(f"profile {t}, bucket {bucket} has probability outside [0,1]")

    witness_rho = rat(dual_data.get("rho", curves_data.get("rho", "0")))
    if witness_rho and witness_rho < target_rho:
        raise ValueError(f"witness rho {witness_rho} is smaller than target rho {target_rho}")

    unary_endpoint_weight = unary_weight / 2
    binary_endpoint_weight = Q(1, 2)

    q = [
        [[curve[bucket] if sign == 0 else 1 - curve[bucket] for bucket in range(L)] for sign in (0, 1)]
        for curve in curves
    ]
    unary_round = [
        [sum(alpha * q[t][sign][bucket] for t, alpha in enumerate(alphas)) for bucket in range(L)]
        for sign in (0, 1)
    ]
    unary_dual = [
        [
            [endpoint_dual(lambdas, intervals, unary_endpoint_weight, sign, bucket, bit) for bit in (0, 1)]
            for bucket in range(L)
        ]
        for sign in (0, 1)
    ]
    binary_dual = [
        [
            [endpoint_dual(lambdas, intervals, binary_endpoint_weight, sign, bucket, bit) for bit in (0, 1)]
            for bucket in range(L)
        ]
        for sign in (0, 1)
    ]

    checked_unary = 0
    checked_binary = 0
    min_slack: Q | None = None
    min_atom: tuple[Any, ...] | None = None

    def record(slack: Q, atom: tuple[Any, ...]) -> None:
        nonlocal min_slack, min_atom
        if min_slack is None or slack < min_slack:
            min_slack = slack
            min_atom = atom
        if slack < 0:
            raise AssertionError(f"negative slack at {atom}: {slack}")

    for sign, bucket, bit in product((0, 1), range(L), (0, 1)):
        opt = Q(1) if lit_sat(sign, bit) else Q(0)
        slack = unary_round[sign][bucket] - target_rho * opt + unary_dual[sign][bucket][bit]
        record(slack, ("unary", sign, bucket, bit))
        checked_unary += 1

    for a, b in product((0, 1), (0, 1)):
        for i, j in product(range(L), range(L)):
            rounded = sum(
                alpha * (1 - (1 - q[t][a][i]) * (1 - q[t][b][j]))
                for t, alpha in enumerate(alphas)
            )
            for tau, ups in product((0, 1), (0, 1)):
                opt = Q(1) if (lit_sat(a, tau) or lit_sat(b, ups)) else Q(0)
                slack = (
                    rounded
                    - target_rho * opt
                    + binary_dual[a][i][tau]
                    + binary_dual[b][j][ups]
                )
                record(slack, ("binary", a, b, i, j, tau, ups))
                checked_binary += 1

    return {
        "L": L,
        "profiles": len(curves),
        "unary_weight": unary_weight,
        "target_rho": target_rho,
        "witness_rho": witness_rho,
        "checked_unary": checked_unary,
        "checked_binary": checked_binary,
        "min_slack": min_slack,
        "min_atom": min_atom,
        "nonzero_lambdas": sum(lam != 0 for lam in lambdas),
        "nonzero_alphas": sum(alpha != 0 for alpha in alphas),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--witness-json", type=Path, default=DEFAULT_WITNESS)
    parser.add_argument("--curves-json", type=Path, default=DEFAULT_CURVES)
    parser.add_argument("--rho", default=str(DEFAULT_RHO), help="target ratio to verify, default 18563/25000")
    args = parser.parse_args()

    curves_path = args.curves_json
    dual_path = args.witness_json
    if not curves_path.exists():
        raise SystemExit(f"missing rounding curves JSON: {curves_path}")
    if not dual_path.exists():
        raise SystemExit(
            f"missing exact witness JSON with lambdas: {dual_path}\n"
            "Run scripts/max2sat_multi_rounding_certificate_search.py with --curves-json "
            "to generate it."
        )

    curves_data = read_json_exact(curves_path)
    dual_data = read_json_exact(dual_path)
    result = check_certificate(curves_data, dual_data, rat(args.rho))

    print(f"target rho: {result['target_rho']} = {float(result['target_rho']):.12f}")
    print(f"witness rho: {result['witness_rho']} = {float(result['witness_rho']):.12f}")
    print(
        f"profiles: {result['profiles']}; buckets: {result['L']}; "
        f"unary weight: {result['unary_weight']}"
    )
    print(
        f"unary inequalities verified: {result['checked_unary']}; "
        f"binary inequalities verified: {result['checked_binary']}"
    )
    print(f"minimum certificate slack: {result['min_slack']} at {result['min_atom']}")
    print(
        f"nonzero convex weights: {result['nonzero_alphas']}; "
        f"nonzero dual multipliers: {result['nonzero_lambdas']}"
    )


if __name__ == "__main__":
    main()
