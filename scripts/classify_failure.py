#!/usr/bin/env python3
"""Deterministic classifier.

Consumes a normalized, signed evidence document (see
framework/schemas/evidence-schema-v1.json, schema_version "2.0") and
emits a classification JSON document. This script never calls an AI
model: classification is pure rule evaluation over the evidence's own
fields plus the policy file (for permitted paths / validation profile
lookup).

Unlike the original scenario-based classifier, this version is
category-driven: `evidence.failure_category` is trusted only after (a)
schema + signature validation and (b) cross-checking it against the
evidence's own `measurements` for internal consistency (a defense-in-depth
re-check of the same logic scripts/collect_evidence.py used to pick the
category, independent of whether the evidence was collected correctly).

Unknown, conflicting, or incomplete evidence always yields
`failure_category: "unsupported"` with `supported: false` and a
human-readable reason.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "framework" / "schemas"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evidence_lib  # noqa: E402
import simple_yaml  # noqa: E402

DEFAULT_POLICY_PATH = REPO_ROOT / ".github" / "policies" / "self-heal-policy.yml"

# Per-category required measurement keys. Evidence missing these keys is
# incomplete and must be rejected as unsupported.
REQUIRED_MEASUREMENT_KEYS = {
    "unit-test-failure": {"failing_tests"},
    "coverage-gap": {"coverage_percent", "threshold_percent"},
    "performance-regression": {"median_ms", "threshold_ms"},
}

VALIDATION_PROFILE_BY_CATEGORY = {
    "unit-test-failure": "unit-test-remediation",
    "coverage-gap": "coverage-remediation",
    "performance-regression": "performance-remediation",
}


def _category_is_consistent_with_measurements(category: str, measurements: dict) -> bool:
    """Independent re-derivation of "is this category actually what the
    measurements show", so a hand-edited (even if still correctly
    signed, e.g. replayed from a different run) evidence document can't
    claim a category its own numbers don't support."""
    if category == "unit-test-failure":
        return bool(measurements.get("failing_tests"))
    if category == "coverage-gap":
        percent = measurements.get("coverage_percent")
        threshold = measurements.get("threshold_percent")
        changed = measurements.get("changed_line_coverage") or {}
        if percent is None or threshold is None:
            return False
        return percent < threshold or changed.get("passed") is False
    if category == "performance-regression":
        median = measurements.get("median_ms")
        threshold = measurements.get("threshold_ms")
        if median is None or threshold is None:
            return False
        return median > threshold
    return False


def classify(evidence: dict, policy: dict) -> dict:
    schema_errors = evidence_lib.validate_evidence(evidence)
    if schema_errors:
        return _unsupported(
            f"evidence failed schema/signature validation: {'; '.join(schema_errors)}",
        )

    reported_category = evidence["failure_category"]
    if reported_category == "unsupported":
        return _unsupported("evidence itself reports failure_category 'unsupported' "
                             "(no deterministic check failed)")

    required_keys = REQUIRED_MEASUREMENT_KEYS.get(reported_category, set())
    measurements = evidence.get("measurements", {})
    missing = sorted(
        key for key in required_keys
        if measurements.get(key) is None
    )
    if missing:
        return _unsupported(
            f"measurements missing or null for required keys of {reported_category!r}: {missing}",
        )

    if not _category_is_consistent_with_measurements(reported_category, measurements):
        return _unsupported(
            f"evidence failure_category {reported_category!r} is not supported by its own "
            "measurements (re-derivation disagrees)",
        )

    if not evidence.get("relevant_files"):
        return _unsupported("evidence has no relevant_files to examine")

    category_policy = policy.get("categories", {}).get(reported_category, {})
    permitted_scope = category_policy.get("permitted_paths", [])

    return {
        "schema_version": "2.0",
        "failure_category": reported_category,
        "failure_signature": evidence["failure_signature"],
        "supported": True,
        "relevant_files": evidence["relevant_files"],
        "permitted_remediation_scope": permitted_scope,
        "confidence": "deterministic",
        "reason": "evidence is schema-valid, signed, and internally consistent "
                  "with its own measurements for the reported failure_category",
        "validation_profile": VALIDATION_PROFILE_BY_CATEGORY[reported_category],
    }


def _unsupported(reason: str) -> dict:
    return {
        "schema_version": "2.0",
        "failure_category": "unsupported",
        "failure_signature": None,
        "supported": False,
        "relevant_files": [],
        "permitted_remediation_scope": [],
        "confidence": "deterministic",
        "reason": reason,
        "validation_profile": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text())
    policy = simple_yaml.load_file(str(args.policy))

    result = classify(evidence, policy)

    output_text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text + "\n")
    print(output_text)

    return 0 if result["supported"] else 1


if __name__ == "__main__":
    sys.exit(main())
