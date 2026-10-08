#!/usr/bin/env python3
"""Prepare or replay the isolated v016 fine-unary exact certificate gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from maxksat_large.v016_fine_unary_exact import (  # noqa: E402
    FineUnaryExactResourceLimits,
)
from maxksat_large.v016_fine_unary_gate import (  # noqa: E402
    prepare_fine_unary_exact_artifact,
    verify_fine_unary_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--artifact", type=Path)
    source.add_argument("--numerical-payload", type=Path)
    parser.add_argument("--artifact-output", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--repair-padding", default="1/1000000000000")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-design-hash", required=True)
    parser.add_argument("--max-num-buckets", type=int, default=2_048)
    parser.add_argument("--max-low-label-pairs", type=int, default=2_100_000)
    parser.add_argument("--max-group-multisets", type=int, default=2_000_000)
    parser.add_argument("--max-pair-table-entries", type=int, default=20_000)
    parser.add_argument("--max-hull-states", type=int, default=8_192)
    parser.add_argument("--max-upper-transitions", type=int, default=120_000_000)
    parser.add_argument("--max-seconds", type=float, default=600.0)
    args = parser.parse_args()
    limits = FineUnaryExactResourceLimits(
        max_num_buckets=args.max_num_buckets,
        max_low_label_pairs=args.max_low_label_pairs,
        max_group_multisets=args.max_group_multisets,
        max_pair_table_entries=args.max_pair_table_entries,
        max_hull_states=args.max_hull_states,
        max_upper_transitions=args.max_upper_transitions,
        max_seconds=args.max_seconds,
    )
    preparation = None
    artifact = args.artifact
    if args.numerical_payload is not None:
        if args.artifact_output is None or args.target is None:
            parser.error("--numerical-payload requires --artifact-output and exact --target")
        preparation = prepare_fine_unary_exact_artifact(
            args.numerical_payload,
            args.artifact_output,
            target_rho=args.target,
            repair_padding=args.repair_padding,
            resource_limits=limits,
        )
        artifact = args.artifact_output
    elif args.artifact_output is not None or args.target is not None:
        parser.error("--artifact-output/--target apply only to --numerical-payload")
    result = verify_fine_unary_artifact(
        artifact,
        args.output_dir,
        args.expected_design_hash,
        resource_limits=limits,
    )
    rendered = result if preparation is None else {"preparation": preparation, "gate": result}
    print(json.dumps(rendered, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "exact_verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
