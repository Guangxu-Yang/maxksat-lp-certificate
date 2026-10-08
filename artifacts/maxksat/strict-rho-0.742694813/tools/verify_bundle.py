#!/usr/bin/env python3
"""Fast, offline integrity and semantics check for the rho=0.742694813 bundle.

This verifier deliberately does *not* recompute the expensive Fraction certificate.
It authenticates the archived result, its original SHA-256 chain, the bound verifier
sources and the critical semantic claims.  Use the separately supplied replay tool
when an independent full mathematical recomputation is required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


RHO = "742694813/1000000000"
RHO_DECIMAL = "0.742694813"
DESIGN_HASH = "50840a0d010b4f8ecb7e703bdedf8a058dc0b90d1751b1d13a51af855ebcd5c4"
NUMERICAL_PAYLOAD_SHA256 = (
    "ff19fcb1f6b7655a286d652e681535e3d848601822513fa28ffd903ddcbf9740"
)

# These are intentionally compiled into the verifier.  They are the small trust
# root needed to prevent a rewritten bundle manifest from authenticating a
# different certificate.
TRUST_ANCHORS = {
    "original/promotion/promotion.json": (
        "8475f73d5a2edcdbace963627c1ffef11bb5c3895384b319309b3cae7db10741"
    ),
    "original/promotion/SHA256SUMS.json": (
        "db314bb88bec3d819f3bf62568582d6bac84c8f8da692dfa2cde84a32ccae0e2"
    ),
    "original/certificate/exact_candidate.json": (
        "84ad3c58240ee3677d733a625c7abb8097abf74975a359b40d3c9737b03e342b"
    ),
    "original/certificate/exact_gate/verify_report.json": (
        "32e25248fbd6159ca04f4927bbbf4068b1664e513b70c790f4e99ad9532538a0"
    ),
    "original/certificate/exact_gate/identity_report.json": (
        "9477bd303987f1ad86ad79913e53a3a060d466dc54670d7e46c50f1c30a16ebd"
    ),
    "original/certificate/SHA256SUMS.json": (
        "90dcbdeb54d29731bf39c0ee9e6c75b1b81c5c029edd75e59c7faebf039e6132"
    ),
}

# The independent identity report names these historical inputs by hash.  The
# bundle gives them stable descriptive paths; pin both the path and bytes so an
# unrelated duplicate with the same role cannot silently replace one.
DIRECT_INPUT_ANCHORS = {
    "provenance/lineage/v014_anchor/certified_anchor.json": (
        "f0ed94a4de5a47a610d475ef8d8beb57155bcca8727fc0c9d99e386169d81937"
    ),
    "provenance/lineage/v016_fine_unary/warm_payload.json": (
        "3820578dec5da9dfeb59179450584571e49ff2ce5b2388c1534610aa6b355ee0"
    ),
    "provenance/lineage/v016_hierarchical_lift/overall_summary.json": (
        "8fd70cb76aa5123c1bbee8c9a87eb3dbf3fd5440eec247e61836214362d2a5ed"
    ),
    "provenance/lineage/v016_hierarchical_lift/p500_source_candidate.json": (
        "b070e1d2c07c593db19ce5fa9d117226f8ea75acd5e7a57bbf096c4880f28e57"
    ),
    "provenance/lineage/v016_hierarchical_lift/p500_summary.json": (
        "519e37af172aa88dae008595159a8f6b73bcf90556f7aea8f3047d9ffe140880"
    ),
    "provenance/logs/051_v016_P500严格基线提升与低阶瓶颈.md": (
        "af833d4e29076fb85a06b7c654f391de2a32c931db816cdb463ce0008585853a"
    ),
}

PROJECT_STATE_ANCHORS = {
    "provenance/project_state/PRESERVATION_INDEX.json": (
        "71cc97875209cb462e49979fe6616da28cb9ffa15e95c95a40fd168fbda51b6b"
    ),
    "provenance/project_state/STABLE_RELEASE.json": (
        "a11edf3be1c93ad5659ecff8e7034ea1acc265243e740c3c497e89ff8c1d54ae"
    ),
}

EXPECTED_FAMILIES = {
    "d1_satisfied",
    "d1_unsatisfied",
    "d2_satisfied",
    "d2_unsatisfied",
    "d3_satisfied",
    "d3_unsatisfied",
    "d3_upper",
    "d4_satisfied",
    "d4_unsatisfied",
    "d4_upper",
    "d5_satisfied",
    "d5_unsatisfied",
    "d5_upper",
    "long_floor",
}

CERTIFICATE_INNER_FILES = {
    "attempt.json": "original/certificate/exact_gate/attempt.json",
    "exact_candidate.json": "original/certificate/exact_candidate.json",
    "fine_unary_raw.json": "original/certificate/fine_unary_raw.json",
    "identity_report.json": "original/certificate/exact_gate/identity_report.json",
    "initial_witness_audit.json": "original/certificate/initial_witness_audit.json",
    "numerical_payload.json": "original/certificate/numerical_payload.json",
    "registration.json": "original/certificate/registration.json",
    "run_lease.json": "original/certificate/run_lease.json",
    "summary.json": "original/certificate/summary.json",
    "verify_report.json": "original/certificate/exact_gate/verify_report.json",
}

PROMOTION_CERTIFICATE_FIELDS = {
    "registration_sha256": "registration.json",
    "raw_numerical_solver_result_sha256": "fine_unary_raw.json",
    "canonical_numerical_payload_sha256": "numerical_payload.json",
    "exact_candidate_artifact_sha256": "exact_candidate.json",
    "exact_gate_attempt_sha256": "attempt.json",
    "identity_report_sha256": "identity_report.json",
    "verification_report_sha256": "verify_report.json",
    "certificate_summary_sha256": "summary.json",
}

SOURCE_BINDINGS = {
    "numerical_runner_sha256": "scripts/run_v016_target_design_fine_unary_full.py",
    "fine_unary_large_core_sha256": "src/maxksat_large/v016_fine_unary_large.py",
    "exact_verifier_sha256": "src/maxksat_large/v016_fine_unary_exact.py",
    "identity_verifier_sha256": "src/maxksat_large/v016_fine_unary_identity.py",
    "gate_runner_sha256": "src/maxksat_large/v016_fine_unary_gate.py",
}

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_BAD_CHARS = set('<>:"\\|?*')
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class VerificationError(RuntimeError):
    """An input defect that makes further structural verification unsafe."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {token}")


