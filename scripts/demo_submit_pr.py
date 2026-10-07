#!/usr/bin/env python3
"""Create a normal developer branch, commit, and pull request from one of
this repository's demo-failure fixtures, using the `gh` CLI.

This is the **only** supported way fixtures interact with the live
self-healing demo: they are a convenience for repeatably producing a real
pull request that CI will genuinely fail on, so the full PR-driven
remediation path (CI failure -> evidence -> classification -> policy ->
diagnosis comment -> bounded AI remediation -> stacked fix PR) can be
exercised end-to-end without having to write a real bug by hand each time.

The remediation workflow itself never applies a fixture and never knows
fixtures exist -- it only ever reacts to a real CI failure on a real pull
request, regardless of how that failure was introduced.

Usage:
    python3 scripts/demo_submit_pr.py easy-unit-test
    python3 scripts/demo_submit_pr.py medium-low-coverage --base main
    python3 scripts/demo_submit_pr.py advanced-performance --no-push

Requires a clean working tree, the `gh` CLI authenticated against this
repository, and push access to create branches on `origin`.
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"

KNOWN_SCENARIOS = ["easy-unit-test", "medium-low-coverage", "advanced-performance"]


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=REPO_ROOT, check=True, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", choices=KNOWN_SCENARIOS)
    parser.add_argument("--base", default="main", help="Base branch for the demo pull request.")
    parser.add_argument("--no-push", action="store_true",
                         help="Create the local branch and commit only; do not push or open a PR.")
    parser.add_argument("--draft", action="store_true", help="Open the pull request as a draft.")
    args = parser.parse_args()

    fixture_dir = FIXTURES_DIR / args.scenario
    patch_path = fixture_dir / "fixture.patch"
    metadata_path = fixture_dir / "metadata.json"
    if not patch_path.exists():
        print(f"No fixture patch found for scenario {args.scenario!r}: {patch_path}", file=sys.stderr)
        return 2

    status = subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True)
    if status.stdout.strip():
        print("Working tree is not clean. Commit, stash, or discard changes before running this "
              "demo helper.", file=sys.stderr)
        return 1

    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    description = metadata.get("description", args.scenario)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    branch = f"demo/{args.scenario}-{timestamp}"

    run(["git", "checkout", args.base])
    run(["git", "pull", "--ff-only", "origin", args.base])
    run(["git", "checkout", "-b", branch])
    run(["git", "apply", str(patch_path)])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", f"demo: {description}\n\nIntroduces a real, isolated defect from "
                                  f"fixtures/{args.scenario}/ for the self-heal remediation demo."])

    if args.no_push:
        print(f"\nCreated local branch {branch!r} with a real commit. Push it and open a pull "
              f"request manually when you are ready, or re-run without --no-push.")
        return 0

    run(["git", "push", "-u", "origin", branch])

    pr_cmd = ["gh", "pr", "create", "--base", args.base, "--head", branch,
               "--title", f"demo: {description}",
               "--body", (
                   f"Demo pull request for the self-healing CI/CD remediation workflow, "
                   f"introducing the `{args.scenario}` fixture as a real, isolated defect.\n\n"
                   "CI is expected to fail on this pull request. The `self-heal-remediation` "
                   "workflow should then automatically post a diagnosis and, if policy permits, "
                   "open a draft pull request stacked on top of this branch with a validated fix."
               )]
    if args.draft:
        pr_cmd.append("--draft")
    run(pr_cmd)

    print(f"\nPull request opened from {branch!r} against {args.base!r}. "
          "Watch the CI and self-heal-remediation workflow runs in the Actions tab.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
