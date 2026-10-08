#!/usr/bin/env python3
"""Replay the bundled v016 fine-unary certificate with exact arithmetic.

This script deliberately ignores the historical absolute path stored in
``exact_candidate.json``.  It binds that immutable candidate to the copy of
``numerical_payload.json`` carried by the bundle through SHA-256, validates
the numerical-to-exact identity, and then repeats every Fraction-based
certificate row check using only verifier sources carried by the bundle.

Exit status is 0 only after all checks and both archived-report comparisons
pass.  Any rejection, resource-limit result, or unexpected exception exits
nonzero and leaves a fail-closed ``FULL_EXACT_REPLAY.json`` record.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import importlib.util
import json
from math import isfinite
from pathlib import Path, PurePosixPath
import sys
from time import perf_counter
import types
from typing import Any, Mapping


TARGET_RHO = Fraction(742_694_813, 1_000_000_000)
TARGET_RHO_TEXT = "742694813/1000000000"
TARGET_RHO_DECIMAL = "0.742694813"
RESULT_SCHEMA = "maxksat-strict-certificate-full-exact-replay-v1"
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
IDENTITY_FLAGS = (
    "identity_verified",
    "model_restrictions_verified",
    "numerical_payload_bound",
    "float_to_exact_repair_verified",
)
SOURCE_NAMES = (
    "v016_fine_unary_exact.py",
    "v016_fine_unary_identity.py",
    "v016_fine_unary_gate.py",
)


class ReplayRejected(RuntimeError):
    """Raised whenever a fail-closed replay condition is not met."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(value: Any) -> bytes:
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