def load_json_strict(path: Path) -> Any:
    """Load RFC-style JSON, rejecting duplicate names, NaN and Infinity."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise VerificationError(f"cannot read {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VerificationError(f"JSON is not UTF-8: {path}: {exc}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise VerificationError(f"invalid strict JSON in {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _is_reparse(st: os.stat_result) -> bool:
    return bool(getattr(st, "st_file_attributes", 0) & REPARSE_ATTRIBUTE)


def _validate_portable_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise VerificationError("manifest path must be a non-empty string")
    if "\\" in value or "\x00" in value or any(ord(ch) < 32 for ch in value):
        raise VerificationError(f"unsafe manifest path: {value!r}")
    posix = PurePosixPath(value)
    if posix.is_absolute() or posix.as_posix() != value:
        raise VerificationError(f"manifest path is not normalized relative POSIX: {value!r}")
    if any(part in {"", ".", ".."} for part in posix.parts):
        raise VerificationError(f"unsafe manifest path component: {value!r}")
    for part in posix.parts:
        if part.endswith((" ", ".")) or any(ch in WINDOWS_BAD_CHARS for ch in part):
            raise VerificationError(f"path is unsafe on Windows: {value!r}")
        stem = part.split(".", 1)[0].upper()
        if stem in WINDOWS_RESERVED:
            raise VerificationError(f"reserved Windows path component: {value!r}")
    return value


def _scan_bundle(root: Path) -> tuple[dict[str, Path], list[str]]:
    """Enumerate without following links and reject every reparse/special node."""

    issues: list[str] = []
    files: dict[str, Path] = {}
    try:
        root_stat = root.stat(follow_symlinks=False)
    except OSError as exc:
        raise VerificationError(f"cannot stat bundle root: {exc}") from exc
    if root.is_symlink() or _is_reparse(root_stat):
        raise VerificationError("bundle root itself may not be a symlink/reparse point")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise VerificationError("bundle root is not a directory")

    def visit(directory: Path, parts: tuple[str, ...]) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            issues.append(f"cannot enumerate {directory}: {exc}")
            return
        for entry in entries:
            rel_parts = (*parts, entry.name)
            rel = PurePosixPath(*rel_parts).as_posix()
            try:
                _validate_portable_relative_path(rel)
                st = entry.stat(follow_symlinks=False)
            except (OSError, VerificationError) as exc:
                issues.append(f"unsafe/unreadable entry {rel}: {exc}")
                continue
            if entry.is_symlink() or _is_reparse(st):
                issues.append(f"symlink/reparse point forbidden: {rel}")
            elif stat.S_ISDIR(st.st_mode):
                visit(Path(entry.path), rel_parts)
            elif stat.S_ISREG(st.st_mode):
                files[rel] = Path(entry.path)
            else:
                issues.append(f"non-regular filesystem node forbidden: {rel}")

    visit(root, ())
    folded: dict[str, str] = {}
    for rel in files:
        key = rel.casefold()
        if key in folded and folded[key] != rel:
            issues.append(f"case-colliding paths: {folded[key]!r} and {rel!r}")
        folded[key] = rel
    return files, issues


def _parse_manifest_files(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_files = manifest.get("files")
    parsed: dict[str, dict[str, Any]] = {}
    if isinstance(raw_files, list):
        iterator: Iterable[tuple[Any, Any]] = (
            (entry.get("path") if isinstance(entry, dict) else None, entry)
            for entry in raw_files
        )
    elif isinstance(raw_files, dict):
        iterator = raw_files.items()
    else:
        raise VerificationError("BUNDLE_MANIFEST.json.files must be a list or object")

    casefolded: dict[str, str] = {}
    for raw_path, raw_entry in iterator:
        rel = _validate_portable_relative_path(raw_path)
        if rel == "BUNDLE_MANIFEST.json":
            raise VerificationError("manifest cannot recursively list itself")
        if rel in parsed:
            raise VerificationError(f"duplicate manifest file path: {rel}")
        folded = rel.casefold()
        if folded in casefolded:
            raise VerificationError(
                f"case-colliding manifest paths: {casefolded[folded]!r} and {rel!r}"
            )
        casefolded[folded] = rel

        if isinstance(raw_entry, str):
            sha = raw_entry
            size = None
            role = None
        elif isinstance(raw_entry, dict):
            sha = raw_entry.get("sha256")
            size = raw_entry.get("size_bytes", raw_entry.get("size"))
            role = raw_entry.get("role")
        else:
            raise VerificationError(f"invalid manifest entry for {rel}")
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            raise VerificationError(f"invalid lowercase SHA-256 for {rel}")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise VerificationError(f"missing/invalid byte size for {rel}")
        if role is not None and not isinstance(role, str):
            raise VerificationError(f"invalid role for {rel}")
        parsed[rel] = {"sha256": sha, "size_bytes": size, "role": role}
    if not parsed:
        raise VerificationError("bundle manifest contains no files")
    return parsed


class BundleVerifier:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks: list[str] = []
        self.files: dict[str, Path] = {}
        self.file_hashes: dict[str, str] = {}
        self.hash_to_paths: dict[str, list[str]] = {}
        self.json_cache: dict[str, Any] = {}
        self.manifest: dict[str, Any] = {}
        self.manifest_files: dict[str, dict[str, Any]] = {}

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)

    def check(self, condition: bool, name: str, failure: str | None = None) -> None:
        if condition:
            self.checks.append(name)
        else:
            self.errors.append(failure or name)

    def json_at(self, rel: str) -> Any:
        if rel not in self.json_cache:
            path = self.files.get(rel)
            if path is None:
                raise VerificationError(f"required JSON file missing: {rel}")
            self.json_cache[rel] = load_json_strict(path)
        return self.json_cache[rel]

    def actual_sha(self, rel: str) -> str | None:
        return self.file_hashes.get(rel)

    def paths_with_sha(self, sha: str, prefix: str | None = None) -> list[str]:
        paths = self.hash_to_paths.get(sha, [])
        if prefix is None:
            return list(paths)
        return [path for path in paths if path.startswith(prefix)]

    def verify_structure_and_manifest(self) -> None:
        self.files, scan_issues = _scan_bundle(self.root)
        self.errors.extend(scan_issues)
        manifest_path = self.files.get("BUNDLE_MANIFEST.json")
        if manifest_path is None:
            raise VerificationError("BUNDLE_MANIFEST.json is missing at bundle root")
        raw_manifest = load_json_strict(manifest_path)
        if not isinstance(raw_manifest, dict):
            raise VerificationError("BUNDLE_MANIFEST.json root must be an object")
        self.manifest = raw_manifest
        self.check(
            raw_manifest.get("schema") == "maxksat.strict_certificate_bundle_manifest.v1",
            "bundle_manifest_schema",
            "unexpected bundle manifest schema",
        )
        self.manifest_files = _parse_manifest_files(raw_manifest)

        actual_payload = set(self.files) - {"BUNDLE_MANIFEST.json"}
        declared = set(self.manifest_files)
        missing = sorted(declared - actual_payload)
        extra = sorted(actual_payload - declared)
        self.check(
            not missing and not extra,
            "manifest_exact_file_closure",
            f"manifest file closure mismatch; missing={missing}, extra={extra}",
        )

        for rel in sorted(declared & actual_payload):
            path = self.files[rel]
            try:
                size = path.stat(follow_symlinks=False).st_size
                digest = sha256_file(path)
            except OSError as exc:
                self.errors.append(f"cannot hash {rel}: {exc}")
                continue
            expected = self.manifest_files[rel]
            self.require(size == expected["size_bytes"], f"size mismatch: {rel}")
            self.require(digest == expected["sha256"], f"SHA-256 mismatch: {rel}")
            self.file_hashes[rel] = digest
            self.hash_to_paths.setdefault(digest, []).append(rel)

        # Every JSON payload is strict JSON, not merely the handful used below.
        for rel in sorted(path for path in declared if path.lower().endswith(".json")):
            try:
                self.json_at(rel)
            except VerificationError as exc:
                self.errors.append(str(exc))
        self.check(
            all(self.actual_sha(path) == digest for path, digest in TRUST_ANCHORS.items()),
            "six_compiled_trust_anchors",
            "one or more of the six compiled trust anchors is missing or changed",
        )
        self.check(
            all(
                self.actual_sha(path) == digest
                for path, digest in DIRECT_INPUT_ANCHORS.items()
            ),
            "six_direct_input_anchors",
            "one or more of the six fixed historical direct inputs is missing or changed",
        )
        self.check(
            all(
                self.actual_sha(path) == digest
                for path, digest in PROJECT_STATE_ANCHORS.items()
            ),
            "project_state_snapshot_anchors",
            "one or more project-state snapshots is missing or changed",
        )
        self.check(
            not missing and not extra and not scan_issues,
            "safe_regular_file_tree",
            "bundle tree contains unsafe, unreadable, missing, or extra nodes",
        )

    def _require_mapping(self, obj: Any, label: str) -> Mapping[str, Any]:
        if not isinstance(obj, dict):
            raise VerificationError(f"{label} must be a JSON object")
        return obj

    def _require_fraction_positive(self, value: Any, label: str) -> Fraction | None:
        if not isinstance(value, str):
            self.errors.append(f"{label} is not an exact fraction string")
            return None
        try:
            result = Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            self.errors.append(f"invalid fraction at {label}: {exc}")
            return None
        self.require(result > 0, f"non-positive exact slack at {label}")
        return result

    def verify_inner_hash_chain(self) -> None:
        inner = self._require_mapping(
            self.json_at("original/certificate/SHA256SUMS.json"),
            "original certificate SHA manifest",
        )
        self.check(
            set(inner) == set(CERTIFICATE_INNER_FILES),
            "original_certificate_manifest_exact_10_entries",
            "original certificate SHA manifest does not contain exactly the expected 10 entries",
        )
        for inner_name, rel in CERTIFICATE_INNER_FILES.items():
            expected = inner.get(inner_name)
            self.require(
                isinstance(expected, str) and SHA_RE.fullmatch(expected) is not None,
                f"invalid original certificate hash for {inner_name}",
            )
            self.require(
                expected == self.actual_sha(rel),
                f"original certificate inner hash mismatch: {inner_name} -> {rel}",
            )

        promotion = self._require_mapping(
            self.json_at("original/promotion/promotion.json"), "promotion record"
        )
        promotion_sha = self._require_mapping(
            self.json_at("original/promotion/SHA256SUMS.json"), "promotion SHA manifest"
        )
        record = self._require_mapping(
            promotion_sha.get("promotion_record"), "promotion_record"
        )
        self.check(
            record.get("path") == "promotion.json"
            and record.get("sha256") == self.actual_sha("original/promotion/promotion.json"),
            "promotion_record_hash_link",
            "promotion SHA manifest does not authenticate promotion.json",
        )

        promotion_lineage = self._require_mapping(
            promotion.get("lineage_and_evidence"), "promotion lineage_and_evidence"
        )
        promotion_chain = self._require_mapping(
            promotion_sha.get("immutable_certificate_chain"),
            "promotion immutable_certificate_chain",
        )
        for field, inner_name in PROMOTION_CERTIFICATE_FIELDS.items():
            expected = inner.get(inner_name)
            self.require(
                promotion_lineage.get(field) == expected,
                f"promotion lineage field does not match certificate manifest: {field}",
            )
            self.require(
                promotion_chain.get(field) == expected,
                f"promotion SHA chain field does not match certificate manifest: {field}",
            )
        self.require(
            promotion_lineage.get("certificate_sha256s_manifest_sha256")
            == self.actual_sha("original/certificate/SHA256SUMS.json"),
            "promotion does not bind the original certificate SHA manifest",
        )
        self.require(
            promotion_chain.get("certificate_sha256s_manifest_sha256")
            == self.actual_sha("original/certificate/SHA256SUMS.json"),
            "promotion SHA manifest does not bind the certificate SHA manifest",
        )

        numbered_log = self._require_mapping(
            promotion_sha.get("numbered_log_snapshot"), "numbered_log_snapshot"
        )
        log_sha = numbered_log.get("sha256")
        self.check(
            isinstance(log_sha, str)
            and log_sha
            == self.actual_sha(
                "provenance/logs/051_v016_P500严格基线提升与低阶瓶颈.md"
            ),
            "promotion_numbered_log_present",
            "SHA-bound promotion log is absent or changed at its fixed bundle path",
        )

        # The policy was explicitly mutable control state, not a certificate input.
        # If the old bytes are supplied, authenticate them; otherwise make the
        # limitation visible without incorrectly failing the immutable proof chain.
        policy = self._require_mapping(
            promotion_sha.get("policy_snapshot_after_promotion"),
            "policy_snapshot_after_promotion",
        )
        policy_sha = policy.get("sha256")
        policy_matches = (
            self.paths_with_sha(policy_sha, "provenance/")
            if isinstance(policy_sha, str)
            else []
        )
        if policy_matches:
            self.checks.append("optional_historical_policy_snapshot_present")
        else:
            self.warnings.append(
                "The mutable policy snapshot bytes from promotion time are not included; "
                "only their historical hash remains. They are not part of the immutable "
                "certificate proof chain."
            )

    def verify_semantics(self) -> None:
        promotion = self._require_mapping(
            self.json_at("original/promotion/promotion.json"), "promotion"
        )
        candidate = self._require_mapping(
            self.json_at("original/certificate/exact_candidate.json"), "exact candidate"
        )
        attempt = self._require_mapping(
            self.json_at("original/certificate/exact_gate/attempt.json"), "gate attempt"
        )
        report = self._require_mapping(
            self.json_at("original/certificate/exact_gate/verify_report.json"),
            "exact verification report",
        )
        identity = self._require_mapping(
            self.json_at("original/certificate/exact_gate/identity_report.json"),
            "identity report",
        )
        summary = self._require_mapping(
            self.json_at("original/certificate/summary.json"), "certificate summary"
        )
        numerical = self._require_mapping(
            self.json_at("original/certificate/numerical_payload.json"),
            "numerical payload",
        )
        registration = self._require_mapping(
            self.json_at("original/certificate/registration.json"), "registration"
        )

        new_incumbent = self._require_mapping(
            promotion.get("new_incumbent"), "promotion.new_incumbent"
        )
        complete_gate = self._require_mapping(
            promotion.get("complete_gate"), "promotion.complete_gate"
        )
        lineage = self._require_mapping(
            promotion.get("lineage_and_evidence"), "promotion.lineage_and_evidence"
        )
        source_binding = self._require_mapping(
            promotion.get("source_code_binding"), "promotion.source_code_binding"
        )

        self.check(
            promotion.get("schema") == "maxksat.strict_incumbent_promotion.v1"
            and promotion.get("campaign_version") == "v016_j2_group_search"
            and promotion.get("status") == "strict_development_incumbent_promoted",
            "promotion_scope_and_schema",
            "promotion scope/schema/status changed",
        )
        self.check(
            promotion.get("formal_experiment_running") is False
            and promotion.get("target_reached") is False
            and promotion.get("target_rho") == "749/1000",
            "claim_boundary_not_0749",
            "promotion incorrectly changes its development-only / target-not-reached boundary",
        )
        self.check(
            new_incumbent.get("rho") == RHO
            and new_incumbent.get("rho_decimal") == RHO_DECIMAL
            and new_incumbent.get("design_canonical_hash") == DESIGN_HASH,
            "promoted_rho_and_design",
            "promoted rho or canonical design hash changed",
        )
        self.check(
            new_incumbent.get("positive_bucket_count") == 500
            and new_incumbent.get("signed_label_count") == 1000
            and new_incumbent.get("signed_group_count") == 20,
            "promoted_bucket_counts_500_1000_20",
            "promoted bucket/group counts are not 500 positive, 1000 signed, 20 signed groups",
        )
        self.check(
            complete_gate.get("passed") is True
            and complete_gate.get("family_count") == 14
            and complete_gate.get("independent_identity_binding_passed") is True
            and complete_gate.get("complete_fraction_replay_passed") is True,
            "promotion_complete_gate",
            "promotion does not record both identity binding and complete Fraction replay",
        )
        self.check(
            complete_gate.get("low_order_label_pairs_checked") == 2_001_000
            and complete_gate.get("high_order_group_multisets_checked") == 52_899
            and complete_gate.get("upper_hull_transitions_checked") == 21_946_945,
            "promotion_complete_gate_row_counts",
            "promotion row/transition counts changed",
        )

        cert = self._require_mapping(candidate.get("certificate"), "candidate.certificate")
        outer = self._require_mapping(candidate.get("outer_design"), "candidate.outer_design")
        self.check(
            candidate.get("schema") == "v016-fine-unary-exact-promotion-artifact-v1"
            and candidate.get("outer_design_hash") == DESIGN_HASH
            and candidate.get("numerical_payload_sha256") == NUMERICAL_PAYLOAD_SHA256,
            "exact_candidate_binding",
            "exact candidate schema/design/payload binding changed",
        )
        self.check(
            cert.get("schema") == "v016-j1-fine-unary-group-pair-exact-v1"
            and cert.get("rho") == RHO
            and cert.get("claim") == "candidate_requires_complete_fraction_hull_replay",
            "candidate_exact_rho_and_claim",
            "candidate certificate rho/schema/claim changed",
        )
        bucket_map = cert.get("bucket_group_map")
        intervals = cert.get("bucket_intervals")
        rounding = cert.get("rounding")
        self.check(
            cert.get("num_buckets") == 1000
            and isinstance(bucket_map, list)
            and len(bucket_map) == 1000
            and isinstance(intervals, list)
            and len(intervals) == 1000
            and isinstance(rounding, list)
            and len(rounding) == 1000,
            "candidate_1000_signed_buckets",
            "candidate does not contain exactly 1000 signed buckets/maps/rounding values",
        )
        if isinstance(bucket_map, list):
            self.check(
                all(isinstance(value, int) and not isinstance(value, bool) for value in bucket_map)
                and set(bucket_map) == set(range(10)),
                "candidate_10_unsigned_groups",
                "bucket group map is not the expected ten unsigned groups (twenty signed groups)",
            )
        if isinstance(intervals, list) and len(intervals) == 1000:
            try:
                parsed_intervals = [
                    (Fraction(item[0]), Fraction(item[1]))
                    for item in intervals
                    if isinstance(item, list) and len(item) == 2
                ]
                intervals_ok = (
                    len(parsed_intervals) == 1000
                    and parsed_intervals[0][0] == -1
                    and parsed_intervals[-1][1] == 1
                    and all(left < right for left, right in parsed_intervals)
                    and all(
                        parsed_intervals[index - 1][1] == parsed_intervals[index][0]
                        for index in range(1, len(parsed_intervals))
                    )
                )
            except (ValueError, ZeroDivisionError, TypeError):
                intervals_ok = False
            self.check(
                intervals_ok,
                "candidate_signed_bucket_partition",
                "signed bucket intervals are not a contiguous exact partition of [-1,1]",
            )
        if isinstance(rounding, list) and len(rounding) == 1000:
            try:
                rounding_ok = all(0 <= Fraction(value) <= 1 for value in rounding)
            except (ValueError, ZeroDivisionError, TypeError):
                rounding_ok = False
            self.check(
                rounding_ok,
                "candidate_rounding_probabilities_in_unit_interval",
                "one or more exact rounding probabilities is outside [0,1]",
            )

        boundaries = outer.get("positive_bucket_boundary_ticks")
        profiles = outer.get("profile_rounding_ticks")
        tick_denominator = outer.get("tick_denominator")
        self.check(
            isinstance(boundaries, list)
            and len(boundaries) == 499
            and all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in boundaries
            )
            and boundaries == sorted(set(boundaries))
            and isinstance(tick_denominator, int)
            and all(0 < value < tick_denominator for value in boundaries),
            "outer_design_500_positive_buckets",
            "outer design does not define 500 ordered positive buckets",
        )
        self.check(
            isinstance(profiles, list)
            and len(profiles) == 1
            and isinstance(profiles[0], list)
            and len(profiles[0]) == 500
            and all(
                isinstance(value, int)
                and not isinstance(value, bool)
                and 0 <= value <= tick_denominator
                for value in profiles[0]
            )
            and profiles[0] == sorted(profiles[0]),
            "outer_design_500_independent_rounding_slots",
            "outer design rounding profile is not a valid monotone 500-slot profile",
        )
        self.check(
            outer.get("boundary_convention") == "left-closed-right-open-last-closed"
            and outer.get("monotone_rounding") is True
            and outer.get("weight_denominator") == 8380
            and outer.get("weight_numerators") == [611000, 157027, 93018, 50280, 10475]
            and cert.get("weights") == ["30550/419", "157027/8380", "111/10", "6", "5/4"],
            "outer_design_weights_and_boundary_convention",
            "outer design weight or boundary convention changed",
        )

        self.check(
            attempt.get("schema_version") == "v016-fine-unary-independent-exact-gate-v1"
            and attempt.get("status") == "exact_verified"
            and attempt.get("verified_rho") == RHO
            and attempt.get("design_hash") == DESIGN_HASH
            and attempt.get("all_14_families_verified") is True
            and attempt.get("complete_separation") is True,
            "exact_gate_attempt_passed",
            "exact gate attempt status/rho/design/coverage changed",
        )
        self.check(
            attempt.get("artifact_sha256")
            == self.actual_sha("original/certificate/exact_candidate.json")
            and attempt.get("numerical_payload_sha256") == NUMERICAL_PAYLOAD_SHA256
            and attempt.get("identity_report_sha256")
            == self.actual_sha("original/certificate/exact_gate/identity_report.json")
            and attempt.get("verify_report_sha256")
            == self.actual_sha("original/certificate/exact_gate/verify_report.json"),
            "exact_gate_attempt_hash_links",
            "exact gate attempt hash links changed",
        )

        self.check(
            report.get("schema") == "v016-j1-fine-unary-group-pair-exact-v1"
            and report.get("status") == "exact_rational_certificate"
            and report.get("ok") is True
            and report.get("rho") == RHO,
            "exact_fraction_report_passed",
            "exact Fraction report status/schema/rho changed",
        )
        report_flags = (
            "all_14_families_verified",
            "all_high_order_rows_checked",
            "all_low_order_rows_checked",
            "complete_separation",
            "fine_unary_anchor_gauge_verified",
            "lower_group_minimum_equivalence",
            "upper_hull_equivalence",
        )
        self.check(
            all(report.get(name) is True for name in report_flags),
            "exact_fraction_report_coverage_flags",
            "one or more exact Fraction coverage/equivalence flags is not true",
        )
        self.check(
            report.get("num_buckets") == 1000
            and report.get("num_label_groups") == 20
            and report.get("num_profiles") == 1
            and report.get("low_label_pairs") == 2_001_000
            and report.get("group_multisets") == 52_899
            and report.get("upper_hull_transitions") == 21_946_945
            and report.get("maximum_upper_hull_size") == 177,
            "exact_fraction_report_dimensions",
            "exact Fraction report dimensions or complete row counts changed",
        )
        report_min = self._require_fraction_positive(report.get("minimum_slack"), "report.minimum_slack")
        attempt_min = self._require_fraction_positive(
            attempt.get("minimum_slack"), "attempt.minimum_slack"
        )
        self.require(report_min == Fraction(1, 10**12), "global minimum slack is not exactly 1e-12")
        self.require(attempt_min == report_min, "attempt/report minimum slacks disagree")

        families = report.get("families")
        self.check(
            isinstance(families, dict) and set(families) == EXPECTED_FAMILIES,
            "exact_14_family_set",
            "exact report family names are not the expected complete set of 14",
        )
        family_slacks: list[Fraction] = []
        if isinstance(families, dict):
            for name in sorted(EXPECTED_FAMILIES & set(families)):
                family = families[name]
                if not isinstance(family, dict):
                    self.errors.append(f"family record is not an object: {name}")
                    continue
                slack = self._require_fraction_positive(
                    family.get("minimum_slack"), f"families.{name}.minimum_slack"
                )
                if slack is not None:
                    family_slacks.append(slack)
                separated = family.get("separated_rows")
                conceptual = family.get("conceptual_rows")
                self.require(
                    isinstance(separated, int)
                    and not isinstance(separated, bool)
                    and separated > 0
                    and isinstance(conceptual, int)
                    and not isinstance(conceptual, bool)
                    and conceptual >= separated,
                    f"invalid row counts for exact family {name}",
                )
        if family_slacks and report_min is not None:
            self.require(
                min(family_slacks) == report_min,
                "reported global slack is not the minimum of all 14 family slacks",
            )

        identity_flags = (
            "identity_verified",
            "model_restrictions_verified",
            "numerical_payload_bound",
            "float_to_exact_repair_verified",
        )
        restrictions = identity.get("model_restrictions")
        self.check(
            identity.get("identity_schema") == "v016-j1-fine-unary-certificate-identity-v1"
            and all(identity.get(name) is True for name in identity_flags)
            and identity.get("rho_bound") == RHO
            and identity.get("outer_design_hash") == DESIGN_HASH
            and identity.get("numerical_payload_sha256") == NUMERICAL_PAYLOAD_SHA256,
            "independent_identity_binding",
            "independent identity report or one of its four required flags changed",
        )
        self.check(
            isinstance(restrictions, dict)
            and restrictions.get("J") == 1
            and restrictions.get("arity") == [3, 4, 5]
            and restrictions.get("maximum_endpoint_order") == 2
            and restrictions.get("weight_budget") == 110
            and restrictions.get("boundary_convention")
            == "left-closed-right-open-last-closed"
            and restrictions.get("surrogate")
            == "fine-label unary plus coarse-label-group pair",
            "identity_model_restrictions",
            "bound model restrictions changed",
        )
        content_links = {
            "raw_design_content_sha256": "raw_design_content_hash",
            "raw_witness_content_sha256": "raw_witness_content_hash",
            "group_map_content_sha256": "group_map_content_hash",
            "unary_content_sha256": "unary_content_hash",
            "pair_content_sha256": "pair_content_hash",
            "lambda_content_sha256": "lambda_content_hash",
        }
        for promotion_name, identity_name in content_links.items():
            self.require(
                lineage.get(promotion_name) == identity.get(identity_name),
                f"promotion/identity content hash disagreement: {promotion_name}",
            )
        self.require(
            lineage.get("exact_report_payload_sha256") == report.get("payload_sha256"),
            "promotion/report exact logical payload hash disagreement",
        )

        self.check(
            summary.get("schema_version") == "v016-target-design-fine-unary-full-summary-v1"
            and summary.get("is_full_certificate") is True
            and summary.get("strict_improvement") is True
            and summary.get("verified_rho") == RHO
            and summary.get("design_hash") == DESIGN_HASH
            and summary.get("complete_separation") is True
            and summary.get("all_low_order_rows_checked") is True
            and summary.get("all_fine_typed_rows_checked") is True
            and summary.get("all_fine_upper_rows_covered") is True,
            "certificate_summary_full_and_strict",
            "certificate summary does not retain the full strict certificate claim",
        )
        self.check(
            summary.get("exact_artifact_sha256")
            == self.actual_sha("original/certificate/exact_candidate.json")
            and summary.get("numerical_payload_sha256") == NUMERICAL_PAYLOAD_SHA256
            and summary.get("raw_file_sha256")
            == self.actual_sha("original/certificate/fine_unary_raw.json")
            and summary.get("exact_gate") == attempt,
            "certificate_summary_hash_and_gate_links",
            "certificate summary hash links or embedded exact gate changed",
        )
        self.require(
            summary.get("artifact_content_sha256")
            == lineage.get("certificate_summary_content_sha256"),
            "certificate summary logical content hash differs from promotion",
        )

        self.check(
            numerical.get("schema_version") == "v016-fine-unary-numerical-candidate-v1"
            and numerical.get("status") == "complete_fine_unary_numeric_candidate"
            and numerical.get("design_hash") == DESIGN_HASH
            and numerical.get("outer_design") == outer
            and numerical.get("bucket_group_map") == bucket_map,
            "bound_numerical_payload_design",
            "SHA-bound numerical payload no longer agrees with the exact design",
        )
        numerical_check = numerical.get("check")
        self.check(
            isinstance(numerical_check, dict)
            and numerical_check.get("ok") is True
            and numerical_check.get("all_low_order_rows_checked") is True
            and numerical_check.get("all_high_order_rows_checked") is True
            and numerical_check.get("complete_separation") is True,
            "bound_numerical_payload_coverage",
            "numerical payload coverage flags changed",
        )
        self.require(
            registration.get("design_hash") == DESIGN_HASH,
            "registration design hash changed",
        )

    def verify_bound_sources_and_inputs(self) -> None:
        promotion = self._require_mapping(
            self.json_at("original/promotion/promotion.json"), "promotion"
        )
        source_binding = self._require_mapping(
            promotion.get("source_code_binding"), "source_code_binding"
        )
        for field, suffix in SOURCE_BINDINGS.items():
            sha = source_binding.get(field)
            expected_rel = f"verifier/source/{suffix}"
            self.require(
                isinstance(sha, str) and self.actual_sha(expected_rel) == sha,
                f"bound verifier source absent or changed: {expected_rel}",
            )

        attempt = self._require_mapping(
            self.json_at("original/certificate/exact_gate/attempt.json"), "attempt"
        )
        attempt_sources = attempt.get("verifier_source_sha256")
        if not isinstance(attempt_sources, dict):
            self.errors.append("attempt.verifier_source_sha256 is not an object")
        else:
            basename_paths = {
                "v016_fine_unary_exact.py": "verifier/source/src/maxksat_large/v016_fine_unary_exact.py",
                "v016_fine_unary_identity.py": "verifier/source/src/maxksat_large/v016_fine_unary_identity.py",
                "v016_fine_unary_gate.py": "verifier/source/src/maxksat_large/v016_fine_unary_gate.py",
            }
            self.require(
                set(attempt_sources) == set(basename_paths),
                "attempt verifier source set changed",
            )
            for name, rel in basename_paths.items():
                self.require(
                    attempt_sources.get(name) == self.actual_sha(rel),
                    f"attempt verifier source hash mismatch: {name}",
                )

        identity = self._require_mapping(
            self.json_at("original/certificate/exact_gate/identity_report.json"), "identity"
        )
        self.require(
            identity.get("numerical_code_sha256")
            == {
                "scripts/run_v016_target_design_fine_unary_full.py": self.actual_sha(
                    "verifier/source/scripts/run_v016_target_design_fine_unary_full.py"
                ),
                "src/maxksat_large/v016_fine_unary_large.py": self.actual_sha(
                    "verifier/source/src/maxksat_large/v016_fine_unary_large.py"
                ),
            },
            "identity numerical code hashes do not match bundled sources",
        )

        lineage = self._require_mapping(
            promotion.get("lineage_and_evidence"), "lineage_and_evidence"
        )
        direct_lineage_fields = {
            "hierarchical_lift_overall_summary_sha256": (
                "provenance/lineage/v016_hierarchical_lift/overall_summary.json"
            ),
            "hierarchical_lift_p500_summary_sha256": (
                "provenance/lineage/v016_hierarchical_lift/p500_summary.json"
            ),
            "source_design_artifact_sha256": (
                "provenance/lineage/v016_hierarchical_lift/p500_source_candidate.json"
            ),
        }
        for field, rel in direct_lineage_fields.items():
            self.require(
                lineage.get(field) == self.actual_sha(rel),
                f"SHA-bound direct lineage input absent: {field}",
            )

        numerical_sources = identity.get("numerical_source_sha256")
        if not isinstance(numerical_sources, dict):
            self.errors.append("identity.numerical_source_sha256 is not an object")
        else:
            expected_keys = {
                "fine_unary_raw_file",
                "strict_anchor_file",
                "target_candidate_file",
                "warm_payload_file",
            }
            self.require(
                set(numerical_sources) == expected_keys,
                "identity numerical source key set changed",
            )
            raw_sha = numerical_sources.get("fine_unary_raw_file")
            self.require(
                raw_sha == self.actual_sha("original/certificate/fine_unary_raw.json"),
                "identity raw numerical source does not match original certificate",
            )
            numerical_source_paths = {
                "strict_anchor_file": "provenance/lineage/v014_anchor/certified_anchor.json",
                "target_candidate_file": (
                    "provenance/lineage/v016_hierarchical_lift/p500_source_candidate.json"
                ),
                "warm_payload_file": "provenance/lineage/v016_fine_unary/warm_payload.json",
            }
            for key, rel in numerical_source_paths.items():
                self.require(
                    numerical_sources.get(key) == self.actual_sha(rel),
                    f"SHA-bound numerical direct input absent: {key}",
                )

        self.check(
            not self.errors,
            "all_hash_chain_semantic_source_and_input_checks",
            "one or more hash-chain, semantic, source, or direct-input checks failed",
        )

    def run(self) -> dict[str, Any]:
        fatal: str | None = None
        try:
            self.verify_structure_and_manifest()
            # Do not interpret unauthenticated/truncated JSON as certificate data.
            if self.errors:
                raise VerificationError(
                    "structure, manifest, strict JSON, or trust-anchor verification failed"
                )
            self.verify_inner_hash_chain()
            self.verify_semantics()
            self.verify_bound_sources_and_inputs()
        except VerificationError as exc:
            fatal = str(exc)
            self.errors.append(fatal)

        manifest_sha = None
        manifest_path = self.files.get("BUNDLE_MANIFEST.json")
        if manifest_path is not None:
            try:
                manifest_sha = sha256_file(manifest_path)
            except OSError:
                pass
        return {
            "schema": "maxksat.strict_certificate_bundle_verification.v1",
            "ok": not self.errors,
            "bundle_root": str(self.root),
            "verified_rho": RHO if not self.errors else None,
            "verified_rho_decimal": RHO_DECIMAL if not self.errors else None,
            "design_canonical_hash": DESIGN_HASH if not self.errors else None,
            "bundle_manifest_sha256": manifest_sha,
            "manifest_payload_file_count": len(self.manifest_files),
            "actual_file_count_including_manifest": len(self.files),
            "compiled_trust_anchor_count": len(TRUST_ANCHORS),
            "direct_input_anchor_count": len(DIRECT_INPUT_ANCHORS),
            "project_state_anchor_count": len(PROJECT_STATE_ANCHORS),
            "checks_passed": self.checks,
            "check_count": len(self.checks),
            "warnings": self.warnings,
            "errors": self.errors,
            "fatal_error": fatal,
            "full_fraction_replay_performed": False,
            "note": (
                "This fast verifier authenticates the archived full Fraction result; "
                "it does not recompute the expensive mathematical certificate."
            ),
        }


def _write_json_report(destination: str, report: Mapping[str, Any], root: Path) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if destination == "-":
        sys.stdout.write(rendered)
        return
    path = Path(destination).expanduser().resolve()
    try:
        path.relative_to(root)
    except ValueError:
        pass
    else:
        raise VerificationError(
            "--json-output must be outside the immutable bundle being verified"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the exact file closure, six trust anchors, original SHA chains, "
            "bound sources/direct inputs, and key semantics of the rho=0.742694813 bundle."
        )
    )
    parser.add_argument(
        "bundle_root_positional",
        nargs="?",
        help="extracted bundle root containing BUNDLE_MANIFEST.json",
    )
    parser.add_argument(
        "--bundle-root",
        dest="bundle_root_option",
        help="named form of bundle_root (default: current directory)",
    )
    parser.add_argument(
        "--json-output",
        metavar="PATH_OR_DASH",
        help="also write the complete machine-readable report; use '-' for stdout only",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.bundle_root_positional and args.bundle_root_option:
        positional = Path(args.bundle_root_positional).expanduser().resolve()
        named = Path(args.bundle_root_option).expanduser().resolve()
        if positional != named:
            parser.error("positional bundle_root and --bundle-root name different paths")
    root_arg = args.bundle_root_option or args.bundle_root_positional or "."
    root = Path(root_arg).expanduser().resolve()
    verifier = BundleVerifier(root)
    report = verifier.run()

    json_only = args.json_output == "-"
    if args.json_output:
        try:
            _write_json_report(args.json_output, report, root)
        except VerificationError as exc:
            report["ok"] = False
            report["errors"].append(str(exc))
            if json_only:
                sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            else:
                print(f"ERROR: {exc}", file=sys.stderr)

    if not json_only:
        if report["ok"]:
            print(
                "PASS: rho=0.742694813 bundle bytes, SHA chains, source bindings, "
                "and archived exact-certificate semantics verified."
            )
            print(
                f"Files: {report['actual_file_count_including_manifest']} | "
                f"Checks: {report['check_count']} | "
                f"Manifest SHA-256: {report['bundle_manifest_sha256']}"
            )
            for warning in report["warnings"]:
                print(f"WARNING: {warning}")
        else:
            print("FAIL: certificate bundle verification failed.", file=sys.stderr)
            for error in report["errors"]:
                print(f"ERROR: {error}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
