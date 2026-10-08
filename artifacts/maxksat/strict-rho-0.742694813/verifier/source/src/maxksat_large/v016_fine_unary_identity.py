"""Strict identity and float-to-exact binding for fine-unary certificates."""
from __future__ import annotations

from fractions import Fraction as F
from hashlib import sha256
import json
from math import comb, isfinite
from pathlib import PurePosixPath
from typing import Any, Mapping

from .v016_fine_unary_exact import CLAIM, PAYLOAD_KEYS, SCHEMA


IDENTITY_SCHEMA = "v016-j1-fine-unary-certificate-identity-v1"
NUMERICAL_SCHEMA = "v016-fine-unary-numerical-candidate-v1"
CONVERSION_SCHEMA = "v016-fine-unary-binary-fraction-repair-v1"
FORMULATION = "scaled-k-pair-h5-v1"
BOUNDARY_CONVENTION = "left-closed-right-open-last-closed"
CLASSIC_DESIGN_KEYS = frozenset(
    {
        "formulation_version",
        "tick_denominator",
        "positive_bucket_boundary_ticks",
        "profile_rounding_ticks",
        "bias_weight_ticks",
        "eta_min_ticks",
        "monotone_rounding",
        "boundary_convention",
    }
)
RATIONAL_DESIGN_KEYS = frozenset(
    {
        "schema_version",
        "formulation_version",
        "tick_denominator",
        "positive_bucket_boundary_ticks",
        "profile_rounding_ticks",
        "weight_numerators",
        "weight_denominator",
        "eta_min_ticks",
        "monotone_rounding",
        "boundary_convention",
    }
)
NUMERICAL_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "outer_design",
        "design_hash",
        "bucket_group_map",
        "witness",
        "check",
        "verified_rho",
        "is_exact_certificate",
        "is_full_certificate",
        "code_sha256",
        "source_sha256",
    }
)
WITNESS_KEYS = frozenset({"rho", "lambdas", "pair_tables", "unary_tables"})
CHECK_KEYS = frozenset(
    {
        "ok",
        "complete_separation",
        "all_low_order_rows_checked",
        "all_high_order_rows_checked",
        "all_fine_upper_rows_checked",
        "all_fine_typed_rows_checked",
        "floating_fixed_witness_rho",
    }
)
CONVERSION_KEYS = frozenset(
    {
        "schema_version",
        "numerical_payload_sha256",
        "target_policy",
        "lambda_policy",
        "gauge_policy",
        "coefficient_policy",
        "repair_padding",
        "per_pair_downward_shifts",
        "raw_upper_minima",
        "target_downshift_from_checked_numerical",
    }
)


