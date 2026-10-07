#!/usr/bin/env python3
"""Reset a previously applied demo-failure fixture in the local working tree.

Reverts the named scenario's fixture patch (the inverse of
scripts/create_demo_failure.py) and removes any generated evidence
artifacts under .evidence/. Intended for local experimentation only; the
live self-healing demo never applies fixtures to begin with (see
scripts/demo_submit_pr.py), so there is nothing for the remediation
workflow itself to "reset" -- a demo pull request is simply closed or its
branch deleted like any other.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"
EVIDENCE_DIR = REPO_ROOT / ".evidence"

KNOWN_SCENARIOS = ["easy-unit-test", "medium-low-coverage", "advanced-performance"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=KNOWN_SCENARIOS)
    args = parser.parse_args()

    patch_path = FIXTURES_DIR / args.scenario / "fixture.patch"
    if not patch_path.exists():
        print(f"No fixture patch found for scenario {args.scenario!r}", file=sys.stderr)
        return 2

    result = subprocess.run(["git", "apply", "-R", str(patch_path)], cwd=REPO_ROOT)
    if result.returncode != 0:
        print(
            f"Failed to revert fixture {args.scenario!r}. If it was never applied, "
            "there is nothing to reset.",
            file=sys.stderr,
        )
        return result.returncode

    if EVIDENCE_DIR.exists():
        shutil.rmtree(EVIDENCE_DIR)
        print(f"Removed {EVIDENCE_DIR}")

    print(f"Fixture {args.scenario!r} reverted; working tree restored to healthy state.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
