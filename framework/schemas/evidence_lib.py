#!/usr/bin/env python3
"""Shared constants and a small, dependency-free evidence validator.

This intentionally does not implement a general JSON Schema interpreter.
`framework/schemas/evidence-schema-v1.json` is the documented, canonical
schema; this module enforces the same constraints in plain Python so the
framework has zero third-party dependencies. If the two ever disagree,
the JSON schema file is documentation and this module is the enforced
contract used by CI.
"""
from __future__ import annotations

from typing import Any, Dict, List

SCHEMA_VERSION = "1.0"

SCENARIOS = {"easy-unit-test", "medium-low-coverage", "advanced-performance"}

FAILURE_CATEGORIES = {
    "unit-test-failure",
    "coverage-gap",
    "performance-regression",
    "unsupported",
}

REQUIRED_FIELDS = [
    "schema_version",
    "scenario",
    "event_source",
    "repository",
    "branch",
    "triggering_sha",
    "workflow_run",
    "changed_files",
    "diff_file",
    "failure_category",
    "failed_command",
    "failure_signature",
    "concise_log_file",
    "relevant_files",
    "measurements",
    "runtime_budget",
    "attempt_number",
]

# Evidence passed to the remediation agent must stay small and normalized.
# These limits are deliberately conservative for a small demo repository.
MAX_CONCISE_LOG_CHARS = 4000
MAX_DIFF_CHARS = 20000
MAX_CHANGED_FILES = 50


def validate_evidence(evidence: Dict[str, Any]) -> List[str]:
    """Validate an evidence document. Returns a list of error strings;
    the document is valid iff the list is empty."""
    errors: List[str] = []

    for field in REQUIRED_FIELDS:
        if field not in evidence:
            errors.append(f"missing required field: {field}")

    if errors:
        # Avoid cascading type errors below when required fields are absent.
        return errors

    if evidence["schema_version"] != SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version: {evidence['schema_version']!r} "
            f"(expected {SCHEMA_VERSION!r})"
        )

    if evidence["scenario"] not in SCENARIOS:
        errors.append(f"unknown scenario: {evidence['scenario']!r}")

    if evidence["failure_category"] not in FAILURE_CATEGORIES:
        errors.append(f"unknown failure_category: {evidence['failure_category']!r}")

    sha = evidence["triggering_sha"]
    if not isinstance(sha, str) or not (7 <= len(sha) <= 40) or not all(
        c in "0123456789abcdef" for c in sha
    ):
        errors.append(f"invalid triggering_sha: {sha!r}")

    if not isinstance(evidence["changed_files"], list):
        errors.append("changed_files must be a list")
    elif len(evidence["changed_files"]) > MAX_CHANGED_FILES:
        errors.append(
            f"changed_files exceeds limit of {MAX_CHANGED_FILES} entries "
            "(oversized diffs are rejected, not summarized further)"
        )

    if not isinstance(evidence["relevant_files"], list):
        errors.append("relevant_files must be a list")

    if not isinstance(evidence["measurements"], dict):
        errors.append("measurements must be an object")

    budget = evidence["runtime_budget"]
    if not isinstance(budget, dict) or "target_minutes" not in budget:
        errors.append("runtime_budget must be an object with target_minutes")

    attempt = evidence["attempt_number"]
    if not isinstance(attempt, int) or attempt < 1:
        errors.append("attempt_number must be an integer >= 1")

    return errors
