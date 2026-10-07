#!/usr/bin/env python3
"""Universal CI guard: reject any PR/branch that touches a globally
forbidden path, regardless of who (human or AI) authored the change.

Unlike `validate_change.py`, this check needs no evidence contract and
no scenario classification -- it only needs the policy file and a base
ref to diff against. It is meant to run as a required status check on
every pull request, so that even if a self-heal remediation agent
misbehaves (or a human accidentally does), CMakeLists.txt / scripts /
framework / test-harness files can never be silently modified.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evaluate_policy  # noqa: E402


def run(cmd):
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True,
                         help="Base ref/SHA to diff against (e.g. the PR base branch).")
    parser.add_argument("--policy", type=Path, default=evaluate_policy.DEFAULT_POLICY_PATH)
    parser.add_argument("--max-diff-lines", type=int, default=2000,
                         help="Generous universal cap on total inserted+deleted lines, "
                              "independent of any per-scenario policy limit.")
    args = parser.parse_args()

    merge_base = run(["git", "merge-base", args.base_ref, "HEAD"]).stdout.strip()
    if not merge_base:
        print(f"error: could not compute merge-base with {args.base_ref}", file=sys.stderr)
        return 2

    numstat = run(["git", "diff", "--numstat", merge_base, "HEAD"]).stdout
    changed_files, inserted, deleted = evaluate_policy._numstat_to_counts(numstat)

    policy = evaluate_policy.load_policy(args.policy)
    global_forbidden = policy.get("globally_forbidden_paths", [])

    violations = []
    for f in changed_files:
        if evaluate_policy._matches_any(f, global_forbidden):
            violations.append(f)

    total_lines = inserted + deleted
    if total_lines > args.max_diff_lines:
        violations.append(
            f"<diff size {total_lines} lines exceeds universal cap {args.max_diff_lines}>"
        )

    if violations:
        print("FORBIDDEN PATH / SIZE GUARD FAILED:")
        for v in violations:
            print(f"  - {v}")
        return 1

    print(f"OK: no globally forbidden paths touched ({len(changed_files)} files, "
          f"{total_lines} lines changed since {merge_base[:8]}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
