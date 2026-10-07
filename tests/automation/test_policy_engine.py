"""Automation tests for the deterministic policy engine."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _helpers as h  # noqa: E402
import evaluate_policy  # noqa: E402


SUPPORTED_CLASSIFICATION = {
    "supported": True,
    "reason": "ok",
}

UNSUPPORTED_CLASSIFICATION = {
    "supported": False,
    "reason": "classifier could not confirm the evidence",
}


class PolicyEngineTests(unittest.TestCase):
    def setUp(self):
        self.policy = h.load_policy()

    def test_allows_change_within_scope_and_limits(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev,
            ["src/job_processor.cpp"], inserted_lines=3, deleted_lines=0,
        )
        self.assertEqual(decision["decision"], "allow")
        self.assertEqual(decision["reasons"], [])
        self.assertEqual(decision["required_validation_profile"], "unit-test-remediation")

    def test_denies_when_classifier_marked_unsupported(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        decision = evaluate_policy.evaluate(
            self.policy, UNSUPPORTED_CLASSIFICATION, ev, [], 0, 0,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("unsupported" in r for r in decision["reasons"]))

    def test_denies_globally_forbidden_path(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev,
            ["CMakeLists.txt"], inserted_lines=1, deleted_lines=1,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("globally forbidden" in r for r in decision["reasons"]))

    def test_denies_scenario_forbidden_path(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev,
            ["tests/job_processor_tests.cpp"], inserted_lines=1, deleted_lines=1,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("scenario-forbidden" in r for r in decision["reasons"]))

    def test_denies_path_outside_permitted_scope(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev,
            ["app/main.cpp"], inserted_lines=1, deleted_lines=1,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("outside every permitted path" in r for r in decision["reasons"]))

    def test_denies_oversized_diff(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev,
            ["src/job_processor.cpp"], inserted_lines=500, deleted_lines=500,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("exceeds max_inserted_lines" in r for r in decision["reasons"]))
        self.assertTrue(any("exceeds max_deleted_lines" in r for r in decision["reasons"]))

    def test_denies_too_many_changed_files(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev,
            ["src/job_processor.cpp", "include/job_processor.hpp", "app/main.cpp"],
            inserted_lines=3, deleted_lines=0,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("exceeds max_changed_files" in r for r in decision["reasons"]))

    def test_denies_second_attempt(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]}, attempt_number=2)
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev,
            ["src/job_processor.cpp"], inserted_lines=3, deleted_lines=0,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("exceeds max_attempts" in r for r in decision["reasons"]))

    def test_denies_category_mismatch(self):
        ev = h.base_evidence("easy-unit-test", "coverage-gap",
                              {"coverage_percent": 90.0, "threshold_percent": 95.0})
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev,
            ["src/job_processor.cpp"], inserted_lines=3, deleted_lines=0,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("does not match" in r for r in decision["reasons"]))

    def test_denies_runtime_budget_exceeded(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        ev["runtime_budget"]["elapsed_minutes"] = 999
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev,
            ["src/job_processor.cpp"], inserted_lines=3, deleted_lines=0,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("exceeds budget" in r for r in decision["reasons"]))

    def test_denies_unknown_scenario(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        ev["scenario"] = "no-such-scenario"
        decision = evaluate_policy.evaluate(
            self.policy, SUPPORTED_CLASSIFICATION, ev, [], 0, 0,
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("no policy defined" in r for r in decision["reasons"]))

    def test_numstat_parsing(self):
        numstat = "3\t0\tsrc/job_processor.cpp\n1\t1\tinclude/job_processor.hpp\n"
        changed, inserted, deleted = evaluate_policy._numstat_to_counts(numstat)
        self.assertEqual(sorted(changed), ["include/job_processor.hpp", "src/job_processor.cpp"])
        self.assertEqual(inserted, 4)
        self.assertEqual(deleted, 1)


if __name__ == "__main__":
    unittest.main()
