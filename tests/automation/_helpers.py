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
    scenario/category, for use as a starting point in classifier and
    policy-engine tests. Callers can mutate individual fields to
    construct negative test cases."""
    return {
        "schema_version": evidence_lib.SCHEMA_VERSION,
        "scenario": scenario,
        "event_source": "test-harness",
        "repository": "local/self-healing-cicd-demo",
        "branch": f"demo/{scenario}/test-run",
        "triggering_sha": "0" * 40,
        "workflow_run": "test-run",
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


def clone(doc: dict) -> dict:
    return copy.deepcopy(doc)