def _strict_json_loads(data: bytes, *, label: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReplayRejected(f"{label} is not UTF-8 JSON") from error

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ReplayRejected(f"duplicate JSON field in {label}: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ReplayRejected(f"nonfinite JSON constant in {label}: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=invalid_constant,
        )
    except json.JSONDecodeError as error:
        raise ReplayRejected(f"invalid JSON document: {label}") from error


def _write_record(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical_json_bytes(value))
    temporary.replace(path)


def _digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReplayRejected(message)


def _sha_token(value: Any, *, label: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{label} is not a lowercase SHA-256 digest",
    )
    return value


def _resolve_file(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise ReplayRejected(f"required bundle file is missing: {relative}") from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ReplayRejected(f"bundle file escapes bundle root: {relative}") from error
    _require(resolved.is_file(), f"required bundle path is not a file: {relative}")
    return resolved


def _fraction(value: Any, *, label: str) -> Fraction:
    _require(not isinstance(value, (bool, float)), f"{label} is not exact")
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise ReplayRejected(f"invalid exact rational at {label}") from error


def _positive_seconds(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as error:
        raise argparse.ArgumentTypeError("max seconds must be numeric") from error
    if not isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("max seconds must be finite and positive")
    return value


def _load_module(name: str, path: Path) -> types.ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ReplayRejected(f"could not construct module loader for {path.name}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    try:
        specification.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _load_bundled_verifier(
    source_dir: Path,
    verifier_source_hashes: Mapping[str, Any],
) -> tuple[types.ModuleType, types.ModuleType, dict[str, str]]:
    _require(
        isinstance(verifier_source_hashes, dict)
        and set(verifier_source_hashes) == set(SOURCE_NAMES),
        "archived verifier-source hash set is incomplete or has extra entries",
    )
    actual_hashes: dict[str, str] = {}
    source_paths: dict[str, Path] = {}
    for name in SOURCE_NAMES:
        path = _resolve_file(source_dir, name)
        source_paths[name] = path
        actual_hashes[name] = _digest(path)
        _require(
            actual_hashes[name]
            == _sha_token(verifier_source_hashes[name], label=f"verifier source {name}"),
            f"bundled verifier source differs from archived gate: {name}",
        )

    package_name = "_bundled_maxksat_large_" + actual_hashes[
        "v016_fine_unary_exact.py"
    ][:12]
    _require(package_name not in sys.modules, "bundled verifier package already loaded")
    package = types.ModuleType(package_name)
    package.__file__ = str(source_dir / "__init__.py")
    package.__package__ = package_name
    package.__path__ = [str(source_dir)]
    sys.modules[package_name] = package
    try:
        exact = _load_module(
            f"{package_name}.v016_fine_unary_exact",
            source_paths["v016_fine_unary_exact.py"],
        )
        identity = _load_module(
            f"{package_name}.v016_fine_unary_identity",
            source_paths["v016_fine_unary_identity.py"],
        )
    except Exception:
        for loaded_name in tuple(sys.modules):
            if loaded_name == package_name or loaded_name.startswith(package_name + "."):
                sys.modules.pop(loaded_name, None)
        raise
    return exact, identity, actual_hashes


def _verify_numerical_code_hashes(
    source_root: Path,
    declared: Mapping[str, Any],
) -> dict[str, str]:
    _require(isinstance(declared, dict) and bool(declared), "empty numerical code hash map")
    actual: dict[str, str] = {}
    for relative, expected in declared.items():
        _require(isinstance(relative, str) and relative, "invalid numerical code path")
        pure = PurePosixPath(relative)
        _require(
            not pure.is_absolute()
            and ".." not in pure.parts
            and pure.suffix == ".py"
            and pure.parts[0] in {"src", "scripts"},
            f"unsafe numerical code path: {relative}",
        )
        path = _resolve_file(source_root, relative)
        actual[relative] = _digest(path)
        _require(
            actual[relative] == _sha_token(expected, label=f"code_sha256.{relative}"),
            f"bundled numerical source SHA-256 mismatch: {relative}",
        )
    return actual


def _without_elapsed_seconds(report: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(report)
    normalized.pop("elapsed_seconds", None)
    return normalized


def _input_paths(bundle_root: Path) -> dict[str, Path]:
    paths = {
        "exact_candidate": _resolve_file(
            bundle_root, "original/certificate/exact_candidate.json"
        ),
        "numerical_payload": _resolve_file(
            bundle_root, "original/certificate/numerical_payload.json"
        ),
        "archived_attempt": _resolve_file(
            bundle_root, "original/certificate/exact_gate/attempt.json"
        ),
        "archived_identity_report": _resolve_file(
            bundle_root, "original/certificate/exact_gate/identity_report.json"
        ),
        "archived_verify_report": _resolve_file(
            bundle_root, "original/certificate/exact_gate/verify_report.json"
        ),
    }
    return paths


def _run_replay(
    bundle_root: Path,
    output_record: Path,
    max_seconds: float,
    record: dict[str, Any],
) -> None:
    paths = _input_paths(bundle_root)
    input_bytes = {name: path.read_bytes() for name, path in paths.items()}
    input_hashes = {name: _digest_bytes(data) for name, data in input_bytes.items()}
    record["input_sha256"] = input_hashes

    candidate = _strict_json_loads(
        input_bytes["exact_candidate"], label="exact_candidate.json"
    )
    attempt = _strict_json_loads(
        input_bytes["archived_attempt"], label="exact_gate/attempt.json"
    )
    archived_identity = _strict_json_loads(
        input_bytes["archived_identity_report"],
        label="exact_gate/identity_report.json",
    )
    archived_verify = _strict_json_loads(
        input_bytes["archived_verify_report"],
        label="exact_gate/verify_report.json",
    )
    numerical = _strict_json_loads(
        input_bytes["numerical_payload"], label="numerical_payload.json"
    )

    _require(
        isinstance(candidate, dict) and set(candidate) == ARTIFACT_KEYS,
        "exact candidate fields do not exactly match the artifact schema",
    )
    _require(candidate["schema"] == ARTIFACT_SCHEMA, "unsupported exact-candidate schema")
    _require(
        isinstance(candidate["numerical_payload_path"], str)
        and bool(candidate["numerical_payload_path"]),
        "archived numerical_payload_path is empty",
    )
    numerical_sha = _sha_token(
        candidate["numerical_payload_sha256"], label="numerical_payload_sha256"
    )
    _require(
        input_hashes["numerical_payload"] == numerical_sha,
        "bundled numerical payload differs from the candidate-bound SHA-256",
    )
    _require(
        isinstance(candidate["certificate"], dict), "candidate certificate is not an object"
    )
    rho = _fraction(candidate["certificate"].get("rho"), label="certificate.rho")
    _require(rho == TARGET_RHO, "certificate rho is not 742694813/1000000000")

    _require(isinstance(attempt, dict), "archived attempt report is not an object")
    _require(attempt.get("status") == "exact_verified", "archived gate did not pass")
    _require(
        _fraction(attempt.get("verified_rho"), label="attempt.verified_rho")
        == TARGET_RHO,
        "archived gate rho differs from the fixed target",
    )
    _require(
        attempt.get("artifact_sha256") == input_hashes["exact_candidate"],
        "archived gate does not bind the bundled exact candidate",
    )
    _require(
        attempt.get("numerical_payload_sha256") == numerical_sha,
        "archived gate does not bind the bundled numerical payload",
    )
    _require(
        attempt.get("identity_report_sha256")
        == input_hashes["archived_identity_report"],
        "archived attempt does not bind identity_report.json",
    )
    _require(
        attempt.get("verify_report_sha256") == input_hashes["archived_verify_report"],
        "archived attempt does not bind verify_report.json",
    )
    _require(
        attempt.get("all_14_families_verified") is True
        and attempt.get("complete_separation") is True,
        "archived attempt lacks complete 14-family separation",
    )

    source_root = _resolve_directory(bundle_root, "verifier/source")
    package_dir = _resolve_directory(source_root, "src/maxksat_large")
    exact_module, identity_module, verifier_hashes = _load_bundled_verifier(
        package_dir,
        attempt.get("verifier_source_sha256"),
    )
    record["bundled_verifier_source_sha256"] = verifier_hashes

    # Parse through the bundled strict validator, then separately bind each
    # numerical code hash to the source copy carried in this bundle.
    numerical_via_bundle = identity_module.strict_json_loads(
        input_bytes["numerical_payload"].decode("utf-8")
    )
    parsed = identity_module.validate_numerical_payload(numerical_via_bundle)
    _require(
        numerical_via_bundle == numerical,
        "local and bundled strict JSON decoders disagree on numerical payload",
    )
    _require(
        candidate["outer_design"] == numerical["outer_design"],
        "candidate and numerical outer designs differ",
    )
    _require(
        candidate["outer_design_hash"] == parsed["outer"]["outer_design_hash"],
        "candidate outer-design hash differs from validated numerical design",
    )
    code_hashes = _verify_numerical_code_hashes(source_root, parsed["code_sha256"])
    record["bundled_numerical_code_sha256"] = code_hashes
    record["numerical_payload_validation"] = {
        "passed": True,
        "num_buckets": parsed["outer"]["num_buckets"],
        "positive_bucket_count": parsed["outer"]["positive_bucket_count"],
        "checked_floating_rho": repr(parsed["checked_rho"]),
        "bucket_group_count": max(parsed["mapping"]) + 1,
    }
    record["status"] = "running_exact_fraction_replay"
    _write_record(output_record, record)

    identity_report = identity_module.verify_fine_unary_identity(
        candidate["certificate"],
        expected_design=candidate["outer_design"],
        expected_rho=TARGET_RHO,
        numerical_payload_bytes=input_bytes["numerical_payload"],
        expected_numerical_payload_sha256=numerical_sha,
        float_to_exact_repair=candidate["float_to_exact_repair"],
    )
    record["generated_identity_report"] = identity_report
    _require(
        all(identity_report.get(name) is True for name in IDENTITY_FLAGS),
        "generated identity report rejected an exact binding condition",
    )
    _require(
        _fraction(identity_report.get("rho_bound"), label="identity.rho_bound")
        == TARGET_RHO,
        "generated identity report has the wrong rho",
    )
    _require(
        identity_report == archived_identity,
        "generated identity report differs from the archived identity report",
    )

    limits = exact_module.FineUnaryExactResourceLimits(
        max_num_buckets=2_048,
        max_low_label_pairs=2_100_000,
        max_group_multisets=2_000_000,
        max_pair_table_entries=20_000,
        max_hull_states=8_192,
        max_upper_transitions=120_000_000,
        max_seconds=max_seconds,
    )
    verify_report = exact_module.verify_fine_unary_certificate(
        candidate["certificate"], limits
    )
    record["generated_verify_report"] = verify_report
    _write_record(output_record, record)
    _require(verify_report.get("ok") is True, "Fraction certificate replay did not pass")
    _require(
        verify_report.get("status") == "exact_rational_certificate",
        "Fraction replay did not return exact_rational_certificate",
    )
    _require(
        verify_report.get("all_14_families_verified") is True
        and verify_report.get("all_low_order_rows_checked") is True
        and verify_report.get("all_high_order_rows_checked") is True
        and verify_report.get("complete_separation") is True,
        "Fraction replay did not cover every required row family",
    )
    _require(
        set(verify_report.get("families", {})) == set(exact_module.EXPECTED_FAMILIES),
        "Fraction replay family set is incomplete or has extra entries",
    )
    _require(
        _fraction(verify_report.get("rho"), label="verify.rho") == TARGET_RHO,
        "Fraction replay returned the wrong rho",
    )
    _require(
        _fraction(verify_report.get("minimum_slack"), label="verify.minimum_slack")
        >= 0,
        "Fraction replay found negative minimum slack",
    )
    _require(
        isinstance(archived_verify, dict)
        and _without_elapsed_seconds(verify_report)
        == _without_elapsed_seconds(archived_verify),
        "generated verify report differs from archived report beyond elapsed_seconds",
    )

    # Fail if any proof input or verifier source changed while the expensive
    # replay was running.
    for name, path in paths.items():
        _require(_digest(path) == input_hashes[name], f"input changed during replay: {name}")
    for name, digest in verifier_hashes.items():
        _require(
            _digest(package_dir / name) == digest,
            f"verifier source changed during replay: {name}",
        )
    for relative, digest in code_hashes.items():
        _require(
            _digest(source_root.joinpath(*PurePosixPath(relative).parts)) == digest,
            f"numerical code source changed during replay: {relative}",
        )

    record["archived_report_comparison"] = {
        "identity_report_exact_match": True,
        "verify_report_exact_match_excluding_elapsed_seconds": True,
        "ignored_verify_fields": ["elapsed_seconds"],
        "archived_elapsed_seconds": archived_verify.get("elapsed_seconds"),
        "replay_elapsed_seconds": verify_report.get("elapsed_seconds"),
    }
    record["proof_result"] = {
        "verified_rho": TARGET_RHO_TEXT,
        "verified_rho_decimal": TARGET_RHO_DECIMAL,
        "minimum_slack": verify_report["minimum_slack"],
        "all_14_families_verified": True,
        "all_low_order_rows_checked": True,
        "all_high_order_rows_checked": True,
        "complete_separation": True,
        "identity_verified": True,
        "numerical_payload_bound": True,
        "historical_absolute_payload_path_used": False,
    }


def _resolve_directory(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise ReplayRejected(f"required bundle directory is missing: {relative}") from error
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ReplayRejected(f"bundle directory escapes bundle root: {relative}") from error
    _require(resolved.is_dir(), f"required bundle path is not a directory: {relative}")
    return resolved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the bundled rho=0.742694813 certificate with independent "
            "Fraction and identity verification."
        )
    )
    parser.add_argument(
        "--bundle-root",
        required=True,
        type=Path,
        help="root of the extracted certificate bundle",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "new/empty replay output directory; defaults to "
            "<bundle-root>/validation/full_exact_replay"
        ),
    )
    parser.add_argument(
        "--max-seconds",
        type=_positive_seconds,
        default=1_200.0,
        help="exact verifier deadline in seconds (default: 1200)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        bundle_root = arguments.bundle_root.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        print(f"bundle root does not exist: {error}", file=sys.stderr)
        return 1
    if not bundle_root.is_dir():
        print("bundle root is not a directory", file=sys.stderr)
        return 1

    output_dir = (
        arguments.output_dir
        if arguments.output_dir is not None
        else bundle_root / "validation" / "full_exact_replay"
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_record = output_dir / "FULL_EXACT_REPLAY.json"
    if output_record.exists() or output_record.with_name(output_record.name + ".tmp").exists():
        print(
            f"refusing to overwrite an existing replay record: {output_record}",
            file=sys.stderr,
        )
        return 1

    started = perf_counter()
    record: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "status": "running",
        "success": False,
        "started_utc": _utc_now(),
        "finished_utc": None,
        "elapsed_seconds": None,
        "target_rho": TARGET_RHO_TEXT,
        "target_rho_decimal": TARGET_RHO_DECIMAL,
        "resource_limits": {
            "max_num_buckets": 2_048,
            "max_low_label_pairs": 2_100_000,
            "max_group_multisets": 2_000_000,
            "max_pair_table_entries": 20_000,
            "max_hull_states": 8_192,
            "max_upper_transitions": 120_000_000,
            "max_seconds": arguments.max_seconds,
        },
        "bundle_paths": {
            "exact_candidate": "original/certificate/exact_candidate.json",
            "numerical_payload": "original/certificate/numerical_payload.json",
            "archived_attempt": "original/certificate/exact_gate/attempt.json",
            "archived_identity_report": (
                "original/certificate/exact_gate/identity_report.json"
            ),
            "archived_verify_report": (
                "original/certificate/exact_gate/verify_report.json"
            ),
            "verifier_source": "verifier/source",
        },
    }
    _write_record(output_record, record)
    try:
        _run_replay(
            bundle_root=bundle_root,
            output_record=output_record,
            max_seconds=arguments.max_seconds,
            record=record,
        )
        record["status"] = "exact_verified"
        record["success"] = True
    except Exception as error:
        record["status"] = "failed"
        record["success"] = False
        record["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
    record["finished_utc"] = _utc_now()
    record["elapsed_seconds"] = perf_counter() - started
    _write_record(output_record, record)
    summary = {
        "status": record["status"],
        "success": record["success"],
        "verified_rho": (
            record.get("proof_result", {}).get("verified_rho")
            if record["success"]
            else None
        ),
        "result": str(output_record),
    }
    print(_canonical_json_bytes(summary).decode("utf-8"), end="")
    return 0 if record["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
