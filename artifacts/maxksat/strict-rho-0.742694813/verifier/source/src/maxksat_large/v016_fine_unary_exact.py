"""Independent exact verifier for the J=1 fine-unary/group-pair surrogate.

For d in {3,4,5}, the admitted surrogate is

    H_d(a_1,...,a_d) = sum_i u_d(a_i)
                       + sum_{i<j} K_d(g(a_i), g(a_j)).

The verifier is stdlib-only and uses :class:`fractions.Fraction` throughout.
It never imports the numerical LP implementation.  Low-order clauses retain
their exact independent-rounding score.  High-order lower rows use the same
weight/lambda ledger as the original certificate.

Large-bucket upper separation is exact without enumerating (2B)^d fine
tuples.  For a fixed group prefix a state is ``(R,U)`` with ``R=prod(1-q)``
and ``U=sum(u)+sum(K)``.  Any continuation sees a state only through
``U+zR`` for some ``z in [0,1]``.  Therefore retaining the exact upper hull
of these lines loses no possible maximizer.  A depth-d DFS visits every group
multiset, while exact hull pruning handles all fine labels within each group.
The small-bucket brute-force verifier below independently cross-checks this
equivalence by enumerating every fine and typed row.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from functools import reduce
from hashlib import sha256
from itertools import combinations_with_replacement
import json
from math import comb, isfinite
from time import perf_counter
from typing import Any, Mapping, Sequence


SCHEMA = "v016-j1-fine-unary-group-pair-exact-v1"
CLAIM = "candidate_requires_complete_fraction_hull_replay"
ARITIES = (3, 4, 5)
EXPECTED_FAMILIES = frozenset(
    {
        "d1_unsatisfied",
        "d1_satisfied",
        "d2_unsatisfied",
        "d2_satisfied",
        "long_floor",
        *(f"d{arity}_upper" for arity in ARITIES),
        *(
            f"d{arity}_{kind}"
            for arity in ARITIES
            for kind in ("unsatisfied", "satisfied")
        ),
    }
)
PAYLOAD_KEYS = frozenset(
    {
        "schema",
        "claim",
        "num_buckets",
        "rounding",
        "bucket_intervals",
        "weights",
        "rho",
        "lambdas",
        "bucket_group_map",
        "unary_tables",
        "pair_tables",
    }
)


@dataclass(frozen=True, slots=True)
class FineUnaryExactResourceLimits:
    """Hard limits return ``incomplete`` and can never produce a pass."""

    max_num_buckets: int = 2_048
    max_low_label_pairs: int = 2_100_000
    max_group_multisets: int = 2_000_000
    max_pair_table_entries: int = 20_000
    max_hull_states: int = 8_192
    max_upper_transitions: int = 120_000_000
    max_seconds: float | None = 600.0

    def __post_init__(self) -> None:
        for name in (
            "max_num_buckets",
            "max_low_label_pairs",
            "max_group_multisets",
            "max_pair_table_entries",
            "max_hull_states",
            "max_upper_transitions",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive exact integer")
        if self.max_seconds is not None and (
            isinstance(self.max_seconds, bool)
            or not isfinite(self.max_seconds)
            or self.max_seconds <= 0
        ):
            raise ValueError("max_seconds must be finite positive or None")


class _Incomplete(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _HullState:
    slope: F
    intercept: F
    labels: tuple[int, ...]


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _rational(value: Any, *, location: str) -> F:
    if isinstance(value, (bool, float)):
        raise ValueError(f"{location} must be a canonical rational string or integer")
    try:
        result = F(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError(f"invalid exact rational at {location}") from error
    if isinstance(value, str) and value != str(result):
        raise ValueError(f"noncanonical rational string at {location}")
    return result


def _time_check(started: float, limits: FineUnaryExactResourceLimits) -> None:
    if limits.max_seconds is not None and perf_counter() - started > limits.max_seconds:
        raise _Incomplete("exact verification time limit reached")


def _pair_index(left: int, right: int, count: int) -> int:
    if left > right:
        left, right = right, left
    return left * count - left * (left - 1) // 2 + right - left


def _pair_sum(table: Sequence[F], atom: Sequence[int], groups: int) -> F:
    return sum(
        (
            table[_pair_index(atom[left], atom[right], groups)]
            for left in range(len(atom))
            for right in range(left + 1, len(atom))
        ),
        F(0),
    )


def _upper_hull(states: Sequence[_HullState]) -> tuple[_HullState, ...]:
    """Return precisely the lines active somewhere on z in [0,1]."""

    by_slope: dict[F, _HullState] = {}
    for state in states:
        old = by_slope.get(state.slope)
        if old is None or state.intercept > old.intercept or (
            state.intercept == old.intercept and state.labels < old.labels
        ):
            by_slope[state.slope] = state
    ordered = [by_slope[slope] for slope in sorted(by_slope)]
    hull: list[_HullState] = []
    starts: list[F | None] = []  # None denotes -infinity for the first line.
    for state in ordered:
        start: F | None = None
        while hull:
            previous = hull[-1]
            crossing = (previous.intercept - state.intercept) / (
                state.slope - previous.slope
            )
            previous_start = starts[-1]
            if previous_start is not None and crossing <= previous_start:
                hull.pop()
                starts.pop()
                continue
            start = crossing
            break
        if not hull:
            start = None
        hull.append(state)
        starts.append(start)

    active: list[_HullState] = []
    for index, state in enumerate(hull):
        left = starts[index]
        right = starts[index + 1] if index + 1 < len(starts) else None
        # A line active only in a tie at z=0 or z=1 can be discarded: its
        # neighbour is equal at that endpoint and weakly better everywhere
        # else.  Keeping endpoint-only ties needlessly doubles flat-u hulls.
        if (right is None or right > 0) and (left is None or left < 1):
            active.append(state)
    if not active:
        raise RuntimeError("internal empty upper hull")
    return tuple(active)


def _parse_payload(payload: Mapping[str, Any], limits: FineUnaryExactResourceLimits):
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS:
        raise ValueError("exact payload fields do not exactly match the fine-unary schema")
    if payload["schema"] != SCHEMA or payload["claim"] != CLAIM:
        raise ValueError("unsupported schema or candidate claim")
    n = payload["num_buckets"]
    if type(n) is not int or n <= 0 or n % 2:
        raise ValueError("num_buckets must be a positive even exact integer")
    if n > limits.max_num_buckets:
        raise _Incomplete("num_buckets exceeds exact verification resource limit")

    intervals_raw = payload["bucket_intervals"]
    if not isinstance(intervals_raw, list) or len(intervals_raw) != n:
        raise ValueError("bucket_intervals dimension mismatch")
    intervals = []
    for index, row in enumerate(intervals_raw):
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("each bucket interval must have two endpoints")
        intervals.append(
            tuple(
                _rational(value, location=f"bucket_intervals[{index}][{side}]")
                for side, value in enumerate(row)
            )
        )
    intervals = tuple(intervals)
    if (
        intervals[0][0] != -1
        or intervals[-1][1] != 1
        or any(not -1 <= left < right <= 1 for left, right in intervals)
        or any(left[1] != right[0] for left, right in zip(intervals, intervals[1:]))
        or any(
            intervals[index]
            != (-intervals[n - 1 - index][1], -intervals[n - 1 - index][0])
            for index in range(n)
        )
    ):
        raise ValueError("bucket intervals must symmetrically partition [-1,1]")

    rounding_raw = payload["rounding"]
    if not isinstance(rounding_raw, list) or len(rounding_raw) != n:
        raise ValueError("rounding dimension mismatch")
    rounding = tuple(
        _rational(value, location=f"rounding[{index}]")
        for index, value in enumerate(rounding_raw)
    )
    if any(not 0 <= value <= 1 for value in rounding) or any(
        rounding[index] + rounding[n - 1 - index] != 1 for index in range(n)
    ):
        raise ValueError("rounding must be probability-valued and reflected")

    weights_raw = payload["weights"]
    if not isinstance(weights_raw, list) or len(weights_raw) != 5:
        raise ValueError("weights must contain exactly five entries")
    weights = tuple(
        _rational(value, location=f"weights[{index}]")
        for index, value in enumerate(weights_raw)
    )
    if (
        any(value < 0 for value in weights)
        or any(left < right for left, right in zip(weights, weights[1:]))
        or sum(weights, F(0)) != 110
    ):
        raise ValueError("weights must be nonnegative, nonincreasing, and sum to 110")
    rho = _rational(payload["rho"], location="rho")
    if not 0 <= rho <= 1:
        raise ValueError("rho must lie in [0,1]")

    lambdas_raw = payload["lambdas"]
    if not isinstance(lambdas_raw, list) or len(lambdas_raw) != 4 * n:
        raise ValueError("lambda dimension mismatch")
    lambdas = tuple(
        _rational(value, location=f"lambdas[{index}]")
        for index, value in enumerate(lambdas_raw)
    )
    if any(value < 0 for value in lambdas):
        raise ValueError("all lambda multipliers must be nonnegative")

    mapping_raw = payload["bucket_group_map"]
    if not isinstance(mapping_raw, list) or len(mapping_raw) != n or any(
        type(value) is not int or value < 0 for value in mapping_raw
    ):
        raise ValueError("bucket_group_map must contain one nonnegative integer per bucket")
    mapping = tuple(mapping_raw)
    if set(mapping) != set(range(max(mapping) + 1)):
        raise ValueError("bucket groups must be nonempty and contiguous")
    bucket_groups = max(mapping) + 1
    reflection: dict[int, int] = {}
    for group, mirror in zip(mapping, reversed(mapping)):
        old = reflection.get(group)
        if old is not None and old != mirror:
            raise ValueError("bucket_group_map is not reflection-compatible")
        reflection[group] = mirror
    if (
        len(reflection) != bucket_groups
        or set(reflection.values()) != set(range(bucket_groups))
        or any(reflection[reflection[group]] != group for group in reflection)
    ):
        raise ValueError("bucket group reflection must be an involutive permutation")
    groups = 2 * bucket_groups
    pair_count = comb(groups + 1, 2)
    if pair_count > limits.max_pair_table_entries:
        raise _Incomplete("pair table exceeds exact verification resource limit")

    members: list[list[int]] = [[] for _ in range(groups)]
    for label in range(2 * n):
        sign, bucket = divmod(label, n)
        members[sign * bucket_groups + mapping[bucket]].append(label)
    if any(not group for group in members):
        raise ValueError("every label group must contain a fine label")
    members_tuple = tuple(tuple(group) for group in members)

    tables_raw = payload["pair_tables"]
    unary_raw = payload["unary_tables"]
    if not isinstance(tables_raw, dict) or set(tables_raw) != {"3", "4", "5"}:
        raise ValueError("pair_tables must contain exactly K3/K4/K5")
    if not isinstance(unary_raw, dict) or set(unary_raw) != {"3", "4", "5"}:
        raise ValueError("unary_tables must contain exactly u3/u4/u5")
    tables: dict[int, tuple[F, ...]] = {}
    unary: dict[int, tuple[F, ...]] = {}
    for arity in ARITIES:
        raw_table = tables_raw[str(arity)]
        if not isinstance(raw_table, list) or len(raw_table) != pair_count:
            raise ValueError("group pair table dimension mismatch")
        tables[arity] = tuple(
            _rational(value, location=f"pair_tables[{arity}][{index}]")
            for index, value in enumerate(raw_table)
        )
        raw_unary = unary_raw[str(arity)]
        if not isinstance(raw_unary, list) or len(raw_unary) != 2 * n:
            raise ValueError("fine unary table dimension mismatch")
        unary[arity] = tuple(
            _rational(value, location=f"unary_tables[{arity}][{index}]")
            for index, value in enumerate(raw_unary)
        )
        if any(unary[arity][group[0]] != 0 for group in members_tuple):
            raise ValueError("one canonical fine-unary anchor per label group must equal zero")

    low_pairs = comb(2 * n + 1, 2)
    group_multisets = sum(comb(groups + arity - 1, arity) for arity in ARITIES)
    if low_pairs > limits.max_low_label_pairs:
        raise _Incomplete("low-order pair enumeration exceeds resource limit")
    if group_multisets > limits.max_group_multisets:
        raise _Incomplete("high-order group enumeration exceeds resource limit")
    return (
        n,
        intervals,
        rounding,
        weights,
        rho,
        lambdas,
        mapping,
        groups,
        members_tuple,
        tables,
        unary,
        low_pairs,
        group_multisets,
    )


def _problem_arrays(parsed: tuple[Any, ...]):
    n, intervals, rounding, weights, rho, lambdas, mapping, groups, members, tables, unary, low_pairs, group_multisets = parsed
    q = tuple(1 - value for value in rounding) + rounding
    costs = []
    for label in range(2 * n):
        sign, bucket = divmod(label, n)
        lower, upper = intervals[bucket]
        chi = F(2 * sign - 1)
        costs.append(
            tuple(
                lambdas[4 * bucket + 2 * bit] * (lower - chi)
                + lambdas[4 * bucket + 2 * bit + 1] * (chi - upper)
                for bit in (0, 1)
            )
        )
    return q, tuple(costs)


def _record_family(
    families: dict[str, dict[str, Any]],
    name: str,
    slack: F,
    argmin: Any,
    *,
    conceptual_rows: int,
    separated_rows: int,
) -> None:
    families[name] = {
        "minimum_slack": str(slack),
        "argmin": argmin,
        "conceptual_rows": conceptual_rows,
        "separated_rows": separated_rows,
    }


def verify_fine_unary_certificate(
    payload: Mapping[str, Any],
    resource_limits: FineUnaryExactResourceLimits | None = None,
) -> dict[str, Any]:
    """Replay all 14 families exactly using scalable complete separation."""

    started = perf_counter()
    limits = resource_limits or FineUnaryExactResourceLimits()
    if not isinstance(limits, FineUnaryExactResourceLimits):
        raise ValueError("resource_limits must be FineUnaryExactResourceLimits")
    try:
        parsed = _parse_payload(payload, limits)
        (
            n,
            intervals,
            rounding,
            weights,
            rho,
            lambdas,
            mapping,
            groups,
            members,
            tables,
            unary,
            low_pairs,
            group_multisets,
        ) = parsed
        q, costs = _problem_arrays(parsed)
        _time_check(started, limits)
        families: dict[str, dict[str, Any]] = {}

        # d=1 is exact after eliminating the only possible bit in each family.
        best_d1_u = min(
            (
                q[label] + weights[0] * costs[label][1 - label // n],
                label,
                1 - label // n,
            )
            for label in range(2 * n)
        )
        best_d1_s = min(
            (
                q[label] + weights[0] * costs[label][label // n] - rho,
                label,
                label // n,
            )
            for label in range(2 * n)
        )
        _record_family(
            families,
            "d1_unsatisfied",
            best_d1_u[0],
            [[best_d1_u[1], best_d1_u[2]]],
            conceptual_rows=2 * n,
            separated_rows=2 * n,
        )
        _record_family(
            families,
            "d1_satisfied",
            best_d1_s[0],
            [[best_d1_s[1], best_d1_s[2]]],
            conceptual_rows=2 * n,
            separated_rows=2 * n,
        )

        # d=2 scans every fine-label pair and eliminates its four bit choices.
        best_d2_u: tuple[F, Any] | None = None
        best_d2_s: tuple[F, Any] | None = None
        for index, (left, right) in enumerate(
            combinations_with_replacement(range(2 * n), 2), start=1
        ):
            if index & 4095 == 0:
                _time_check(started, limits)
            score = 1 - (1 - q[left]) * (1 - q[right])
            unsat_bits = (1 - left // n, 1 - right // n)
            value_u = score + weights[1] * (
                costs[left][unsat_bits[0]] + costs[right][unsat_bits[1]]
            )
            any_left = min((costs[left][bit], bit) for bit in (0, 1))
            any_right = min((costs[right][bit], bit) for bit in (0, 1))
            sat_left = (costs[left][left // n], left // n)
            sat_right = (costs[right][right // n], right // n)
            correction, forced = min(
                (sat_left[0] + any_right[0], 0),
                (any_left[0] + sat_right[0], 1),
            )
            value_s = score + weights[1] * correction - rho
            arg_u = [[left, unsat_bits[0]], [right, unsat_bits[1]]]
            bits = (
                (sat_left[1], any_right[1])
                if forced == 0
                else (any_left[1], sat_right[1])
            )
            arg_s = [[left, bits[0]], [right, bits[1]]]
            if best_d2_u is None or value_u < best_d2_u[0]:
                best_d2_u = (value_u, arg_u)
            if best_d2_s is None or value_s < best_d2_s[0]:
                best_d2_s = (value_s, arg_s)
        assert best_d2_u is not None and best_d2_s is not None
        typed_d2 = comb(4 * n + 1, 2)
        unsat_d2 = low_pairs
        _record_family(
            families,
            "d2_unsatisfied",
            best_d2_u[0],
            best_d2_u[1],
            conceptual_rows=unsat_d2,
            separated_rows=low_pairs,
        )
        _record_family(
            families,
            "d2_satisfied",
            best_d2_s[0],
            best_d2_s[1],
            conceptual_rows=typed_d2 - unsat_d2,
            separated_rows=low_pairs,
        )

        transition_count = 0
        next_transition_time_check = 16_384
        maximum_hull_size = 0
        group_rows_total = 0
        for arity in ARITIES:
            table = tables[arity]
            u = unary[arity]
            weight = weights[arity - 1]
            base_hulls: list[tuple[_HullState, ...]] = []
            for group in range(groups):
                raw = tuple(
                    _HullState(1 - q[label], u[label], (label,))
                    for label in members[group]
                )
                hull = _upper_hull(raw)
                if len(hull) > limits.max_hull_states:
                    raise _Incomplete("base fine-label hull exceeds state limit")
                base_hulls.append(hull)
                maximum_hull_size = max(maximum_hull_size, len(hull))

            group_unsat = tuple(
                min(
                    (
                        u[label] + weight * costs[label][1 - label // n],
                        label,
                        1 - label // n,
                    )
                    for label in member
                )
                for member in members
            )
            group_any = tuple(
                min(
                    (u[label] + weight * costs[label][bit], label, bit)
                    for label in member
                    for bit in (0, 1)
                )
                for member in members
            )
            group_sat = tuple(
                min(
                    (
                        u[label] + weight * costs[label][label // n],
                        label,
                        label // n,
                    )
                    for label in member
                )
                for member in members
            )
            delta = tuple(group_sat[g][0] - group_any[g][0] for g in range(groups))

            best_upper: tuple[F, tuple[int, ...]] | None = None
            best_unsat: tuple[F, Any] | None = None
            best_sat: tuple[F, Any] | None = None
            group_row_count = 0

            def visit(
                prefix: tuple[int, ...],
                hull: tuple[_HullState, ...],
                pair_total: F,
                unsat_total: F,
                any_total: F,
                deltas: tuple[F, ...],
            ) -> None:
                nonlocal transition_count, next_transition_time_check
                nonlocal maximum_hull_size, group_row_count
                nonlocal best_upper, best_unsat, best_sat
                if len(prefix) == arity:
                    group_row_count += 1
                    score_state = max(
                        hull,
                        key=lambda state: (state.intercept + state.slope, tuple(-x for x in state.labels)),
                    )
                    upper_slack = 1 - (score_state.intercept + score_state.slope)
                    upper_arg = tuple(sorted(score_state.labels))
                    if best_upper is None or upper_slack < best_upper[0]:
                        best_upper = (upper_slack, upper_arg)
                    value_u = pair_total + unsat_total
                    if best_unsat is None or value_u < best_unsat[0]:
                        arg = sorted(
                            ([group_unsat[g][1], group_unsat[g][2]] for g in prefix),
                            key=lambda item: 2 * item[0] + item[1],
                        )
                        best_unsat = (value_u, arg)
                    forced = min(range(arity), key=lambda position: (deltas[position], position))
                    value_s = pair_total + any_total + deltas[forced] - rho
                    if best_sat is None or value_s < best_sat[0]:
                        arg = []
                        for position, group in enumerate(prefix):
                            source = group_sat[group] if position == forced else group_any[group]
                            arg.append([source[1], source[2]])
                        arg.sort(key=lambda item: 2 * item[0] + item[1])
                        best_sat = (value_s, arg)
                    return

                start_group = prefix[-1] if prefix else 0
                for group in range(start_group, groups):
                    pair_add = sum(
                        (table[_pair_index(previous, group, groups)] for previous in prefix),
                        F(0),
                    )
                    candidates: list[_HullState] = []
                    base = base_hulls[group]
                    transition_count += len(hull) * len(base)
                    if transition_count > limits.max_upper_transitions:
                        raise _Incomplete("fine-unary upper hull transition limit reached")
                    for old in hull:
                        for endpoint in base:
                            candidates.append(
                                _HullState(
                                    old.slope * endpoint.slope,
                                    old.intercept + endpoint.intercept + pair_add,
                                    old.labels + endpoint.labels,
                                )
                            )
                    next_hull = _upper_hull(candidates)
                    if len(next_hull) > limits.max_hull_states:
                        raise _Incomplete("fine-unary prefix hull exceeds state limit")
                    maximum_hull_size = max(maximum_hull_size, len(next_hull))
                    if transition_count >= next_transition_time_check:
                        _time_check(started, limits)
                        while next_transition_time_check <= transition_count:
                            next_transition_time_check += 16_384
                    visit(
                        prefix + (group,),
                        next_hull,
                        pair_total + pair_add,
                        unsat_total + group_unsat[group][0],
                        any_total + group_any[group][0],
                        deltas + (delta[group],),
                    )

            visit((), (_HullState(F(1), F(0), ()),), F(0), F(0), F(0), ())
            expected_group_rows = comb(groups + arity - 1, arity)
            if group_row_count != expected_group_rows:
                raise RuntimeError("internal group-multiset coverage mismatch")
            group_rows_total += group_row_count
            assert best_upper is not None and best_unsat is not None and best_sat is not None
            upper_rows = comb(2 * n + arity - 1, arity)
            typed_rows = comb(4 * n + arity - 1, arity)
            unsat_rows = upper_rows
            _record_family(
                families,
                f"d{arity}_upper",
                best_upper[0],
                list(best_upper[1]),
                conceptual_rows=upper_rows,
                separated_rows=group_row_count,
            )
            _record_family(
                families,
                f"d{arity}_unsatisfied",
                best_unsat[0],
                best_unsat[1],
                conceptual_rows=unsat_rows,
                separated_rows=group_row_count,
            )
            _record_family(
                families,
                f"d{arity}_satisfied",
                best_sat[0],
                best_sat[1],
                conceptual_rows=typed_rows - unsat_rows,
                separated_rows=group_row_count,
            )
            _time_check(started, limits)

        long_bound = 1 - (1 - min(q)) ** 6
        _record_family(
            families,
            "long_floor",
            long_bound - rho,
            None,
            conceptual_rows=1,
            separated_rows=1,
        )
        if set(families) != EXPECTED_FAMILIES:
            raise RuntimeError("internal 14-family accounting mismatch")
        minimum = min(F(family["minimum_slack"]) for family in families.values())
        ok = minimum >= 0
        return {
            "schema": SCHEMA,
            "ok": ok,
            "status": "exact_rational_certificate" if ok else "invalid_exact_witness",
            "rho": str(rho),
            "minimum_slack": str(minimum),
            "long_bound": str(long_bound),
            "families": families,
            "all_14_families_verified": True,
            "all_low_order_rows_checked": True,
            "all_high_order_rows_checked": True,
            "complete_separation": True,
            "upper_separation": "exact_fraction_group_multiset_dfs_with_[0,1]_line_hulls",
            "upper_hull_equivalence": True,
            "lower_group_minimum_equivalence": True,
            "fine_unary_anchor_gauge_verified": True,
            "num_buckets": n,
            "num_profiles": 1,
            "num_label_groups": groups,
            "low_label_pairs": low_pairs,
            "group_multisets": group_rows_total,
            "upper_hull_transitions": transition_count,
            "maximum_upper_hull_size": maximum_hull_size,
            "payload_sha256": sha256(_canonical_bytes(payload)).hexdigest(),
            "elapsed_seconds": perf_counter() - started,
        }
    except _Incomplete as error:
        return {
            "schema": SCHEMA,
            "ok": False,
            "status": "incomplete_resource_limit",
            "reason": str(error),
            "all_14_families_verified": False,
            "all_low_order_rows_checked": False,
            "all_high_order_rows_checked": False,
            "complete_separation": False,
            "elapsed_seconds": perf_counter() - started,
        }


def verify_fine_unary_certificate_bruteforce(
    payload: Mapping[str, Any], *, max_num_buckets: int = 8
) -> dict[str, Any]:
    """Independent all-row Fraction reference for small fixtures only."""

    if type(max_num_buckets) is not int or max_num_buckets <= 0:
        raise ValueError("max_num_buckets must be a positive exact integer")
    limits = FineUnaryExactResourceLimits(
        max_num_buckets=max_num_buckets,
        max_low_label_pairs=10_000_000,
        max_group_multisets=10_000_000,
        max_pair_table_entries=100_000,
        max_hull_states=100_000,
        max_upper_transitions=1,
        max_seconds=None,
    )
    parsed = _parse_payload(payload, limits)
    n, _, _, weights, rho, _, mapping, groups, _, tables, unary, _, _ = parsed
    q, costs = _problem_arrays(parsed)
    bucket_groups = groups // 2

    def label_group(label: int) -> int:
        sign, bucket = divmod(label, n)
        return sign * bucket_groups + mapping[bucket]

    def h_value(labels: Sequence[int], arity: int) -> F:
        grouped = tuple(label_group(label) for label in labels)
        return sum((unary[arity][label] for label in labels), F(0)) + _pair_sum(
            tables[arity], grouped, groups
        )

    families: dict[str, dict[str, Any]] = {}
    for arity in ARITIES:
        best: tuple[F, Any] | None = None
        count = 0
        for labels in combinations_with_replacement(range(2 * n), arity):
            count += 1
            score = 1 - reduce(lambda value, label: value * (1 - q[label]), labels, F(1))
            slack = score - h_value(labels, arity)
            if best is None or slack < best[0]:
                best = (slack, list(labels))
        assert best is not None
        _record_family(
            families,
            f"d{arity}_upper",
            best[0],
            best[1],
            conceptual_rows=count,
            separated_rows=count,
        )

    typed_count = 4 * n
    for arity in range(1, 6):
        best: dict[bool, tuple[F, Any] | None] = {False: None, True: None}
        counts = {False: 0, True: 0}
        for atom in combinations_with_replacement(range(typed_count), arity):
            decoded = tuple(divmod(endpoint, 2) for endpoint in atom)
            labels = tuple(label for label, _ in decoded)
            if arity <= 2:
                score = 1 - reduce(lambda value, label: value * (1 - q[label]), labels, F(1))
            else:
                score = h_value(labels, arity)
            correction = weights[arity - 1] * sum(
                (costs[label][bit] for label, bit in decoded), F(0)
            )
            satisfied = any(bit == label // n for label, bit in decoded)
            slack = score + correction - (rho if satisfied else 0)
            counts[satisfied] += 1
            current = best[satisfied]
            if current is None or slack < current[0]:
                best[satisfied] = (slack, [[label, bit] for label, bit in decoded])
        for satisfied, kind in ((False, "unsatisfied"), (True, "satisfied")):
            current = best[satisfied]
            assert current is not None
            _record_family(
                families,
                f"d{arity}_{kind}",
                current[0],
                current[1],
                conceptual_rows=counts[satisfied],
                separated_rows=counts[satisfied],
            )

    long_bound = 1 - (1 - min(q)) ** 6
    _record_family(
        families,
        "long_floor",
        long_bound - rho,
        None,
        conceptual_rows=1,
        separated_rows=1,
    )
    minimum = min(F(family["minimum_slack"]) for family in families.values())
    return {
        "schema": SCHEMA,
        "ok": minimum >= 0,
        "status": "exact_bruteforce_all_rows",
        "rho": str(rho),
        "minimum_slack": str(minimum),
        "long_bound": str(long_bound),
        "families": families,
        "all_14_families_verified": set(families) == EXPECTED_FAMILIES,
        "complete_separation": True,
        "enumeration": "all_fine_label_and_typed_endpoint_multisets",
    }


__all__ = [
    "ARITIES",
    "CLAIM",
    "EXPECTED_FAMILIES",
    "FineUnaryExactResourceLimits",
    "PAYLOAD_KEYS",
    "SCHEMA",
    "verify_fine_unary_certificate",
    "verify_fine_unary_certificate_bruteforce",
]
