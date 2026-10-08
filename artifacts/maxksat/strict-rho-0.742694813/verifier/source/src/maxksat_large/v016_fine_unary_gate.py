"""Fail-closed promotion gate for v016 J=1 fine-unary certificates."""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from typing import Any

from .v016_fine_unary_exact import (
    CLAIM,
    EXPECTED_FAMILIES,
    FineUnaryExactResourceLimits,
    SCHEMA,
    verify_fine_unary_certificate,
)
from .v016_fine_unary_identity import (
    CONVERSION_SCHEMA,
    canonical_json_bytes,
    strict_json_loads,
    validate_numerical_payload,
    verify_fine_unary_identity,
)


ARTIFACT_SCHEMA = "v016-fine-unary-exact-promotion-artifact-v1"
ARTIFACT_KEYS = frozenset(
    {
        "schema",
        "certificate",
        "outer_design",
        "outer_design_hash",
        "numerical_payload_path",
        "numerical_payload_sha256",
        "float_to_exact_repair",
    }
)
GATE_SCHEMA = "v016-fine-unary-independent-exact-gate-v1"


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(canonical_json_bytes(value, newline=True))
    temporary.replace(path)


def _exact(value: Any, *, location: str) -> F:
    if isinstance(value, (bool, float)):
        raise ValueError(f"{location} must be exact, not float/bool")
    try:
        return F(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError(f"invalid exact rational at {location}") from error


def _check_numerical_code_hashes(parsed: dict[str, Any], root: Path) -> None:
    for relative, declared in parsed["code_sha256"].items():
        source = (root / Path(relative)).resolve()
        try:
            source.relative_to(root)
        except ValueError as error:
            raise ValueError("numerical code path escapes project root") from error
        if not source.is_file() or _digest(source) != declared:
            raise ValueError(f"numerical code SHA256 mismatch: {relative}")


def _raw_exact_coefficients(parsed: dict[str, Any]):
    n = parsed["outer"]["num_buckets"]
    mapping = parsed["mapping"]
    bucket_groups = max(mapping) + 1
    groups = 2 * bucket_groups
    members: list[list[int]] = [[] for _ in range(groups)]
    for label in range(2 * n):
        sign, bucket = divmod(label, n)
        members[sign * bucket_groups + mapping[bucket]].append(label)
    exact_unary: dict[int, tuple[F, ...]] = {}
    exact_pair: dict[int, tuple[F, ...]] = {}
    for arity in (3, 4, 5):
        raw_u = tuple(F.from_float(value) for value in parsed["unary_tables"][arity])
        raw_k = list(F.from_float(value) for value in parsed["pair_tables"][arity])
        shifts = tuple(raw_u[group[0]] for group in members)
        exact_unary[arity] = tuple(
            value - shifts[(label // n) * bucket_groups + mapping[label % n]]
            for label, value in enumerate(raw_u)
        )
        for left in range(groups):
            for right in range(left, groups):
                index = left * groups - left * (left - 1) // 2 + right - left
                raw_k[index] += (shifts[left] + shifts[right]) / (arity - 1)
        exact_pair[arity] = tuple(raw_k)
    return exact_unary, exact_pair


def _certificate(
    parsed: dict[str, Any],
    target: F,
    unary: dict[int, tuple[F, ...]],
    pair: dict[int, tuple[F, ...]],
) -> dict[str, Any]:
    outer = parsed["outer"]
    return {
        "schema": SCHEMA,
        "claim": CLAIM,
        "num_buckets": outer["num_buckets"],
        "rounding": [str(value) for value in outer["rounding"]],
        "bucket_intervals": [
            [str(left), str(right)] for left, right in outer["intervals"]
        ],
        "weights": [str(value) for value in outer["weights"]],
        "rho": str(target),
        "lambdas": [str(F.from_float(value)) for value in parsed["lambdas"]],
        "bucket_group_map": list(parsed["mapping"]),
        "unary_tables": {
            str(arity): [str(value) for value in unary[arity]]
            for arity in (3, 4, 5)
        },
        "pair_tables": {
            str(arity): [str(value) for value in pair[arity]]
            for arity in (3, 4, 5)
        },
    }


def prepare_fine_unary_exact_artifact(
    numerical_payload_path: str | Path,
    artifact_output_path: str | Path,
    *,
    target_rho: Any,
    repair_padding: Any = F(1, 10**12),
    resource_limits: FineUnaryExactResourceLimits | None = None,
) -> dict[str, Any]:
    """Convert a complete float candidate, repair upper roundoff, and replay."""

    numerical_path = Path(numerical_payload_path).resolve()
    output_path = Path(artifact_output_path).resolve()
    if not numerical_path.is_file():
        raise ValueError("numerical payload path must name an existing file")
    if output_path.exists():
        raise FileExistsError("exact artifact output already exists")
    numerical_bytes = numerical_path.read_bytes()
    numerical_sha = sha256(numerical_bytes).hexdigest()
    try:
        numerical = strict_json_loads(numerical_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError("numerical payload must be UTF-8 JSON") from error
    parsed = validate_numerical_payload(numerical)
    project_root = Path(__file__).resolve().parents[2]
    _check_numerical_code_hashes(parsed, project_root)
    target = _exact(target_rho, location="target_rho")
    padding = _exact(repair_padding, location="repair_padding")
    if not 0 <= target <= F.from_float(parsed["checked_rho"]) or padding <= 0:
        raise ValueError("target must be exact and no greater than checked rho; padding must be positive")
    exact_unary, raw_pair = _raw_exact_coefficients(parsed)
    provisional = _certificate(parsed, target, exact_unary, raw_pair)
    raw_report = verify_fine_unary_certificate(provisional, resource_limits)
    if raw_report.get("complete_separation") is not True or set(raw_report.get("families", {})) != EXPECTED_FAMILIES:
        raise ValueError("raw binary candidate did not complete exact upper separation")
    raw_minima = {
        arity: F(raw_report["families"][f"d{arity}_upper"]["minimum_slack"])
        for arity in (3, 4, 5)
    }
    shifts = {
        arity: (max(F(0), -raw_minima[arity]) + padding) / (arity * (arity - 1) // 2)
        for arity in (3, 4, 5)
    }
    repaired_pair = {
        arity: tuple(value - shifts[arity] for value in raw_pair[arity])
        for arity in (3, 4, 5)
    }
    certificate = _certificate(parsed, target, exact_unary, repaired_pair)
    repair = {
        "schema_version": CONVERSION_SCHEMA,
        "numerical_payload_sha256": numerical_sha,
        "target_policy": "exact_target_not_above_checked_floating_rho",
        "lambda_policy": "nonnegative_float_to_exact_binary_fraction",
        "gauge_policy": "subtract_one_anchor_per_label_group_and_absorb_into_K",
        "coefficient_policy": "exact_binary_u_and_K_then_uniform_per_pair_downward_upper_repair",
        "repair_padding": str(padding),
        "per_pair_downward_shifts": {
            str(arity): str(shifts[arity]) for arity in (3, 4, 5)
        },
        "raw_upper_minima": {
            str(arity): str(raw_minima[arity]) for arity in (3, 4, 5)
        },
        "target_downshift_from_checked_numerical": str(
            F.from_float(parsed["checked_rho"]) - target
        ),
    }
    identity = verify_fine_unary_identity(
        certificate,
        expected_design=numerical["outer_design"],
        expected_rho=target,
        numerical_payload_bytes=numerical_bytes,
        expected_numerical_payload_sha256=numerical_sha,
        float_to_exact_repair=repair,
    )
    exact_report = verify_fine_unary_certificate(certificate, resource_limits)
    if (
        identity.get("identity_verified") is not True
        or identity.get("numerical_payload_bound") is not True
        or identity.get("float_to_exact_repair_verified") is not True
        or exact_report.get("ok") is not True
        or exact_report.get("status") != "exact_rational_certificate"
        or exact_report.get("all_14_families_verified") is not True
        or exact_report.get("complete_separation") is not True
    ):
        raise ValueError("exact conversion failed identity or complete 14-family replay")
    artifact = {
        "schema": ARTIFACT_SCHEMA,
        "certificate": certificate,
        "outer_design": numerical["outer_design"],
        "outer_design_hash": parsed["outer"]["outer_design_hash"],
        "numerical_payload_path": str(numerical_path),
        "numerical_payload_sha256": numerical_sha,
        "float_to_exact_repair": repair,
    }
    payload = canonical_json_bytes(artifact, newline=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as handle:
        handle.write(payload)
    return {
        "status": "exact_candidate_preflight_passed",
        "artifact_path": str(output_path),
        "artifact_sha256": sha256(payload).hexdigest(),
        "numerical_payload_sha256": numerical_sha,
        "outer_design_hash": parsed["outer"]["outer_design_hash"],
        "target_rho": str(target),
        "checked_numerical_rho": repr(parsed["checked_rho"]),
        "per_pair_downward_shifts": repair["per_pair_downward_shifts"],
        "raw_upper_minima": repair["raw_upper_minima"],
        "identity": identity,
        "exact_preflight": exact_report,
    }


def verify_fine_unary_artifact(
    artifact_path: str | Path,
    new_output_dir: str | Path,
    expected_design_hash: str | None = None,
    *,
    resource_limits: FineUnaryExactResourceLimits | None = None,
) -> dict[str, Any]:
    """Re-read immutable bytes and emit verified_rho only after every gate."""

    source = Path(artifact_path).resolve()
    output = Path(new_output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    if not source.is_file():
        raise ValueError("promotion artifact path must name an existing file")
    package = Path(__file__).resolve().parent
    project_root = package.parents[1]
    source_names = (
        "v016_fine_unary_exact.py",
        "v016_fine_unary_identity.py",
        "v016_fine_unary_gate.py",
    )
    artifact_hash = _digest(source)
    verifier_hashes = {name: _digest(package / name) for name in source_names}
    record: dict[str, Any] = {
        "schema_version": GATE_SCHEMA,
        "status": "running",
        "started_utc": _utc_now(),
        "verified_rho": None,
        "artifact_path": str(source),
        "artifact_sha256": artifact_hash,
        "verifier_source_sha256": verifier_hashes,
    }
    _write_json(output / "attempt.json", record)
    numerical_path: Path | None = None
    numerical_hash: str | None = None
    numerical_code_paths: dict[str, str] = {}
    try:
        artifact = strict_json_loads(source.read_text(encoding="utf-8"))
        if not isinstance(artifact, dict) or set(artifact) != ARTIFACT_KEYS:
            raise ValueError("promotion artifact fields do not exactly match schema")
        if artifact["schema"] != ARTIFACT_SCHEMA:
            raise ValueError("unsupported promotion artifact schema")
        relative = artifact["numerical_payload_path"]
        if not isinstance(relative, str) or not relative:
            raise ValueError("numerical_payload_path must be nonempty")
        candidate = Path(relative)
        numerical_path = candidate.resolve() if candidate.is_absolute() else (source.parent / candidate).resolve()
        if not numerical_path.is_file():
            raise ValueError("bound numerical payload does not exist")
        numerical_hash = _digest(numerical_path)
        if numerical_hash != artifact["numerical_payload_sha256"]:
            raise ValueError("bound numerical payload SHA256 mismatch")
        numerical_bytes = numerical_path.read_bytes()
        numerical = strict_json_loads(numerical_bytes.decode("utf-8"))
        parsed = validate_numerical_payload(numerical)
        _check_numerical_code_hashes(parsed, project_root)
        numerical_code_paths = parsed["code_sha256"]
        if artifact["outer_design_hash"] != parsed["outer"]["outer_design_hash"]:
            raise ValueError("artifact outer_design_hash does not match numerical design")
        if expected_design_hash is not None and expected_design_hash != artifact["outer_design_hash"]:
            raise ValueError("candidate outer identity differs from requested design")
        certificate = artifact["certificate"]
        rho = F(certificate["rho"])
        identity = verify_fine_unary_identity(
            certificate,
            expected_design=artifact["outer_design"],
            expected_rho=rho,
            numerical_payload_bytes=numerical_bytes,
            expected_numerical_payload_sha256=numerical_hash,
            float_to_exact_repair=artifact["float_to_exact_repair"],
        )
        if not all(
            identity.get(name) is True
            for name in (
                "identity_verified",
                "model_restrictions_verified",
                "numerical_payload_bound",
                "float_to_exact_repair_verified",
            )
        ):
            raise ValueError("strict identity binding rejected")
        _write_json(output / "identity_report.json", identity)
        exact = verify_fine_unary_certificate(certificate, resource_limits)
        _write_json(output / "verify_report.json", exact)
        if (
            exact.get("ok") is not True
            or exact.get("status") != "exact_rational_certificate"
            or exact.get("all_14_families_verified") is not True
            or exact.get("complete_separation") is not True
            or set(exact.get("families", {})) != EXPECTED_FAMILIES
            or F(exact["rho"]) != rho
            or F(exact["minimum_slack"]) < 0
        ):
            raise ValueError("full independent 14-family Fraction replay rejected")
        if (
            _digest(source) != artifact_hash
            or _digest(numerical_path) != numerical_hash
            or any(_digest(package / name) != digest for name, digest in verifier_hashes.items())
            or any(_digest(project_root / Path(name)) != digest for name, digest in numerical_code_paths.items())
        ):
            raise ValueError("artifact, numerical payload, or source changed during replay")
        record.update(
            status="exact_verified",
            verified_rho=str(rho),
            design_hash=artifact["outer_design_hash"],
            numerical_payload_path=str(numerical_path),
            numerical_payload_sha256=numerical_hash,
            minimum_slack=exact["minimum_slack"],
            all_14_families_verified=True,
            complete_separation=True,
            identity_report_sha256=_digest(output / "identity_report.json"),
            verify_report_sha256=_digest(output / "verify_report.json"),
        )
    except Exception as error:
        record.update(status="failed", error=repr(error), verified_rho=None)
    record["finished_utc"] = _utc_now()
    _write_json(output / "attempt.json", record)
    return record


__all__ = [
    "ARTIFACT_KEYS",
    "ARTIFACT_SCHEMA",
    "GATE_SCHEMA",
    "prepare_fine_unary_exact_artifact",
    "verify_fine_unary_artifact",
]
