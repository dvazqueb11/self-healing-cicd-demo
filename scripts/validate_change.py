#!/usr/bin/env python3
"""Deterministic post-remediation validation profiles.

Each profile re-runs the relevant deterministic checks against the
remediation agent's proposed change and runs a set of "anti-weakening"
checks that verify the agent did not take a shortcut (deleting tests,
loosening thresholds, touching forbidden files, etc).

A remediation is successful only when every check in its profile passes.
This script performs no AI reasoning.

Diff bases used by this script are intentionally two different commits:

  - Patch-scope / anti-weakening checks always diff the remediation
    against `evidence.head_sha` (the exact failing commit the agent
    started from), never against `main` or `evidence.base_sha` -- the
    *developer's* pull request may itself touch paths that would be
    forbidden for the *remediation* to re-touch, so diffing against
    anything earlier than the failing commit would incorrectly blame
    the agent for the original PR's own changes.
  - The coverage profile's changed-line-coverage check diffs against
    `evidence.base_sha` (the original PR's base commit) instead, because
    the question there is "did the developer's own new production code
    get covered by the agent's new tests", which is only answerable
    relative to the PR's own base, not the failing commit the agent
    started from.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evaluate_policy  # noqa: E402
import measure_coverage  # noqa: E402

# The fixed set of unit-test names that must always be present (and
# passing) for the unit-test and performance-remediation profiles. A
# remediation that deletes, skips, or disables one of these is rejected,
# regardless of whether the build or exit code otherwise looks fine.
REQUIRED_TEST_NAMES = {
    "average_empty_input",
    "average_normal_input",
    "average_negative_values",
    "duplicates_empty_input",
    "duplicates_no_duplicates",
    "duplicates_repeated_values",
    "duplicates_deterministic_ordering",
    "summary_empty_input",
    "summary_small_job",
    "summary_medium_job",
    "summary_large_job",
}

PRODUCTION_PATHS = ("src/", "include/")
COVERAGE_CONFIG_PATHS = ("scripts/measure_coverage.py", ".github/policies/self-heal-policy.yml")
BENCHMARK_PATHS = ("benchmarks/",)


class ValidationError(Exception):
    pass


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True)


def git(*args):
    result = run(["git", *args])
    if result.returncode != 0:
        raise ValidationError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def changed_files_since(base_branch: str):
    merge_base = git("merge-base", base_branch, "HEAD")
    diff_names = git("diff", "--name-only", merge_base, "HEAD")
    return [f for f in diff_names.splitlines() if f.strip()], merge_base


def numstat_since(base_branch: str, merge_base: str) -> str:
    return git("diff", "--numstat", merge_base, "HEAD")


def configure_and_build(build_dir: Path, enable_coverage: bool):
    configure_cmd = ["cmake", "-S", str(REPO_ROOT), "-B", str(build_dir)]
    if enable_coverage:
        configure_cmd.append("-DENABLE_COVERAGE=ON")
    configure_result = run(configure_cmd)
    if configure_result.returncode != 0:
        raise ValidationError(f"cmake configure failed:\n{configure_result.stdout}\n{configure_result.stderr}")

    build_result = run(["cmake", "--build", str(build_dir), "-j", "4"])
    if build_result.returncode != 0:
        raise ValidationError(f"build failed:\n{build_result.stdout}\n{build_result.stderr}")


_CTEST_NAME_RE = re.compile(r"^Test\s+#\d+:\s*(.+)$")


def list_ctest_names(build_dir: Path):
    result = run(["ctest", "-N"], cwd=build_dir)
    names = []
    for line in result.stdout.splitlines():
        # ctest right-aligns the test number, so single- vs multi-digit
        # test counts use a different number of spaces before "#N:"
        # (e.g. "Test  #1:" vs "Test #10:"). Match on whitespace, not an
        # exact literal prefix.
        match = _CTEST_NAME_RE.match(line.strip())
        if match:
            names.append(match.group(1).strip())
    return names


def run_failed_tests_first(build_dir: Path, failing_tests):
    """Unit-test-remediation profile only: re-run the specific tests the
    evidence recorded as failing before re-running the full suite, so a
    fix that happens to pass everything-but-the-actual-bug is caught
    immediately with a focused error instead of a generic full-suite
    failure."""
    if not failing_tests:
        return
    result = run(["ctest", "--output-on-failure", "-R",
                  "^(" + "|".join(re.escape(name) for name in failing_tests) + ")$"],
                 cwd=build_dir)
    if result.returncode != 0:
        raise ValidationError(
            f"previously-failing test(s) {failing_tests} still fail:\n{result.stdout}"
        )


def run_all_unit_tests(build_dir: Path):
    result = run(["ctest", "--output-on-failure", "-E", "performance_policy"], cwd=build_dir)
    if result.returncode != 0:
        raise ValidationError(f"unit tests failed:\n{result.stdout}")


def verify_required_tests_present(build_dir: Path):
    names = set(list_ctest_names(build_dir))
    missing = REQUIRED_TEST_NAMES - names
    if missing:
        raise ValidationError(f"required tests are missing/disabled: {sorted(missing)}")


def verify_patch_scope(base_branch: str, build_dir: Path):
    changed_files, merge_base = changed_files_since(base_branch)
    numstat_text = numstat_since(base_branch, merge_base)

    evidence_path = REPO_ROOT / ".evidence" / "evidence.json"
    classification_path = REPO_ROOT / ".evidence" / "classification.json"
    if not evidence_path.exists() or not classification_path.exists():
        raise ValidationError("evidence.json / classification.json not found; cannot verify patch scope")

    numstat_file = REPO_ROOT / ".evidence" / "post_change.numstat"
    numstat_file.write_text(numstat_text)

    policy = evaluate_policy.load_policy()
    evidence = json.loads(evidence_path.read_text())
    classification = json.loads(classification_path.read_text())
    changed, inserted, deleted = evaluate_policy._numstat_to_counts(numstat_text)

    decision = evaluate_policy.evaluate(policy, classification, evidence, changed, inserted, deleted)
    if decision["decision"] != "allow":
        raise ValidationError(f"patch scope violates policy: {decision['reasons']}")
    return changed_files


def verify_paths_unchanged(changed_files, forbidden_prefixes, description):
    hits = [f for f in changed_files if any(f.startswith(p) for p in forbidden_prefixes)]
    if hits:
        raise ValidationError(f"{description}: {hits}")


def _load_evidence() -> dict:
    evidence_path = REPO_ROOT / ".evidence" / "evidence.json"
    if not evidence_path.exists():
        raise ValidationError("evidence.json not found; cannot validate")
    return json.loads(evidence_path.read_text())


def profile_unit_test_remediation(base_branch: str, build_dir: Path) -> dict:
    evidence = _load_evidence()
    configure_and_build(build_dir, enable_coverage=False)
    failing_tests = (evidence.get("measurements") or {}).get("failing_tests") or []
    run_failed_tests_first(build_dir, failing_tests)
    run_all_unit_tests(build_dir)
    verify_required_tests_present(build_dir)
    changed_files = verify_patch_scope(base_branch, build_dir)
    return {"changed_files": changed_files, "failing_tests_reverified": failing_tests}


def profile_coverage_remediation(base_branch: str, build_dir: Path) -> dict:
    evidence = _load_evidence()
    configure_and_build(build_dir, enable_coverage=True)
    run_all_unit_tests(build_dir)
    verify_required_tests_present(build_dir)

    original_base_sha = evidence.get("base_sha") or base_branch
    coverage_json = build_dir / "coverage.json"
    coverage_result = run([
        sys.executable, str(REPO_ROOT / "scripts" / "measure_coverage.py"),
        "--build-dir", str(build_dir), "--threshold", str(measure_coverage.DEFAULT_THRESHOLD),
        "--diff-against", original_base_sha,
        "--output", str(coverage_json),
    ])
    if coverage_result.returncode != 0:
        raise ValidationError(f"coverage policy still failing:\n{coverage_result.stdout}")

    changed_files = verify_patch_scope(base_branch, build_dir)
    verify_paths_unchanged(changed_files, PRODUCTION_PATHS, "production code was modified")
    verify_paths_unchanged(changed_files, COVERAGE_CONFIG_PATHS,
                            "coverage threshold/exclusions were modified")
    return {"changed_files": changed_files, "coverage": json.loads(coverage_json.read_text())}


def profile_performance_remediation(base_branch: str, build_dir: Path) -> dict:
    configure_and_build(build_dir, enable_coverage=False)
    run_all_unit_tests(build_dir)
    verify_required_tests_present(build_dir)

    # A single benchmark run can be noisy on a shared CI runner; require
    # the fix to pass on a stable majority of repeated runs rather than
    # a single pass/fail sample, per the performance-remediation profile.
    benchmark_runs = []
    passes = 0
    attempts = 3
    for _ in range(attempts):
        bench_result = run([str(build_dir / "performance_check")])
        benchmark_runs.append(bench_result.stdout)
        if bench_result.returncode == 0:
            passes += 1
    if passes < 2:
        raise ValidationError(
            f"performance policy still failing ({passes}/{attempts} runs passed):\n"
            + "\n---\n".join(benchmark_runs)
        )

    changed_files = verify_patch_scope(base_branch, build_dir)
    verify_paths_unchanged(changed_files, BENCHMARK_PATHS, "benchmark configuration was modified")
    return {
        "changed_files": changed_files,
        "benchmark_runs_passed": f"{passes}/{attempts}",
        "benchmark_output": benchmark_runs[-1],
    }


PROFILES = {
    "unit-test-remediation": profile_unit_test_remediation,
    "coverage-remediation": profile_coverage_remediation,
    "performance-remediation": profile_performance_remediation,
}


def _default_base_branch() -> str:
    """Diff base for patch-scope/anti-weakening checks: always
    `evidence.head_sha` (the exact failing commit the agent started
    from), never `main` or `evidence.base_sha` -- the developer's own
    pull request may itself touch paths that would be forbidden for the
    *remediation* to re-touch, so diffing against anything earlier than
    the failing commit would incorrectly blame the agent for the
    original PR's own changes.
    """
    evidence_path = REPO_ROOT / ".evidence" / "evidence.json"
    if evidence_path.exists():
        try:
            evidence = json.loads(evidence_path.read_text())
            sha = evidence.get("head_sha")
            if sha:
                return sha
        except (json.JSONDecodeError, OSError):
            pass
    return "main"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, choices=sorted(PROFILES.keys()))
    parser.add_argument(
        "--base-branch", default=None,
        help="Git ref to diff the remediation's patch scope against. "
             "Defaults to the head_sha recorded in .evidence/evidence.json "
             "(the failure commit), falling back to 'main' if no evidence "
             "is present.",
    )
    parser.add_argument("--build-dir", default=REPO_ROOT / "build", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    base_branch = args.base_branch or _default_base_branch()

    result = {
        "schema_version": "2.0",
        "profile": args.profile,
        "base_branch": base_branch,
        "passed": False,
        "details": {},
        "error": None,
    }

    try:
        details = PROFILES[args.profile](base_branch, args.build_dir)
        result["details"] = details
        result["passed"] = True
    except ValidationError as exc:
        result["error"] = str(exc)

    output_text = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text + "\n")
    print(output_text)

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
