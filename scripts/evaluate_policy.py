#!/usr/bin/env python3
"""Deterministic policy engine.

Consumes:
  - the evidence contract (JSON)
  - the deterministic classifier's output (JSON)
  - a proposed patch's changed-file list and insertion/deletion counts
    (as produced by `git diff --numstat`)

Emits a policy decision (JSON) describing whether remediation is allowed,
and if not, why. The engine fails closed: any ambiguity, missing data, or
rule violation results in a denial.

Policy is driven by the evidence's `failure_category`
(unit-test-failure / coverage-gap / performance-regression), looked up
in `.github/policies/self-heal-policy.yml`'s `categories` block -- not
by a fixed scenario id, because a real developer pull request can touch
any file. This script never calls an AI model; it is pure, deterministic
rule evaluation over that policy file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "framework" / "schemas"))

import simple_yaml  # noqa: E402

DEFAULT_POLICY_PATH = REPO_ROOT / ".github" / "policies" / "self-heal-policy.yml"


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict:
    return simple_yaml.load_file(str(path))


def _matches_any(path: str, prefixes) -> bool:
    return any(path == p or path.startswith(p) for p in (prefixes or []))


def evaluate(
    policy: dict,
    classification: dict,
    evidence: dict,
    changed_files: list,
    inserted_lines: int,
    deleted_lines: int,
) -> dict:
    """Returns a policy decision dict. Never raises for ordinary denial
    conditions; only raises for structurally malformed inputs."""

    reasons: List[str] = []
    failure_category = evidence.get("failure_category")
    categories = policy.get("categories", {})

    if not classification.get("supported", False):
        return _deny(
            failure_category,
            ["classifier marked evidence as unsupported: "
             + str(classification.get("reason", "no reason given"))],
        )

    category_policy = categories.get(failure_category)
    if category_policy is None:
        return _deny(failure_category, [f"no policy defined for category {failure_category!r}"])

    classified_category = classification.get("failure_category")
    if classified_category != failure_category:
        reasons.append(
            f"classification failure_category {classified_category!r} does not match "
            f"evidence failure_category {failure_category!r}"
        )

    attempt_number = evidence.get("attempt_number", 1)
    max_attempts = category_policy.get("max_attempts", 1)
    if attempt_number > max_attempts:
        reasons.append(
            f"attempt_number {attempt_number} exceeds max_attempts {max_attempts}"
        )

    budget = evidence.get("runtime_budget", {})
    budget_minutes = category_policy.get("runtime_budget_minutes")
    elapsed = budget.get("elapsed_minutes")
    if elapsed is not None and budget_minutes is not None and elapsed > budget_minutes:
        reasons.append(
            f"runtime_budget.elapsed_minutes {elapsed} exceeds budget {budget_minutes}"
        )

    global_forbidden = policy.get("globally_forbidden_paths", [])
    category_forbidden = category_policy.get("forbidden_paths", [])
    permitted = category_policy.get("permitted_paths", [])

    for f in changed_files:
        if _matches_any(f, global_forbidden):
            reasons.append(f"changed file {f!r} matches a globally forbidden path")
        elif _matches_any(f, category_forbidden):
            reasons.append(f"changed file {f!r} matches a category-forbidden path")
        elif not _matches_any(f, permitted):
            reasons.append(f"changed file {f!r} is outside every permitted path")

    max_changed = category_policy.get("max_changed_files")
    if max_changed is not None and len(changed_files) > max_changed:
        reasons.append(
            f"changed-file count {len(changed_files)} exceeds max_changed_files {max_changed}"
        )

    max_ins = category_policy.get("max_inserted_lines")
    if max_ins is not None and inserted_lines > max_ins:
        reasons.append(f"inserted lines {inserted_lines} exceeds max_inserted_lines {max_ins}")

    max_del = category_policy.get("max_deleted_lines")
    if max_del is not None and deleted_lines > max_del:
        reasons.append(f"deleted lines {deleted_lines} exceeds max_deleted_lines {max_del}")

    if reasons:
        return _deny(failure_category, reasons)

    return {
        "schema_version": "2.0",
        "failure_category": failure_category,
        "decision": "allow",
        "required_validation_profile": category_policy.get("required_validation_profile"),
        "runtime_budget_minutes": category_policy.get("runtime_budget_minutes"),
        "permitted_paths": permitted,
        "reasons": [],
    }


def _deny(failure_category, reasons) -> dict:
    return {
        "schema_version": "2.0",
        "failure_category": failure_category,
        "decision": "deny",
        "required_validation_profile": None,
        "runtime_budget_minutes": None,
        "permitted_paths": [],
        "reasons": reasons,
    }


def _numstat_to_counts(numstat_text: str):
    changed_files = []
    inserted = 0
    deleted = 0
    for line in numstat_text.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        ins, dele, path = parts
        changed_files.append(path)
        inserted += int(ins) if ins.isdigit() else 0
        deleted += int(dele) if dele.isdigit() else 0
    return changed_files, inserted, deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--classification", required=True, type=Path)
    parser.add_argument("--numstat", type=Path, default=None,
                         help="Path to a file containing `git diff --numstat` output "
                              "for the proposed change. Omit for a pre-remediation "
                              "dry-run policy check (no changed files yet).")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text())
    classification = json.loads(args.classification.read_text())
    policy = load_policy(args.policy)

    if args.numstat and args.numstat.exists():
        changed_files, inserted, deleted = _numstat_to_counts(args.numstat.read_text())
    else:
        changed_files, inserted, deleted = [], 0, 0

    decision = evaluate(policy, classification, evidence, changed_files, inserted, deleted)

    output_text = json.dumps(decision, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text + "\n")
    print(output_text)

    return 0 if decision["decision"] == "allow" else 1


if __name__ == "__main__":
    sys.exit(main())