def strict_json_loads(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("invalid JSON document") from error


def canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    encoded = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (encoded + ("\n" if newline else "")).encode("utf-8")


def _hash(value: Any) -> str:
    return sha256(canonical_json_bytes(value)).hexdigest()


def _integer(value: Any, *, location: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{location} must be an exact JSON integer")
    return value


def _rational(value: Any, *, location: str) -> F:
    if isinstance(value, (bool, float)):
        raise ValueError(f"{location} must be a canonical rational string or integer")
    try:
        result = F(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError(f"invalid rational at {location}") from error
    if isinstance(value, str) and value != str(result):
        raise ValueError(f"noncanonical rational at {location}")
    return result


def _finite_float(value: Any, *, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{location} must be a numerical scalar")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{location} must be finite")
    return result


def _sha_token(value: Any, *, location: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{location} must be a lowercase SHA-256 digest")
    return value


def validate_outer_design(design: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the two J=1 design encodings used by this project."""

    if not isinstance(design, dict):
        raise ValueError("outer design must be an object")
    keys = set(design)
    if keys == CLASSIC_DESIGN_KEYS:
        adapter = "classic-integer-weight-j1"
    elif keys == RATIONAL_DESIGN_KEYS:
        if design["schema_version"] != "large-rational-weight-design-v1":
            raise ValueError("unsupported rational-weight design schema")
        adapter = "rational-weight-j1"
    else:
        raise ValueError("outer design fields do not match an admitted J=1 schema")
    if (
        design["formulation_version"] != FORMULATION
        or design["boundary_convention"] != BOUNDARY_CONVENTION
        or design["monotone_rounding"] is not True
    ):
        raise ValueError("unsupported formulation, boundary convention, or monotonicity")
    denominator = _integer(design["tick_denominator"], location="tick_denominator")
    if not 2 <= denominator <= 10**12:
        raise ValueError("tick_denominator outside admitted domain")
    boundaries = tuple(
        _integer(value, location="positive_bucket_boundary_ticks")
        for value in design["positive_bucket_boundary_ticks"]
    )
    positive = len(boundaries) + 1
    if (
        not 1 <= positive <= 4096
        or any(not 0 < value < denominator for value in boundaries)
        or any(left >= right for left, right in zip(boundaries, boundaries[1:]))
    ):
        raise ValueError("invalid positive bias partition")
    profiles = design["profile_rounding_ticks"]
    if not isinstance(profiles, list) or len(profiles) != 1 or not isinstance(profiles[0], list):
        raise ValueError("fine-unary identity requires exactly J=1")
    ticks = tuple(_integer(value, location="profile_rounding_ticks") for value in profiles[0])
    if (
        len(ticks) != positive
        or any(not denominator <= 2 * value <= 2 * denominator for value in ticks)
        or any(left > right for left, right in zip(ticks, ticks[1:]))
    ):
        raise ValueError("J=1 rounding must be monotone with values in [1/2,1]")
    if adapter == "classic-integer-weight-j1":
        raw_weights = design["bias_weight_ticks"]
        if not isinstance(raw_weights, list):
            raise ValueError("bias_weight_ticks must be an array")
        weights = tuple(F(_integer(value, location="bias_weight_ticks")) for value in raw_weights)
    else:
        raw_weights = design["weight_numerators"]
        weight_denominator = _integer(design["weight_denominator"], location="weight_denominator")
        if not isinstance(raw_weights, list) or weight_denominator <= 0:
            raise ValueError("rational weights require an array and positive denominator")
        weights = tuple(
            F(_integer(value, location="weight_numerators"), weight_denominator)
            for value in raw_weights
        )
    if (
        len(weights) != 5
        or any(value < 0 for value in weights)
        or any(left < right for left, right in zip(weights, weights[1:]))
        or sum(weights, F(0)) != 110
    ):
        raise ValueError("weights must be nonnegative, nonincreasing, and sum to 110")
    eta_min_ticks = _integer(design["eta_min_ticks"], location="eta_min_ticks")
    if not 0 < eta_min_ticks <= denominator:
        raise ValueError("eta_min_ticks outside admitted domain")
    positive_edges = tuple(F(value, denominator) for value in boundaries)
    edges = (F(-1), *(-value for value in reversed(positive_edges)), F(0), *positive_edges, F(1))
    positive_q = tuple(F(value, denominator) for value in ticks)
    rounding = tuple(1 - value for value in reversed(positive_q)) + positive_q
    return {
        "outer_design_hash": _hash(design),
        "adapter": adapter,
        "num_buckets": 2 * positive,
        "intervals": tuple(zip(edges, edges[1:])),
        "rounding": rounding,
        "weights": weights,
        "positive_bucket_count": positive,
        "distinct_positive_q": len(set(positive_q)),
        "distinct_full_q": len(set(rounding)),
    }


def _validate_hash_map(value: Any, *, location: str, paths: bool) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{location} must be a nonempty hash object")
    result: dict[str, str] = {}
    for name, digest in value.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"{location} contains an invalid name")
        if paths:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or path.suffix != ".py" or path.parts[0] not in {"src", "scripts"}:
                raise ValueError(f"{location} contains an unsafe code path")
        result[name] = _sha_token(digest, location=f"{location}.{name}")
    return result


def validate_numerical_payload(numerical: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(numerical, dict) or set(numerical) != NUMERICAL_KEYS:
        raise ValueError("numerical payload fields do not exactly match schema")
    if (
        numerical["schema_version"] != NUMERICAL_SCHEMA
        or numerical["status"] != "complete_fine_unary_numeric_candidate"
        or numerical["verified_rho"] is not None
        or numerical["is_exact_certificate"] is not False
        or numerical["is_full_certificate"] is not False
    ):
        raise ValueError("numerical payload has an inadmissible status or claim")
    outer = validate_outer_design(numerical["outer_design"])
    if numerical["design_hash"] != outer["outer_design_hash"]:
        raise ValueError("numerical design hash is not canonical")
    mapping = numerical["bucket_group_map"]
    if (
        not isinstance(mapping, list)
        or len(mapping) != outer["num_buckets"]
        or any(type(value) is not int or value < 0 for value in mapping)
        or set(mapping) != set(range(max(mapping) + 1))
    ):
        raise ValueError("numerical bucket_group_map is malformed")
    witness = numerical["witness"]
    if not isinstance(witness, dict) or set(witness) != WITNESS_KEYS:
        raise ValueError("numerical witness fields do not exactly match schema")
    check = numerical["check"]
    if not isinstance(check, dict) or set(check) != CHECK_KEYS or any(
        check[name] is not True
        for name in (
            "ok",
            "complete_separation",
            "all_low_order_rows_checked",
            "all_high_order_rows_checked",
            "all_fine_upper_rows_checked",
            "all_fine_typed_rows_checked",
        )
    ):
        raise ValueError("numerical semantic check is incomplete")
    checked_rho = _finite_float(check["floating_fixed_witness_rho"], location="check.floating_fixed_witness_rho")
    raw_rho = _finite_float(witness["rho"], location="witness.rho")
    if not 0 <= checked_rho <= raw_rho + 1e-8 or not 0 <= raw_rho <= 1:
        raise ValueError("numerical rho fields are inconsistent")
    n = outer["num_buckets"]
    lambdas = witness["lambdas"]
    if not isinstance(lambdas, list) or len(lambdas) != 4 * n:
        raise ValueError("numerical lambda dimension mismatch")
    lambda_float = tuple(_finite_float(value, location="witness.lambdas") for value in lambdas)
    if any(value < 0 for value in lambda_float):
        raise ValueError("numerical lambdas must be nonnegative")
    groups = 2 * (max(mapping) + 1)
    pair_count = comb(groups + 1, 2)
    pair_tables = witness["pair_tables"]
    unary_tables = witness["unary_tables"]
    if not isinstance(pair_tables, dict) or set(pair_tables) != {"3", "4", "5"}:
        raise ValueError("numerical pair tables must contain exactly 3/4/5")
    if not isinstance(unary_tables, dict) or set(unary_tables) != {"3", "4", "5"}:
        raise ValueError("numerical unary tables must contain exactly 3/4/5")
    parsed_pair: dict[int, tuple[float, ...]] = {}
    parsed_unary: dict[int, tuple[float, ...]] = {}
    for arity in (3, 4, 5):
        raw_pair = pair_tables[str(arity)]
        raw_unary = unary_tables[str(arity)]
        if not isinstance(raw_pair, list) or len(raw_pair) != pair_count:
            raise ValueError("numerical pair-table dimension mismatch")
        if not isinstance(raw_unary, list) or len(raw_unary) != 2 * n:
            raise ValueError("numerical unary-table dimension mismatch")
        parsed_pair[arity] = tuple(_finite_float(value, location="witness.pair_tables") for value in raw_pair)
        parsed_unary[arity] = tuple(_finite_float(value, location="witness.unary_tables") for value in raw_unary)
    code = _validate_hash_map(numerical["code_sha256"], location="code_sha256", paths=True)
    sources = _validate_hash_map(numerical["source_sha256"], location="source_sha256", paths=False)
    return {
        "outer": outer,
        "mapping": tuple(mapping),
        "rho": raw_rho,
        "checked_rho": checked_rho,
        "lambdas": lambda_float,
        "pair_tables": parsed_pair,
        "unary_tables": parsed_unary,
        "code_sha256": code,
        "source_sha256": sources,
    }


def verify_fine_unary_identity(
    certificate: Mapping[str, Any],
    *,
    expected_design: Mapping[str, Any],
    expected_rho: Any | None = None,
    numerical_payload_bytes: bytes | None = None,
    expected_numerical_payload_sha256: str | None = None,
    float_to_exact_repair: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind literal proof fields to design and, when supplied, numerical bytes."""

    if not isinstance(certificate, dict) or set(certificate) != PAYLOAD_KEYS:
        raise ValueError("certificate fields do not exactly match raw schema")
    if certificate["schema"] != SCHEMA or certificate["claim"] != CLAIM:
        raise ValueError("unsupported certificate schema or claim")
    outer = validate_outer_design(expected_design)
    n = outer["num_buckets"]
    if certificate["num_buckets"] != n:
        raise ValueError("raw bucket count differs from outer design")
    rounding = tuple(_rational(value, location="rounding") for value in certificate["rounding"])
    intervals = tuple(
        tuple(_rational(value, location="bucket_intervals") for value in row)
        for row in certificate["bucket_intervals"]
    )
    weights = tuple(_rational(value, location="weights") for value in certificate["weights"])
    if rounding != outer["rounding"] or intervals != outer["intervals"] or weights != outer["weights"]:
        raise ValueError("raw q/interval/weight fields differ from outer design")
    rho = _rational(certificate["rho"], location="rho")
    if expected_rho is not None and rho != F(expected_rho):
        raise ValueError("raw rho differs from requested exact target")
    mapping = certificate["bucket_group_map"]
    if not isinstance(mapping, list) or len(mapping) != n:
        raise ValueError("raw group map dimension mismatch")
    lambdas = tuple(_rational(value, location="lambdas") for value in certificate["lambdas"])
    exact_unary = {
        arity: tuple(_rational(value, location="unary_tables") for value in certificate["unary_tables"][str(arity)])
        for arity in (3, 4, 5)
    }
    exact_pair = {
        arity: tuple(_rational(value, location="pair_tables") for value in certificate["pair_tables"][str(arity)])
        for arity in (3, 4, 5)
    }
    result = {
        "identity_schema": IDENTITY_SCHEMA,
        "identity_verified": True,
        "model_restrictions_verified": True,
        "outer_design_hash": outer["outer_design_hash"],
        "raw_design_content_hash": _hash(
            {key: certificate[key] for key in ("num_buckets", "rounding", "bucket_intervals", "weights")}
        ),
        "raw_witness_content_hash": _hash(certificate),
        "group_map_content_hash": _hash(mapping),
        "unary_content_hash": _hash(certificate["unary_tables"]),
        "pair_content_hash": _hash(certificate["pair_tables"]),
        "lambda_content_hash": _hash(certificate["lambdas"]),
        "rho_bound": str(rho),
        "numerical_payload_bound": False,
        "float_to_exact_repair_verified": False,
        "model_restrictions": {
            "J": 1,
            "surrogate": "fine-label unary plus coarse-label-group pair",
            "arity": [3, 4, 5],
            "maximum_endpoint_order": 2,
            "weight_budget": 110,
            "boundary_convention": BOUNDARY_CONVENTION,
        },
    }
    if numerical_payload_bytes is None:
        if expected_numerical_payload_sha256 is not None or float_to_exact_repair is not None:
            raise ValueError("partial numerical identity binding is forbidden")
        return result
    numerical_sha = sha256(numerical_payload_bytes).hexdigest()
    if expected_numerical_payload_sha256 != numerical_sha:
        raise ValueError("numerical payload SHA256 mismatch")
    try:
        numerical = strict_json_loads(numerical_payload_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError("numerical payload must be UTF-8 JSON") from error
    parsed = validate_numerical_payload(numerical)
    if parsed["outer"]["outer_design_hash"] != outer["outer_design_hash"]:
        raise ValueError("numerical and exact outer designs differ")
    if parsed["mapping"] != tuple(mapping):
        raise ValueError("numerical and exact group maps differ")
    repair = float_to_exact_repair
    if not isinstance(repair, dict) or set(repair) != CONVERSION_KEYS:
        raise ValueError("float-to-exact repair fields do not exactly match schema")
    if repair["schema_version"] != CONVERSION_SCHEMA or repair["numerical_payload_sha256"] != numerical_sha:
        raise ValueError("float-to-exact repair does not bind numerical bytes")
    padding = _rational(repair["repair_padding"], location="repair_padding")
    if padding <= 0:
        raise ValueError("repair padding must be positive")
    expected_target_downshift = F.from_float(parsed["checked_rho"]) - rho
    if _rational(repair["target_downshift_from_checked_numerical"], location="target_downshift") != expected_target_downshift or expected_target_downshift < 0:
        raise ValueError("target does not match checked numerical rho binding")
    shifts_raw = repair["per_pair_downward_shifts"]
    minima_raw = repair["raw_upper_minima"]
    if not isinstance(shifts_raw, dict) or set(shifts_raw) != {"3", "4", "5"}:
        raise ValueError("repair shifts must contain exactly 3/4/5")
    if not isinstance(minima_raw, dict) or set(minima_raw) != {"3", "4", "5"}:
        raise ValueError("raw upper minima must contain exactly 3/4/5")
    shifts = {arity: _rational(shifts_raw[str(arity)], location="per_pair_shift") for arity in (3, 4, 5)}
    if any(value <= 0 for value in shifts.values()):
        raise ValueError("every per-pair repair shift must be positive")
    raw_minima = {
        arity: _rational(minima_raw[str(arity)], location="raw_upper_minimum")
        for arity in (3, 4, 5)
    }
    if any(
        shifts[arity]
        != (max(F(0), -raw_minima[arity]) + padding) / comb(arity, 2)
        for arity in (3, 4, 5)
    ):
        raise ValueError("per-pair repair shift does not match declared upper minimum and padding")
    members: list[list[int]] = [[] for _ in range(2 * (max(mapping) + 1))]
    bucket_groups = max(mapping) + 1
    for label in range(2 * n):
        sign, bucket = divmod(label, n)
        members[sign * bucket_groups + mapping[bucket]].append(label)
    rebuilt_unary: dict[int, tuple[F, ...]] = {}
    rebuilt_pair: dict[int, tuple[F, ...]] = {}
    for arity in (3, 4, 5):
        raw_u = tuple(F.from_float(value) for value in parsed["unary_tables"][arity])
        raw_k = list(F.from_float(value) for value in parsed["pair_tables"][arity])
        anchors = tuple(group[0] for group in members)
        group_shift = tuple(raw_u[anchor] for anchor in anchors)
        normalized_u = tuple(
            value - group_shift[sign * bucket_groups + mapping[label % n]]
            for label, value in enumerate(raw_u)
            for sign in (label // n,)
        )
        groups = len(members)
        for left in range(groups):
            for right in range(left, groups):
                index = left * groups - left * (left - 1) // 2 + right - left
                raw_k[index] += (group_shift[left] + group_shift[right]) / (arity - 1)
        rebuilt_unary[arity] = normalized_u
        rebuilt_pair[arity] = tuple(value - shifts[arity] for value in raw_k)
    if rebuilt_unary != exact_unary or rebuilt_pair != exact_pair:
        raise ValueError("exact u/K fields do not equal the declared binary/gauge/shift conversion")
    if tuple(F.from_float(value) for value in parsed["lambdas"]) != lambdas:
        raise ValueError("exact lambdas do not equal numerical binary fractions")
    if repair["target_policy"] != "exact_target_not_above_checked_floating_rho" or repair["lambda_policy"] != "nonnegative_float_to_exact_binary_fraction" or repair["gauge_policy"] != "subtract_one_anchor_per_label_group_and_absorb_into_K" or repair["coefficient_policy"] != "exact_binary_u_and_K_then_uniform_per_pair_downward_upper_repair":
        raise ValueError("repair policy labels are not the admitted conversion")
    result.update(
        numerical_payload_bound=True,
        float_to_exact_repair_verified=True,
        numerical_payload_sha256=numerical_sha,
        numerical_code_sha256=parsed["code_sha256"],
        numerical_source_sha256=parsed["source_sha256"],
    )
    return result


__all__ = [
    "BOUNDARY_CONVENTION",
    "CHECK_KEYS",
    "CONVERSION_KEYS",
    "CONVERSION_SCHEMA",
    "IDENTITY_SCHEMA",
    "NUMERICAL_KEYS",
    "NUMERICAL_SCHEMA",
    "WITNESS_KEYS",
    "canonical_json_bytes",
    "strict_json_loads",
    "validate_numerical_payload",
    "validate_outer_design",
    "verify_fine_unary_identity",
]
