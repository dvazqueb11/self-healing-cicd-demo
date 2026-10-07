"""Automation tests for the deterministic classifier."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _helpers as h  # noqa: E402
import classify_failure  # noqa: E402


class ClassifierTests(unittest.TestCase):
    def setUp(self):
        self.policy = h.load_policy()

    def test_unit_test_failure_is_supported(self):
        ev = h.base_evidence(
            "easy-unit-test", "unit-test-failure",
            {"failing_tests": ["average_empty_input"]},
        )
        result = classify_failure.classify(ev, self.policy)
        self.assertTrue(result["supported"])
        self.assertEqual(result["failure_category"], "unit-test-failure")
        self.assertEqual(result["validation_profile"], "unit-test-remediation")
        self.assertEqual(result["confidence"], "deterministic")

    def test_coverage_gap_is_supported(self):
        ev = h.base_evidence(
            "medium-low-coverage", "coverage-gap",
            {"coverage_percent": 93.88, "threshold_percent": 95.0},
            relevant_files=["src/job_processor.cpp", "tests/"],
        )
        result = classify_failure.classify(ev, self.policy)
        self.assertTrue(result["supported"])
        self.assertEqual(result["validation_profile"], "coverage-remediation")

    def test_performance_regression_is_supported(self):
        ev = h.base_evidence(
            "advanced-performance", "performance-regression",
            {"median_ms": 468.4, "threshold_ms": 200.0},
        )
        result = classify_failure.classify(ev, self.policy)
        self.assertTrue(result["supported"])
        self.assertEqual(result["validation_profile"], "performance-remediation")

    def test_schema_invalid_evidence_is_unsupported(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        del ev["head_sha"]
        result = classify_failure.classify(ev, self.policy)
        self.assertFalse(result["supported"])
        self.assertIn("schema/signature validation", result["reason"])

    def test_category_measurement_mismatch_is_unsupported(self):
        """Claiming coverage-gap while the measurements show coverage
        already meets the threshold must be rejected: the independent
        re-derivation of category from measurements disagrees with the
        evidence's own claimed failure_category."""
        ev = h.base_evidence(
            "medium-low-coverage", "coverage-gap",
            {"coverage_percent": 97.0, "threshold_percent": 95.0},
            relevant_files=["src/job_processor.cpp", "tests/"],
        )
        result = classify_failure.classify(ev, self.policy)
        self.assertFalse(result["supported"])
        self.assertIn("not supported by its own measurements", result["reason"])

    def test_missing_required_measurement_is_unsupported(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        result = classify_failure.classify(ev, self.policy)
        self.assertFalse(result["supported"])
        self.assertIn("missing or null", result["reason"])

    def test_null_required_measurement_is_unsupported(self):
        ev = h.base_evidence(
            "medium-low-coverage", "coverage-gap",
            {"coverage_percent": None, "threshold_percent": 95.0},
            relevant_files=["src/job_processor.cpp", "tests/"],
        )
        result = classify_failure.classify(ev, self.policy)
        self.assertFalse(result["supported"])
        self.assertIn("missing or null", result["reason"])

    def test_empty_relevant_files_is_unsupported(self):
        ev = h.base_evidence(
            "easy-unit-test", "unit-test-failure",
            {"failing_tests": ["average_empty_input"]},
            relevant_files=[],
        )
        result = classify_failure.classify(ev, self.policy)
        self.assertFalse(result["supported"])
        self.assertIn("relevant_files", result["reason"])

    def test_scenario_field_does_not_affect_classification(self):
        """`scenario` is provenance-only: classification must depend only
        on failure_category and measurements, never on which fixture (if
        any) produced the evidence."""
        ev = h.base_evidence(
            "easy-unit-test", "unit-test-failure",
            {"failing_tests": ["average_empty_input"]},
        )
        ev = h.resign({**ev, "scenario": "medium-low-coverage"})
        result = classify_failure.classify(ev, self.policy)
        self.assertTrue(result["supported"])
        self.assertEqual(result["failure_category"], "unit-test-failure")

    def test_reported_unsupported_category_is_unsupported(self):
        ev = h.base_evidence("easy-unit-test", "unsupported", {})
        result = classify_failure.classify(ev, self.policy)
        self.assertFalse(result["supported"])
        self.assertIn("reports failure_category 'unsupported'", result["reason"])


if __name__ == "__main__":
    unittest.main()
