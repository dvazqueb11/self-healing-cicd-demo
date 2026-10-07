# Security Policy

This repository is a **demonstration project**: a self-contained example of
combining deterministic GitHub Actions with bounded, policy-gated AI
remediation (GitHub Agentic Workflows). It is not a production service and
does not process customer data.

## Supported versions

There are no released versions; `main` is the only maintained branch.

## Reporting a vulnerability

If you find a security issue in this repository (for example, a way to make
the self-heal remediation agent exceed its declared permissions, bypass
`scripts/validate_change.py`, or touch a path listed as
`globally_forbidden_paths` in `.github/policies/self-heal-policy.yml`),
please open a private report using GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
feature on this repository ("Security" tab → "Report a vulnerability")
instead of opening a public issue.

## Scope notes

- The AI remediation workflow (`.github/workflows/self-heal-remediation.md`)
  never has direct write access to the repository; it can only request a
  pull request or issue via gh-aw's "safe outputs" mechanism, and every
  pull request requires human review and approval before merge.
- Known, accepted limitations of this demo (not vulnerabilities) are
  documented in `docs/architecture.md#known-limitations`, including the fact
  that `.evidence/` is a same-job, same-trust-boundary artifact rather than
  a tamper-proof artifact passed across a trust boundary.
