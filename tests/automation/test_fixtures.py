"""Automation tests for fixture apply/reset, run in an isolated git
worktree so they never touch the real repository's working tree or
branches.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

KNOWN_SCENARIOS = ["easy-unit-test", "medium-low-coverage", "advanced-performance"]


def _run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"{' '.join(cmd)} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout


class FixtureApplyResetTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.worktree = Path(self._tmpdir.name) / "worktree"
        _run(["git", "worktree", "add", "--detach", str(self.worktree), "main"], cwd=REPO_ROOT)

    def tearDown(self):
        _run(["git", "worktree", "remove", "--force", str(self.worktree)], cwd=REPO_ROOT)
        self._tmpdir.cleanup()

    def test_every_fixture_applies_and_resets_cleanly(self):
        for scenario in KNOWN_SCENARIOS:
            with self.subTest(scenario=scenario):
                apply_result = subprocess.run(
                    [sys.executable, str(self.worktree / "scripts" / "create_demo_failure.py"), scenario],
                    cwd=self.worktree, capture_output=True, text=True,
                )
                self.assertEqual(apply_result.returncode, 0, apply_result.stderr)

                status_after_apply = _run(["git", "status", "--short"], cwd=self.worktree)
                self.assertTrue(status_after_apply.strip(), "fixture apply produced no changes")

                reset_result = subprocess.run(
                    [sys.executable, str(self.worktree / "scripts" / "reset_demo.py"), scenario],
                    cwd=self.worktree, capture_output=True, text=True,
                )
                self.assertEqual(reset_result.returncode, 0, reset_result.stderr)

                status_after_reset = _run(["git", "status", "--short"], cwd=self.worktree)
                self.assertEqual(status_after_reset.strip(), "", "reset did not restore a clean tree")

    def test_fixture_check_mode_does_not_modify_tree(self):
        result = subprocess.run(
            [sys.executable, str(self.worktree / "scripts" / "create_demo_failure.py"),
             "easy-unit-test", "--check"],
            cwd=self.worktree, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        status = _run(["git", "status", "--short"], cwd=self.worktree)
        self.assertEqual(status.strip(), "")

    def test_unknown_scenario_is_rejected_by_argparse(self):
        result = subprocess.run(
            [sys.executable, str(self.worktree / "scripts" / "create_demo_failure.py"), "not-a-scenario"],
            cwd=self.worktree, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
