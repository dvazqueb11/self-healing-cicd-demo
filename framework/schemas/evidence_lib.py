#!/usr/bin/env python3
"""Shared constants and a small, dependency-free evidence validator.

This intentionally does not implement a general JSON Schema interpreter.
`framework/schemas/evidence-schema-v1.json` is the documented, canonical
schema; this module enforces the same constraints in plain Python so the
framework has zero third-party dependencies. If the two ever disagree,
the JSON schema file is documentation and this module is the enforced
contract used by CI.

Schema version 2.0: evidence is keyed by a real pull request (repository,
PR number, base/head branch+SHA, workflow run id), not by a fixture
scenario id. `scenario` is retained as an optional, nullable field purely
for the provenance of the optional demo-fixture helper scripts; the
classifier, policy engine, and validator never key any decision on it.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

SCHEMA_VERSION = "2.0"

# Demo-fixture scenario ids. Only meaningful for the optional `scenario`
# provenance field written by scripts/create_demo_failure.py /
# scripts/demo_submit_pr.py; never used to drive a classification or
# policy decision.
SCENARIOS = {"easy-unit-test", "medium-low-coverage", "advanced-performance"}

FAILURE_CATEGORIES = {
    "unit-test-failure",
    "coverage-gap",
    "performance-regression",
    "unsupported",
}

REQUIRED_FIELDS = [
    "schema_version",
    "event_source",
    "repository",
    "pr_number",
    "base_branch",
    "base_sha",
    "head_branch",
    "head_sha",
    "workflow_run_id",
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
    "signature",
]

# Evidence passed to the remediation agent must stay small and normalized.
# These limits are deliberately conservative for a small demo repository.
MAX_CONCISE_LOG_CHARS = 4000
MAX_DIFF_CHARS = 20000
MAX_CHANGED_FILES = 50

_SHA_HEX = "0123456789abcdef"


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and 7 <= len(value) <= 40 and all(c in _SHA_HEX for c in value)


def canonical_signing_bytes(evidence: Dict[str, Any]) -> bytes:
    """Deterministic byte representation of every field except
    `signature` itself, used both to compute and to verify the
    evidence's integrity signature."""
    payload = {k: v for k, v in evidence.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_signature(evidence: Dict[str, Any]) -> str:
    """A sha256 digest over every other field, computed by the evidence
    collector in the same trusted CI job that measured the failure.

    This is tamper-evidence, not a cryptographic guarantee of authorship:
    it detects accidental corruption/truncation of the artifact in
    transit and any attempt to hand-edit evidence.json after collection
    without also recomputing a matching signature. Combined with the
    remediation workflow's independent checks against the GitHub API
    (run belongs to this repository, was not a fork, conclusion was
    failure, head SHA matches the live PR), this is sufficient for this
    demo's documented threat model. See docs/architecture.md#known-limitations.
    """
    return hashlib.sha256(canonical_signing_bytes(evidence)).hexdigest()


def verify_signature(evidence: Dict[str, Any]) -> bool:
    signature = evidence.get("signature")
    if not isinstance(signature, str):
        return False
    return signature == compute_signature(evidence)


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

    scenario = evidence.get("scenario")
    if scenario is not None and scenario not in SCENARIOS:
        errors.append(f"unknown scenario: {scenario!r}")

    if evidence["failure_category"] not in FAILURE_CATEGORIES:
        errors.append(f"unknown failure_category: {evidence['failure_category']!r}")

    if not isinstance(evidence["pr_number"], int) or evidence["pr_number"] < 1:
        errors.append(f"invalid pr_number: {evidence['pr_number']!r}")

    for sha_field in ("base_sha", "head_sha"):
        value = evidence[sha_field]
        if not _is_sha(value):
            errors.append(f"invalid {sha_field}: {value!r}")

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

    signature = evidence["signature"]
    if not isinstance(signature, str) or len(signature) != 64 or not all(
        c in _SHA_HEX for c in signature
    ):
        errors.append("signature must be a 64-character hex sha256 digest")
    elif not verify_signature(evidence):
        errors.append("signature does not match the evidence content (tampered or corrupted)")

    return errors
