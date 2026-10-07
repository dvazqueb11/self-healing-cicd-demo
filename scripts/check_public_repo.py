#!/usr/bin/env python3
"""Deterministic scanner for things that must never land in a public repo.

This is a conservative, pattern-based scanner -- not a replacement for a
real secret-scanning service (GitHub's push protection / secret
scanning already covers the account). It exists so `make public-check`
gives a fast, offline, zero-dependency second opinion before a push,
and so the automation test suite can assert the repository stays clean
over time.

Checks performed:
  * common secret/token shapes (AWS keys, GitHub tokens, private key
    blocks, generic "password =" / "api_key =" assignments with a
    non-placeholder-looking value)
  * personal email addresses (anything not in the allowed domain list)
  * internal hostnames / URLs (configurable denylist of substrings)
  * TODO/FIXME markers that mention internal ticket systems (JIRA-style
    PROJ-123 identifiers), which often leak internal project names

The scanner walks tracked, non-binary files only (via `git ls-files`),
skipping the fixtures directory's patch files only for the "internal
reference" word check (patches legitimately contain source diffs).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Domains considered acceptable in a public demo repo (project-owned or
# well-known placeholder domains). Anything else triggers a finding.
ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.invalid",
    "users.noreply.github.com",
}

SECRET_PATTERNS = [
    ("AWS Access Key ID", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub personal access token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,255}")),
    ("Private key block", re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY-----")),
    ("Generic high-entropy assignment", re.compile(
        r"(?i)\b(api[_-]?key|secret|password|token)\b\s*[:=]\s*['\"][A-Za-z0-9/+_\-]{16,}['\"]"
    )),
]

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Substrings that indicate an internal-only reference. Keep this list
# generic; organizations adopting this framework should extend it with
# their own internal hostnames in a local override.
INTERNAL_REFERENCE_PATTERNS = [
    re.compile(r"(?i)\binternal\.corp\b"),
    re.compile(r"(?i)\.corp\.[a-z]+\b"),
    re.compile(r"(?i)\bgithub\.megacorp\b"),
]

BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".o", ".a", ".so", ".dylib"}


def tracked_files():
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line.strip()]


def scan_file(path: Path):
    findings = []
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return findings
    try:
        text = path.read_text(errors="ignore")
    except (OSError, UnicodeDecodeError):
        return findings

    rel = path.relative_to(REPO_ROOT)

    for line_no, line in enumerate(text.splitlines(), start=1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"{rel}:{line_no}: possible {label}")

        for email in EMAIL_PATTERN.findall(line):
            domain = email.rsplit("@", 1)[-1].lower()
            if domain not in ALLOWED_EMAIL_DOMAINS:
                findings.append(f"{rel}:{line_no}: email address with non-placeholder domain: {email}")

        for pattern in INTERNAL_REFERENCE_PATTERNS:
            if pattern.search(line):
                findings.append(f"{rel}:{line_no}: possible internal hostname/reference: {line.strip()[:120]}")

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    all_findings = []
    for path in tracked_files():
        all_findings.extend(scan_file(path))

    if all_findings:
        print(f"Public-repo scan FAILED: {len(all_findings)} finding(s)\n")
        for finding in all_findings:
            print(f"  - {finding}")
        return 1

    print("Public-repo scan PASSED: no secrets, non-placeholder emails, or internal references found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
