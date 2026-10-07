#!/usr/bin/env python3
"""Deterministic loop-prevention guards for the self-heal remediation
workflow.

These run *before* any evidence is even downloaded, using only the
triggering `workflow_run` event payload plus two small live lookups the
calling workflow performs (the pull request's current head SHA, and
whether a remediation branch/PR already exists for this head SHA) --
see `.github/workflows/self-heal-remediation.md` for exactly how those
two values are obtained via the GitHub CLI/API.

Guards enforced, in order (any failure denies and stops immediately):

  1. The completed workflow run must be for the `pull_request` event
     with conclusion `failure`. Anything else (push, schedule, success,
     cancelled, ...) is out of scope.
  2. The run must be associated with a pull request in *this*
     repository. GitHub does not populate `workflow_run.pull_requests`
     for fork pull requests, so an empty list here means "fork PR" --
     denied, because the remediation workflow runs with repository
     secrets, and a fork PR's CI run must never be able to trigger it.
  3. The pull request's head branch must not already start with the
     configured `remediation_branch_prefix` -- otherwise a remediation
     PR's own (inevitably red, by design, until a human merges it) CI
     run could re-trigger another remediation attempt against itself.
  4. The workflow run's `head_sha` must still be the pull request's
     *current* head SHA. If the developer pushed new commits after CI
     ran, the evidence is stale and must not be acted on.
  5. No remediation branch/PR may already exist for this exact head
     SHA + category (duplicate guard) -- the caller supplies this as a
     single pre-computed boolean so this module stays a pure function.

This module performs no network calls itself and calls no AI model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evaluate_policy  # noqa: E402

DEFAULT_POLICY_PATH = evaluate_policy.DEFAULT_POLICY_PATH


def evaluate_guards(policy: dict, context: dict) -> dict:
    reasons = []
    workflow_run = context.get("workflow_run", {})

    event = workflow_run.get("event")
    conclusion = workflow_run.get("conclusion")
    if event != "pull_request" or conclusion != "failure":
        reasons.append(
            f"workflow_run event={event!r} conclusion={conclusion!r} is not an "
            "in-scope pull_request failure"
        )
        return _deny(reasons)

    pull_requests = workflow_run.get("pull_requests") or []
    same_repo = (
        workflow_run.get("repository_full_name")
        == workflow_run.get("head_repository_full_name")
    )
    if not pull_requests or not same_repo:
        reasons.append(
            "no same-repository pull request is associated with this workflow run "
            "(forked pull requests never populate workflow_run.pull_requests)"
        )
        return _deny(reasons)

    pr_number = pull_requests[0].get("number")
    head_branch = workflow_run.get("head_branch", "")
    branch_prefix = policy.get("remediation_branch_prefix", "self-heal/")
    if head_branch.startswith(branch_prefix):
        reasons.append(
            f"head_branch {head_branch!r} already starts with remediation_branch_prefix "
            f"{branch_prefix!r} (loop guard: refusing to remediate a remediation branch)"
        )
        return _deny(reasons, pr_number)

    current_head_sha = context.get("current_pr_head_sha")
    workflow_head_sha = workflow_run.get("head_sha")
    if not current_head_sha or current_head_sha != workflow_head_sha:
        reasons.append(
            f"workflow_run.head_sha {workflow_head_sha!r} does not match the pull "
            f"request's current head SHA {current_head_sha!r} (stale: new commits "
            "were pushed after this CI run)"
        )
        return _deny(reasons, pr_number)

    if context.get("existing_remediation_branch_exists"):
        reasons.append(
            "a remediation branch/pull request already exists for this head SHA "
            "(duplicate guard)"
        )
        return _deny(reasons, pr_number)

    return {
        "schema_version": "2.0",
        "decision": "allow",
        "pr_number": pr_number,
        "head_branch": head_branch,
        "head_sha": workflow_head_sha,
        "base_branch": pull_requests[0].get("base_ref"),
        "reasons": [],
    }


def _deny(reasons, pr_number=None) -> dict:
    return {
        "schema_version": "2.0",
        "decision": "deny",
        "pr_number": pr_number,
        "head_branch": None,
        "head_sha": None,
        "base_branch": None,
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, type=Path,
                         help="JSON file with {workflow_run, current_pr_head_sha, "
                              "existing_remediation_branch_exists}.")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    context = json.loads(args.context.read_text())
    policy = evaluate_policy.load_policy(args.policy)
    decision = evaluate_guards(policy, context)

    output_text = json.dumps(decision, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text + "\n")
    print(output_text)

    return 0 if decision["decision"] == "allow" else 1


if __name__ == "__main__":
    sys.exit(main())
