"""Shared test helpers for the automation test suite.

All tests import scripts/framework modules directly (no packaging,
matching the rest of this dependency-free framework) and operate on
temporary copies of fixtures / policy data so they never depend on or
mutate the real git working tree.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "framework" / "schemas"))

import evaluate_policy  # noqa: E402
import classify_failure  # noqa: E402
import evidence_lib  # noqa: E402


def load_policy():
    return evaluate_policy.load_policy()


def base_evidence(scenario: str, failure_category: str, measurements: dict,
                   relevant_files=None, attempt_number: int = 1) -> dict:
    """Build a minimal, schema-valid evidence document for a given
    demo scenario/category, for use as a starting point in classifier and
    policy-engine tests. Callers can mutate individual fields (and must
    call `resign(doc)` afterwards) to construct negative test cases.

    `scenario` is purely provenance here (which fixture produced this
    evidence in a test or demo run); classification and policy decisions
    never depend on it."""
    doc = {
        "schema_version": evidence_lib.SCHEMA_VERSION,
        "scenario": scenario,
        "event_source": "test-harness",
        "repository": "local/self-healing-cicd-demo",
        "pr_number": 1,
        "base_branch": "main",
        "base_sha": "1" * 40,
        "head_branch": f"demo/{scenario}/test-run",
        "head_sha": "0" * 40,
        "workflow_run_id": "123456789",
        "changed_files": ["src/job_processor.cpp"],
        "diff_file": ".evidence/diff.patch",
        "failure_category": failure_category,
        "failed_command": "test-command",
        "failure_signature": f"{scenario}:{failure_category}:test",
        "concise_log_file": ".evidence/failure_log.txt",
        "relevant_files": relevant_files if relevant_files is not None else ["src/job_processor.cpp"],
        "measurements": measurements,
        "runtime_budget": {"target_minutes": 10, "elapsed_minutes": 1},
        "attempt_number": attempt_number,
    }
    return resign(doc)


def resign(doc: dict) -> dict:
    """Recompute the tamper-evidence signature after mutating a test
    evidence document, so it remains schema-valid unless the test is
    deliberately constructing a signature-mismatch negative case."""
    doc = dict(doc)
    doc["signature"] = evidence_lib.compute_signature(doc)
    return doc



def clone(doc: dict) -> dict:
    return copy.deepcopy(doc)
