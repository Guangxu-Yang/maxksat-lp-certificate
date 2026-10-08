#!/usr/bin/env python3
"""Verify or independently replay the rho=0.742694813 Max-kSAT bundle.

The default check verifies the immutable bundle's integrity and archived report
semantics. Use ``replay`` for a full exact-arithmetic recomputation.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / "artifacts" / "maxksat" / "strict-rho-0.742694813"


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def verify() -> None:
    """Check bundle bytes, hash bindings, and archived result semantics."""
    run([
        sys.executable, "-B", str(BUNDLE / "tools" / "verify_bundle.py"),
        "--bundle-root", str(BUNDLE),
    ])


def replay(output_dir: Path) -> None:
    """Recompute the exact certificate, writing a fresh report outside the bundle."""
    verify()
    run([
        sys.executable, "-B", str(BUNDLE / "tools" / "replay_exact_certificate.py"),
        "--bundle-root", str(BUNDLE), "--output-dir", str(output_dir),
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["verify", "replay"],
        nargs="?",
        default="verify",
        help="check to run (default: verify)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="required for replay: a new or empty directory outside the immutable bundle",
    )
    args = parser.parse_args()
    if not __debug__:
        parser.error("run without -O/-OO or PYTHONOPTIMIZE; verification needs assertions")
    if args.command == "replay":
        if args.output_dir is None:
            parser.error("replay requires --output-dir outside the immutable bundle")
        output_dir = args.output_dir.expanduser().resolve()
        if output_dir == BUNDLE or BUNDLE in output_dir.parents:
            parser.error("--output-dir must be outside the immutable bundle")
        if output_dir.exists() and (
            not output_dir.is_dir() or any(output_dir.iterdir())
        ):
            parser.error("--output-dir must be a new or empty directory")
        replay(output_dir)
    elif args.output_dir is not None:
        parser.error("--output-dir is only supported with replay")
    else:
        verify()


if __name__ == "__main__":
    main()
