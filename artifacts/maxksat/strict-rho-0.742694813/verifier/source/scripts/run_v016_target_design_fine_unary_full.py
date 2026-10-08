from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter
from typing import Any, Mapping


VERSION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VERSION_ROOT / "src"))

from maxksat_large.rational_weight_design import RationalWeightDesign  # noqa: E402
from maxksat_large.v016_fine_unary_exact import FineUnaryExactResourceLimits  # noqa: E402
from maxksat_large.v016_fine_unary_gate import (  # noqa: E402
    prepare_fine_unary_exact_artifact,
    verify_fine_unary_artifact,
)
from maxksat_large.v016_fine_unary_identity import NUMERICAL_SCHEMA, canonical_json_bytes  # noqa: E402
from maxksat_large.v016_fine_unary_large import (  # noqa: E402
    FineUnaryLargeSettings,
    check_fine_unary_witness,
    lift_group_witness,
    solve_fine_unary_upper_persistent,
)
from maxksat_large.v016_target_domain_search import canonical_hash, sha256_path, strict_json  # noqa: E402


PROJECT_ROOT = VERSION_ROOT.parents[2]
DEFAULT_CANDIDATE = VERSION_ROOT / (
    "artifacts/development/target_domain_hierarchical_lift_002/layers/p500/candidates/"
    "0003_50840a0d010b4f8ecb7e703bdedf8a058dc0b90d1751b1d13a51af855ebcd5c4.json"
)
DEFAULT_ANCHOR = PROJECT_ROOT / (
    "Workspace/versions/v014_gpu_reward_continuation/artifacts/formal/001_two_hours_0749/"
    "controller/outputs/main_qb_micro/0001_q20_b12/evaluation/certificate/certified_anchor.json"
)
DEFAULT_WARM = VERSION_ROOT / (
    "artifacts/development/fine_unary_p500_candidate_batch_001/"
    "retry_002_rank_003_historical_weight_tangent_half/numerical_payload.json"
)
DEFAULT_OUTPUT = VERSION_ROOT / "artifacts/development/target_domain_p500_fine_unary_001"
INCUMBENT = Fraction(1_484_867, 2_000_000)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _write(path: Path, value: Any, *, canonical: bool = False) -> None:
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    if canonical:
        temporary.write_bytes(canonical_json_bytes(value, newline=True))
    else:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    temporary.replace(path)


