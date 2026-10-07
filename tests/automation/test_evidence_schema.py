"""Automation tests for the evidence schema validator."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _helpers as h  # noqa: E402
import evidence_lib  # noqa: E402


class EvidenceSchemaTests(unittest.TestCase):
    def test_valid_evidence_has_no_errors(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure",
                              {"failing_tests": ["average_empty_input"]})
        self.assertEqual(evidence_lib.validate_evidence(ev), [])

    def test_missing_required_field_is_rejected(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        del ev["head_sha"]
        errors = evidence_lib.validate_evidence(ev)
        self.assertTrue(any("head_sha" in e for e in errors))

    def test_unknown_scenario_is_rejected(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        ev = h.resign({**ev, "scenario": "not-a-real-scenario"})
        errors = evidence_lib.validate_evidence(ev)
        self.assertTrue(any("unknown scenario" in e for e in errors))

    def test_scenario_is_optional(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        ev = h.resign({**ev, "scenario": None})
        self.assertEqual(evidence_lib.validate_evidence(ev), [])

    def test_unknown_failure_category_is_rejected(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        ev = h.resign({**ev, "failure_category": "not-a-real-category"})
        errors = evidence_lib.validate_evidence(ev)
        self.assertTrue(any("unknown failure_category" in e for e in errors))

    def test_invalid_head_sha_is_rejected(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        ev = h.resign({**ev, "head_sha": "not-hex!!"})
        errors = evidence_lib.validate_evidence(ev)
        self.assertTrue(any("head_sha" in e for e in errors))

    def test_invalid_pr_number_is_rejected(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        ev = h.resign({**ev, "pr_number": 0})
        errors = evidence_lib.validate_evidence(ev)
        self.assertTrue(any("pr_number" in e for e in errors))

    def test_oversized_changed_files_is_rejected(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        ev = h.resign({**ev, "changed_files": [f"file_{i}.cpp" for i in range(evidence_lib.MAX_CHANGED_FILES + 1)]})
        errors = evidence_lib.validate_evidence(ev)
        self.assertTrue(any("changed_files exceeds limit" in e for e in errors))

    def test_attempt_number_must_be_positive_int(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        ev = h.resign({**ev, "attempt_number": 0})
        errors = evidence_lib.validate_evidence(ev)
        self.assertTrue(any("attempt_number" in e for e in errors))

    def test_tampered_content_with_stale_signature_is_rejected(self):
        """A field changed without recomputing the signature (the actual
        tamper scenario the signature exists to catch) must be rejected,
        unlike the other negative tests above which deliberately resign
        after mutating, to test the *other* validation rules in isolation."""
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        tampered = dict(ev)
        tampered["failure_category"] = "coverage-gap"
        errors = evidence_lib.validate_evidence(tampered)
        self.assertTrue(any("signature does not match" in e for e in errors))

    def test_malformed_signature_is_rejected(self):
        ev = h.base_evidence("easy-unit-test", "unit-test-failure", {})
        ev["signature"] = "not-a-sha256-digest"
        errors = evidence_lib.validate_evidence(ev)
        self.assertTrue(any("signature must be a 64-character hex sha256 digest" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
