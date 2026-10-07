"""Automation tests for the public-repo scanner.

Runs scripts/check_public_repo.py's underlying functions against a
disposable temporary git repository so tests can safely commit
"bad" content (fake secrets, personal emails) without touching the
real repository.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCANNER_PATH = REPO_ROOT / "scripts" / "check_public_repo.py"

spec = importlib.util.spec_from_file_location("check_public_repo", SCANNER_PATH)
check_public_repo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_public_repo)


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


class PublicRepoScanTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmpdir.name)
        _run(["git", "init", "-q"], cwd=self.repo)
        _run(["git", "config", "user.email", "demo@example.invalid"], cwd=self.repo)
        _run(["git", "config", "user.name", "Test"], cwd=self.repo)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _commit_file(self, relpath: str, content: str):
        path = self.repo / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        _run(["git", "add", relpath], cwd=self.repo)
        _run(["git", "commit", "-q", "-m", f"add {relpath}"], cwd=self.repo)

    def _scan(self):
        # Reuse the scanner's scan_file logic but against the temp repo's
        # tracked files, not REPO_ROOT.
        check_public_repo.REPO_ROOT = self.repo
        findings = []
        for path in check_public_repo.tracked_files():
            findings.extend(check_public_repo.scan_file(path))
        check_public_repo.REPO_ROOT = REPO_ROOT
        return findings

    def test_clean_repo_has_no_findings(self):
        self._commit_file("README.md", "# A perfectly ordinary demo repo\n")
        self.assertEqual(self._scan(), [])

    def test_detects_generic_secret_assignment(self):
        self._commit_file("config.txt", 'api_key = "zzFAKEzzNOTREALzzSECRETzz1234567890"\n')
        findings = self._scan()
        self.assertTrue(any("secret" in f.lower() or "assignment" in f.lower() for f in findings))

    def test_detects_aws_key(self):
        self._commit_file("notes.txt", "AKIAABCDEFGHIJKLMNOP\n")
        findings = self._scan()
        self.assertTrue(any("AWS" in f for f in findings))

    def test_detects_private_key_block(self):
        self._commit_file("key.pem", "-----BEGIN RSA PRIVATE KEY-----\nMIIBogIBAAJ...\n")
        findings = self._scan()
        self.assertTrue(any("Private key" in f for f in findings))

    def test_detects_non_placeholder_email(self):
        self._commit_file("contact.txt", "Reach out to jane.doe@realcompany.com\n")
        findings = self._scan()
        self.assertTrue(any("email address" in f for f in findings))

    def test_allows_placeholder_email_domains(self):
        self._commit_file("contact.txt", "Reach out to demo@example.invalid\n")
        self.assertEqual(self._scan(), [])

    def test_allows_github_noreply_email(self):
        self._commit_file("AUTHORS.md", "Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>\n")
        self.assertEqual(self._scan(), [])

    def test_detects_internal_hostname_reference(self):
        self._commit_file("deploy.md", "See https://ci.internal.corp/jobs/123 for details\n")
        findings = self._scan()
        self.assertTrue(any("internal hostname" in f for f in findings))

    def test_real_repository_passes_the_scan(self):
        """The actual repository being prepared for a public push must
        itself be clean; this is the same check `make public-check` runs."""
        result = subprocess.run(
            [sys.executable, str(SCANNER_PATH)], cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
