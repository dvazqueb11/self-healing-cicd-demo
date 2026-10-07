#!/usr/bin/env python3
"""Deterministic classifier.

Consumes a normalized evidence document (see
framework/schemas/evidence-schema-v1.json) and emits a classification
JSON document. This script never calls an AI model: classification is
pure rule evaluation over the evidence's own fields plus the policy
file (for permitted paths / validation profile lookup).

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

# Deterministic mapping of scenario -> expected failure category. This is
# a fixed lookup table, not inference: each scenario in this repository is
# defined to produce exactly one failure category.
SCENARIO_EXPECTED_CATEGORY = {
    "easy-unit-test": "unit-test-failure",
    "medium-low-coverage": "coverage-gap",
    "advanced-performance": "performance-regression",
}

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


def classify(evidence: dict, policy: dict) -> dict:
    schema_errors = evidence_lib.validate_evidence(evidence)
    if schema_errors:
        return _unsupported(
            evidence.get("scenario"),
            f"evidence failed schema validation: {'; '.join(schema_errors)}",
        )

    scenario = evidence["scenario"]
    expected_category = SCENARIO_EXPECTED_CATEGORY.get(scenario)
    if expected_category is None:
        return _unsupported(scenario, f"no known category mapping for scenario {scenario!r}")

    reported_category = evidence["failure_category"]
    if reported_category != expected_category:
        return _unsupported(
            scenario,
            f"evidence failure_category {reported_category!r} conflicts with the "
            f"category expected for scenario {scenario!r} ({expected_category!r})",
        )

    required_keys = REQUIRED_MEASUREMENT_KEYS.get(reported_category, set())
    measurements = evidence.get("measurements", {})
    missing = sorted(required_keys - set(measurements.keys()))
    if missing:
        return _unsupported(
            scenario,
            f"measurements missing required keys for {reported_category!r}: {missing}",
        )

    if not evidence.get("relevant_files"):
        return _unsupported(scenario, "evidence has no relevant_files to examine")

    scenario_policy = policy.get("scenarios", {}).get(scenario, {})
    permitted_scope = scenario_policy.get("permitted_paths", [])

    return {
        "schema_version": "1.0",
        "scenario": scenario,
        "failure_category": reported_category,
        "failure_signature": evidence["failure_signature"],
        "supported": True,
        "relevant_files": evidence["relevant_files"],
        "permitted_remediation_scope": permitted_scope,
        "confidence": "deterministic",
        "reason": "evidence is complete, consistent, and matches the expected "
                  "category for this scenario",
        "validation_profile": VALIDATION_PROFILE_BY_CATEGORY[reported_category],
    }


def _unsupported(scenario, reason: str) -> dict:
    return {
        "schema_version": "1.0",
        "scenario": scenario,
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