def _checked_numeric_payload(result: Mapping[str, Any], design: RationalWeightDesign, runner: Path, sources: Mapping[str, str]):
    check = result["check"]
    if not (
        result.get("ok") is True
        and result.get("status") == "complete_joint_numeric_candidate"
        and check.get("ok") is True
        and check.get("complete_separation") is True
        and check.get("all_low_order_rows_checked") is True
        and check.get("all_fine_upper_rows_covered") is True
        and check.get("all_fine_typed_rows_checked") is True
    ):
        raise ValueError("fine-unary numerical result is not complete")
    module = VERSION_ROOT / "src/maxksat_large/v016_fine_unary_large.py"
    return {
        "schema_version": NUMERICAL_SCHEMA,
        "status": "complete_fine_unary_numeric_candidate",
        "outer_design": design.to_dict(),
        "design_hash": design.canonical_hash,
        "bucket_group_map": result["bucket_group_map"],
        "witness": result["witness"],
        "check": {
            "ok": True,
            "complete_separation": True,
            "all_low_order_rows_checked": True,
            "all_high_order_rows_checked": True,
            "all_fine_upper_rows_checked": True,
            "all_fine_typed_rows_checked": True,
            "floating_fixed_witness_rho": check["rho"],
        },
        "verified_rho": None,
        "is_exact_certificate": False,
        "is_full_certificate": False,
        "code_sha256": {
            "src/maxksat_large/v016_fine_unary_large.py": sha256_path(module),
            "scripts/run_v016_target_design_fine_unary_full.py": sha256_path(runner),
        },
        "source_sha256": dict(sources),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Full fine-unary numerical and independent exact gate for one target-domain P500 design")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--anchor", type=Path, default=DEFAULT_ANCHOR)
    parser.add_argument("--warm", type=Path, default=DEFAULT_WARM)
    parser.add_argument("--expected-warm-sha256", default="3820578dec5da9dfeb59179450584571e49ff2ce5b2388c1534610aa6b355ee0")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    candidate_path = args.candidate.resolve(strict=True)
    anchor_path = args.anchor.resolve(strict=True)
    warm_path = args.warm.resolve(strict=True)
    if sha256_path(warm_path) != args.expected_warm_sha256:
        raise ValueError("warm payload byte SHA mismatch")
    candidate = strict_json(candidate_path)
    candidate_unhashed = dict(candidate)
    declared = candidate_unhashed.pop("artifact_content_sha256", None)
    if canonical_hash(candidate_unhashed) != declared:
        raise ValueError("candidate artifact content hash mismatch")
    design = RationalWeightDesign.from_dict(candidate["design"])
    if design.canonical_hash != candidate.get("design_hash") or design.num_positive_buckets != 500 or design.num_profiles != 1:
        raise ValueError("candidate design identity/domain mismatch")
    anchor = strict_json(anchor_path)
    mapping = tuple(anchor["parent_bucket_groups"])
    if len(mapping) != design.num_buckets or set(mapping) != set(range(max(mapping) + 1)):
        raise ValueError("anchor bucket group map is incompatible")
    warm_payload = strict_json(warm_path)
    if tuple(warm_payload.get("bucket_group_map", ())) != mapping:
        raise ValueError("warm cuts group map mismatch")
    warm_cuts = tuple(tuple(key) for key in warm_payload["warm_cuts"])

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    runner = Path(__file__).resolve()
    settings = FineUnaryLargeSettings(
        time_limit_sec=89.0,
        final_check_reserve_sec=10.0,
        max_rounds=32,
        max_low_rows=220_000,
        max_active_rows=650_000,
        max_group_multisets=100_000,
        max_csr_bytes=1024 * 1024**2,
        add_low_rows_per_round=32_768,
        add_upper_rows_per_round=16_384,
        partners_per_label=16,
        seed_anchor_count=4,
        low_block_size=128,
        tolerance=1e-9,
    )
    registration = {
        "schema_version": "v016-target-design-fine-unary-full-registration-v1",
        "started_utc": _utc(),
        "pid": os.getpid(),
        "candidate_path": str(candidate_path),
        "candidate_file_sha256": sha256_path(candidate_path),
        "candidate_content_sha256": declared,
        "design_hash": design.canonical_hash,
        "anchor_path": str(anchor_path),
        "anchor_file_sha256": sha256_path(anchor_path),
        "bucket_group_map_sha256": sha256(canonical_json_bytes(list(mapping), newline=False)).hexdigest(),
        "warm_path": str(warm_path),
        "warm_file_sha256": sha256_path(warm_path),
        "warm_cut_count": len(warm_cuts),
        "settings": asdict(settings),
        "strict_incumbent_rho": str(INCUMBENT),
        "scope": "development full fine-unary LP followed by independent Fraction/identity gate if numerically improving",
        "is_formal_experiment": False,
    }
    registration["artifact_content_sha256"] = canonical_hash(registration)
    _write(output / "registration.json", registration)
    lease = {"status": "running", "pid": os.getpid(), "started_utc": registration["started_utc"], "design_hash": design.canonical_hash}
    _write(output / "run_lease.json", lease)
    print(json.dumps({"event": "fine_unary_started", "pid": os.getpid(), "design_hash": design.canonical_hash,
                      "warm_cuts": len(warm_cuts), "output": str(output)}), flush=True)

    initial = None
    initial_audit: dict[str, Any] = {"attempted": True, "used": False}
    try:
        lifted = lift_group_witness(
            design,
            mapping,
            rho=float(Fraction(anchor["verified_rho"])),
            lambdas=anchor["lambdas_rational"],
            pair_tables=anchor["pair_tables"],
        )
        precheck = check_fine_unary_witness(
            design, mapping, lifted, tolerance=1e-9, low_block_size=128, max_group_multisets=100_000
        )
        initial_audit["complete_precheck"] = precheck
        if precheck.get("ok") is True:
            initial = lifted
            initial_audit["used"] = True
    except Exception as error:
        initial_audit["error"] = repr(error)
    _write(output / "initial_witness_audit.json", initial_audit)

    started = perf_counter()
    result = solve_fine_unary_upper_persistent(
        design,
        mapping,
        settings=settings,
        warm_cuts=warm_cuts,
        initial_witness=initial,
        initial_witness_provenance=None if initial is None else {
            "source_anchor_path": str(anchor_path),
            "source_anchor_file_sha256": sha256_path(anchor_path),
            "complete_semantic_precheck": True,
            "trusted_as_final_result": False,
        },
    )
    result["source_sha256"].update({
        "target_candidate_file": sha256_path(candidate_path),
        "strict_anchor_file": sha256_path(anchor_path),
        "warm_payload_file": sha256_path(warm_path),
        "runner": sha256_path(runner),
    })
    raw_path = output / "fine_unary_raw.json"
    _write(raw_path, result)
    numerical_path = exact_path = None
    gate = preparation = None
    checked_rho = None if result.get("check") is None else result["check"].get("rho")
    sources = {
        "target_candidate_file": sha256_path(candidate_path),
        "strict_anchor_file": sha256_path(anchor_path),
        "warm_payload_file": sha256_path(warm_path),
        "fine_unary_raw_file": sha256_path(raw_path),
    }
    if result.get("ok") is True:
        numerical = _checked_numeric_payload(result, design, runner, sources)
        numerical_path = output / "numerical_payload.json"
        _write(numerical_path, numerical, canonical=True)
        checked = Fraction.from_float(float(numerical["check"]["floating_fixed_witness_rho"]))
        scale = 10**9
        target = Fraction(math.floor(checked * scale) - 2, scale)
        if target > INCUMBENT:
            exact_path = output / "exact_candidate.json"
            limits = FineUnaryExactResourceLimits(max_seconds=600.0)
            preparation = prepare_fine_unary_exact_artifact(
                numerical_path,
                exact_path,
                target_rho=str(target),
                repair_padding="1/1000000000000",
                resource_limits=limits,
            )
            gate = verify_fine_unary_artifact(
                exact_path,
                output / "exact_gate",
                design.canonical_hash,
                resource_limits=limits,
            )
    summary = {
        "schema_version": "v016-target-design-fine-unary-full-summary-v1",
        "finished_utc": _utc(),
        "elapsed_seconds": perf_counter() - started,
        "design_hash": design.canonical_hash,
        "numerical_status": result.get("status"),
        "numerical_ok": result.get("ok"),
        "numerical_rho": result.get("rho"),
        "checked_rho": checked_rho,
        "complete_separation": result.get("complete_separation"),
        "all_low_order_rows_checked": result.get("all_low_order_rows_checked"),
        "all_fine_upper_rows_covered": result.get("all_fine_upper_rows_covered"),
        "all_fine_typed_rows_checked": result.get("all_fine_typed_rows_checked"),
        "round_count": len(result.get("rounds", ())),
        "raw_path": str(raw_path),
        "raw_file_sha256": sha256_path(raw_path),
        "numerical_payload_path": None if numerical_path is None else str(numerical_path),
        "numerical_payload_sha256": None if numerical_path is None else sha256_path(numerical_path),
        "exact_artifact_path": None if exact_path is None else str(exact_path),
        "exact_artifact_sha256": None if exact_path is None else sha256_path(exact_path),
        "exact_preparation": preparation,
        "exact_gate": gate,
        "verified_rho": None if not gate or gate.get("status") != "exact_verified" else gate["verified_rho"],
        "strict_improvement": bool(gate and gate.get("status") == "exact_verified" and Fraction(gate["verified_rho"]) > INCUMBENT),
        "incumbent_rho": str(INCUMBENT),
        "is_full_certificate": bool(gate and gate.get("status") == "exact_verified"),
    }
    summary["artifact_content_sha256"] = canonical_hash(summary)
    summary_path = output / "summary.json"
    _write(summary_path, summary)
    lease.update(status="completed", finished_utc=_utc(), numerical_status=result.get("status"),
                 numerical_ok=result.get("ok"), verified_rho=summary["verified_rho"])
    _write(output / "run_lease.json", lease)
    _write(output / "SHA256SUMS.json", {
        path.name: sha256_path(path)
        for path in sorted(output.rglob("*.json"))
        if path.name != "SHA256SUMS.json"
    })
    print(json.dumps({"event": "fine_unary_finished", "summary_path": str(summary_path),
                      "summary_sha256": sha256_path(summary_path), **summary}), flush=True)
    return 0 if result.get("ok") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
