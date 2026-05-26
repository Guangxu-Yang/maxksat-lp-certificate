#!/usr/bin/env python3
"""Floating-point LP search for the Max-kSAT short-clause certificate.

This script rebuilds the finite LP used to search for a pairwise-decomposable
ternary score H and nonnegative dual multipliers. It is a reproducibility aid:
the proof should rely on scripts/verify_certificate.py, which checks the final
rational certificate exactly over Q.

Requires scipy:

    python3 -m pip install scipy
    python3 scripts/search_lp_certificate.py
"""

from __future__ import annotations

from itertools import product

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix


rho_target = 28691 / 40000
r = np.array(
    [
        27083 / 100000,
        27083 / 100000,
        27083 / 100000,
        4069 / 10000,
        5931 / 10000,
        72917 / 100000,
        72917 / 100000,
        72917 / 100000,
    ],
    dtype=float,
)
L = np.array([-1, -3 / 4, -1 / 2, -1 / 4, 0, 1 / 4, 1 / 2, 3 / 4], dtype=float)
U = np.array([-3 / 4, -1 / 2, -1 / 4, 0, 1 / 4, 1 / 2, 3 / 4, 1], dtype=float)
weights = {1: 4.0, 2: 2.0, 3: 1.0}

pair_list = [(0, 1), (0, 2), (1, 2)]
pair_to_idx = {p: i for i, p in enumerate(pair_list)}


def q(sign: int, bucket: int) -> float:
    return float(r[bucket] if sign == 1 else 1 - r[bucket])


def q_label(lab: int) -> float:
    return q(lab // 8, lab % 8)


def label(sign: int, bucket: int) -> int:
    return sign * 8 + bucket


def lit_satisfied(sign: int, bit: int) -> bool:
    return bool(bit) if sign == 1 else not bool(bit)


def g(endpoint_sign: int, bucket: int, kind: str) -> float:
    if kind == "lo":
        return -(1 - L[bucket]) if endpoint_sign == 1 else (1 + L[bucket])
    if kind == "up":
        return (1 - U[bucket]) if endpoint_sign == 1 else -(1 + U[bucket])
    raise ValueError(kind)


def comp_idx_const() -> int:
    return 0


def comp_idx_u(pos: int, lab: int) -> int:
    return 1 + pos * 16 + lab


def comp_idx_p(pair: tuple[int, int], a: int, b: int) -> int:
    return 1 + 48 + pair_to_idx[pair] * 256 + a * 16 + b


def lam_idx(bucket: int, bit: int, kind: str) -> int:
    k = 0 if kind == "lo" else 1
    return ((bucket * 2 + bit) * 2 + k)


N_COMPONENTS = 1 + 48 + 3 * 256
N_LAMBDAS = 8 * 2 * 2
IDX_RHO = 0
IDX_COMP = 1
IDX_LAM = IDX_COMP + N_COMPONENTS
N_VARS = IDX_LAM + N_LAMBDAS


def add_H_coeffs(rows, cols, data, row: int, labels: tuple[int, int, int], scale: float):
    rows.append(row)
    cols.append(IDX_COMP + comp_idx_const())
    data.append(scale)
    for pos, lab in enumerate(labels):
        rows.append(row)
        cols.append(IDX_COMP + comp_idx_u(pos, lab))
        data.append(scale)
    for pair in pair_list:
        a, b = pair
        rows.append(row)
        cols.append(IDX_COMP + comp_idx_p(pair, labels[a], labels[b]))
        data.append(scale)


def build_lp():
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    rhs: list[float] = []
    row = 0

    # Upper constraints: H(labels) <= true independent-rounding value.
    for labels in product(range(16), repeat=3):
        add_H_coeffs(rows, cols, data, row, labels, +1.0)
        fail = 1.0
        for lab in labels:
            fail *= 1.0 - q_label(lab)
        rhs.append(1.0 - fail)
        row += 1

    # Atom constraints:
    # h(c) - rho*o(c) + sum lambda*g(c) >= 0.
    # In A x <= b form:
    # rho*o(c) - H(c) - sum lambda*g(c) <= 0      for length 3,
    # rho*o(c)        - sum lambda*g(c) <= h(c)   for length 1,2.
    for length in (1, 2, 3):
        for signs in product((0, 1), repeat=length):
            for buckets in product(range(8), repeat=length):
                if length == 1:
                    exact_score = q(signs[0], buckets[0])
                elif length == 2:
                    exact_score = 1.0
                    for sign, bucket in zip(signs, buckets):
                        exact_score *= 1.0 - q(sign, bucket)
                    exact_score = 1.0 - exact_score
                else:
                    exact_score = 0.0
                    labels = tuple(label(s, b) for s, b in zip(signs, buckets))

                for bits in product((0, 1), repeat=length):
                    if length == 3:
                        add_H_coeffs(rows, cols, data, row, labels, -1.0)
                    opt = 1.0 if any(lit_satisfied(s, b) for s, b in zip(signs, bits)) else 0.0
                    rows.append(row)
                    cols.append(IDX_RHO)
                    data.append(opt)
                    for sign, bucket, bit in zip(signs, buckets, bits):
                        for kind in ("lo", "up"):
                            rows.append(row)
                            cols.append(IDX_LAM + lam_idx(bucket, bit, kind))
                            data.append(-weights[length] * g(sign, bucket, kind))
                    rhs.append(exact_score)
                    row += 1

    A = coo_matrix((data, (rows, cols)), shape=(row, N_VARS)).tocsr()
    return A, np.asarray(rhs, dtype=float)


def main() -> None:
    A, b = build_lp()
    objective = np.zeros(N_VARS)
    objective[IDX_RHO] = -1.0
    bounds = [(0.0, 1.0)] + [(None, None)] * N_COMPONENTS + [(0.0, None)] * N_LAMBDAS
    res = linprog(objective, A_ub=A, b_ub=b, bounds=bounds, method="highs")
    if not res.success:
        raise SystemExit(res.message)
    slack = b - A.dot(res.x)
    print(f"floating LP optimum rho: {res.x[IDX_RHO]:.12f}")
    print(f"target rho:              {rho_target:.12f}")
    print(f"minimum slack:           {slack.min():.3e}")
    print(f"nonzero H components:    {np.count_nonzero(np.abs(res.x[IDX_COMP:IDX_LAM]) > 1e-9)}")
    print(f"nonzero dual multipliers:{np.count_nonzero(np.abs(res.x[IDX_LAM:]) > 1e-9)}")


if __name__ == "__main__":
    main()
