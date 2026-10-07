#!/usr/bin/env python3
"""Apply one of this repository's auditable demo-failure fixtures to the
local working tree, for quick manual experimentation only.

Fixtures are plain unified diffs under fixtures/<scenario>/fixture.patch,
reviewable like any other change. This script applies the named
scenario's patch to the current working tree; it does not create
branches, commits, or pull requests itself.

This is an optional developer convenience, separate from the live
self-healing demo. The `self-heal-remediation` workflow never applies a
fixture and never calls this script -- it only ever reacts to a real CI
failure on a real pull request. To produce a real pull request that
exercises the full remediation path end-to-end, use
`scripts/demo_submit_pr.py <scenario>` instead, which creates a normal
branch, commit, and pull request via the `gh` CLI.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"

KNOWN_SCENARIOS = ["easy-unit-test", "medium-low-coverage", "advanced-performance"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=KNOWN_SCENARIOS)
    parser.add_argument("--check", action="store_true",
                         help="Validate the patch applies cleanly without modifying files.")
    args = parser.parse_args()

    fixture_dir = FIXTURES_DIR / args.scenario
    patch_path = fixture_dir / "fixture.patch"
    metadata_path = fixture_dir / "metadata.json"

    if not patch_path.exists():
        print(f"No fixture patch found for scenario {args.scenario!r}: {patch_path}", file=sys.stderr)
        return 2

    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    print(f"Applying fixture: {args.scenario}")
    if metadata.get("description"):
        print(f"  {metadata['description']}")

    cmd = ["git", "apply"]
    if args.check:
        cmd.append("--check")
    cmd.append(str(patch_path))

    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"Failed to apply fixture {args.scenario!r}", file=sys.stderr)
        return result.returncode

    if not args.check:
        print(f"Fixture applied. Target files: {metadata.get('target_files', [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
