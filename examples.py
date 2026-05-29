#!/usr/bin/env python3
"""Convenience entry points for the Max-kSAT LP certificate artifact.

This mirrors the lightweight examples.py style of singerng/oblivious-csps:
the exact verifier is the main artifact, while the floating-point LP search is
an optional reproducibility aid.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def verify() -> None:
    """Run the exact rational certificate verifier."""
    run([sys.executable, "scripts/verify_certificate.py"])


def verify_max2sat() -> None:
    """Run the exact rational Max-2SAT companion verifier."""
    run([sys.executable, "scripts/verify_max2sat_certificate.py"])


def test() -> None:
    """Run the repository smoke tests."""
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])


def search() -> None:
    """Run the optional floating-point LP search.

    This requires scipy.  The formal proof should rely on verify(), not on this
    floating-point search.
    """
    run([sys.executable, "scripts/search_lp_certificate.py"])


def all_checks() -> None:
    """Run the exact verifier and smoke tests."""
    verify()
    verify_max2sat()
    test()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["verify", "verify-max2sat", "test", "search", "all"],
        nargs="?",
        default="all",
        help="which example/check to run",
    )
    args = parser.parse_args()
    if args.command == "verify":
        verify()
    elif args.command == "verify-max2sat":
        verify_max2sat()
    elif args.command == "test":
        test()
    elif args.command == "search":
        search()
    else:
        all_checks()


if __name__ == "__main__":
    main()
