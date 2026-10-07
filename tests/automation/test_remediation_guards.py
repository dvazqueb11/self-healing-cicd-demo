"""Automation tests for the loop-prevention remediation guards."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _helpers as h  # noqa: E402
import check_remediation_guards as guards  # noqa: E402


def make_context(
    event="pull_request",
    conclusion="failure",
    head_sha="a" * 40,
    head_branch="feature/real-change",
    repository_full_name="acme/self-healing-cicd-demo",
    head_repository_full_name="acme/self-healing-cicd-demo",
    pr_number=42,
    base_ref="main",
    current_pr_head_sha="a" * 40,
    existing_remediation_branch_exists=False,
) -> dict:
    pull_requests = []
    if pr_number is not None:
        pull_requests = [{"number": pr_number, "base_ref": base_ref}]
    return {
        "workflow_run": {
            "event": event,
            "conclusion": conclusion,
            "head_sha": head_sha,
            "head_branch": head_branch,
            "repository_full_name": repository_full_name,
            "head_repository_full_name": head_repository_full_name,
            "pull_requests": pull_requests,
        },
        "current_pr_head_sha": current_pr_head_sha,
        "existing_remediation_branch_exists": existing_remediation_branch_exists,
    }


class RemediationGuardsTests(unittest.TestCase):
    def setUp(self):
        self.policy = h.load_policy()

    def test_allows_a_fresh_in_scope_pull_request_failure(self):
        decision = guards.evaluate_guards(self.policy, make_context())
        self.assertEqual(decision["decision"], "allow")
        self.assertEqual(decision["reasons"], [])
        self.assertEqual(decision["pr_number"], 42)
        self.assertEqual(decision["head_branch"], "feature/real-change")
        self.assertEqual(decision["base_branch"], "main")

    def test_denies_non_pull_request_event(self):
        decision = guards.evaluate_guards(self.policy, make_context(event="push"))
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("in-scope pull_request failure" in r for r in decision["reasons"]))

    def test_denies_non_failure_conclusion(self):
        decision = guards.evaluate_guards(self.policy, make_context(conclusion="success"))
        self.assertEqual(decision["decision"], "deny")

    def test_denies_fork_pull_request_with_no_associated_pr(self):
        decision = guards.evaluate_guards(self.policy, make_context(pr_number=None))
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("same-repository pull request" in r for r in decision["reasons"]))

    def test_denies_fork_pull_request_with_mismatched_repository(self):
        decision = guards.evaluate_guards(
            self.policy, make_context(head_repository_full_name="someone-else/fork"),
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("same-repository pull request" in r for r in decision["reasons"]))

    def test_denies_remediation_branch_loop(self):
        decision = guards.evaluate_guards(
            self.policy, make_context(head_branch="self-heal/abc123-unit-test-failure"),
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("loop guard" in r for r in decision["reasons"]))

    def test_denies_stale_head_sha(self):
        decision = guards.evaluate_guards(
            self.policy, make_context(head_sha="a" * 40, current_pr_head_sha="b" * 40),
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("stale" in r for r in decision["reasons"]))

    def test_denies_duplicate_remediation(self):
        decision = guards.evaluate_guards(
            self.policy, make_context(existing_remediation_branch_exists=True),
        )
        self.assertEqual(decision["decision"], "deny")
        self.assertTrue(any("duplicate guard" in r for r in decision["reasons"]))


if __name__ == "__main__":
    unittest.main()
