#!/usr/bin/env python3
"""Deterministic evidence collector.

Runs the deterministic check for a given scenario (unit tests, coverage,
or the performance benchmark), captures a normalized, size-limited diff
and log excerpt, and writes an evidence.json document conforming to
framework/schemas/evidence-schema-v1.json.

This script performs no AI reasoning: every field is derived mechanically
from command output, git metadata, or fixed configuration.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "framework" / "schemas"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import evidence_lib  # noqa: E402
import simple_yaml  # noqa: E402
import measure_coverage  # noqa: E402

DEFAULT_POLICY_PATH = REPO_ROOT / ".github" / "policies" / "self-heal-policy.yml"


def run(cmd, cwd=None, check=False):
    return subprocess.run(
        cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True, check=check
    )


def git(*args) -> str:
    result = run(["git", *args], check=True)
    return result.stdout.strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated, {len(text) - limit} characters omitted]"


def collect_unit_test_evidence(build_dir: Path):
    ctest_result = run(["ctest", "--output-on-failure"], cwd=build_dir)
    failing_tests = []
    for line in ctest_result.stdout.splitlines():
        line = line.strip()
        if line.startswith("FAIL "):
            # Format: "FAIL <test-name> | <file>:<line> | <expr>"
            name = line[len("FAIL "):].split(" |", 1)[0].strip()
            if name not in failing_tests:
                failing_tests.append(name)

    log_excerpt = truncate(ctest_result.stdout, evidence_lib.MAX_CONCISE_LOG_CHARS)
    measurements = {"failing_tests": failing_tests}
    passed = ctest_result.returncode == 0
    return passed, "ctest --output-on-failure", log_excerpt, measurements


def collect_coverage_evidence(build_dir: Path):
    # Coverage data (.gcda) is only produced by actually exercising the
    # instrumented binary, so the unit tests must run first. Their
    # pass/fail status is irrelevant here: we only need the coverage
    # percentage, which measure_coverage.py reports on below.
    run(["ctest", "--output-on-failure"], cwd=build_dir)

    coverage_json_path = build_dir / "coverage.json"
    coverage_result = run([
        sys.executable, str(REPO_ROOT / "scripts" / "measure_coverage.py"),
        "--build-dir", str(build_dir),
        "--threshold", str(measure_coverage.DEFAULT_THRESHOLD),
        "--output", str(coverage_json_path),
    ])
    report = json.loads(coverage_json_path.read_text()) if coverage_json_path.exists() else {}
    log_excerpt = truncate(coverage_result.stdout, evidence_lib.MAX_CONCISE_LOG_CHARS)
    measurements = {
        "coverage_percent": report.get("coverage_percent"),
        "threshold_percent": report.get("threshold_percent"),
        "uncovered_lines": report.get("uncovered_lines", []),
        "source_file": report.get("source_file"),
    }
    passed = coverage_result.returncode == 0
    return passed, f"scripts/measure_coverage.py --threshold {measure_coverage.DEFAULT_THRESHOLD}", log_excerpt, measurements


def collect_performance_evidence(build_dir: Path):
    binary = build_dir / "performance_check"
    bench_result = run([str(binary)])
    stdout = bench_result.stdout

    def extract(key):
        for line in stdout.splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1]
        return None

    median_ms = float(extract("median_ms")) if extract("median_ms") else None
    threshold_ms = float(extract("threshold_ms")) if extract("threshold_ms") else None
    log_excerpt = truncate(stdout, evidence_lib.MAX_CONCISE_LOG_CHARS)
    measurements = {"median_ms": median_ms, "threshold_ms": threshold_ms}
    passed = bench_result.returncode == 0
    return passed, "build/performance_check", log_excerpt, measurements


COLLECTORS = {
    "easy-unit-test": ("unit-test-failure", collect_unit_test_evidence),
    "medium-low-coverage": ("coverage-gap", collect_coverage_evidence),
    "advanced-performance": ("performance-regression", collect_performance_evidence),
}


def build_failure_signature(scenario: str, category: str, measurements: dict) -> str:
    if category == "unit-test-failure":
        key = ",".join(sorted(measurements.get("failing_tests") or []))
    elif category == "coverage-gap":
        key = f"{measurements.get('source_file')}:{len(measurements.get('uncovered_lines') or [])}-uncovered"
    elif category == "performance-regression":
        key = "median-exceeds-threshold"
    else:
        key = "unknown"
    return f"{scenario}:{category}:{key}"[:200]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=sorted(COLLECTORS.keys()))
    parser.add_argument("--build-dir", default=REPO_ROOT / "build", type=Path)
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--evidence-dir", default=REPO_ROOT / ".evidence", type=Path)
    parser.add_argument("--attempt-number", default=1, type=int)
    parser.add_argument("--run-id", default="local")
    parser.add_argument("--start-time-epoch", type=float, default=None,
                         help="Epoch seconds the run started; used to compute "
                              "runtime_budget.elapsed_minutes.")
    parser.add_argument("--require-failure", action="store_true",
                         help="Exit non-zero if the scenario's deterministic "
                              "check did NOT fail (i.e. there is nothing to heal).")
    args = parser.parse_args()

    category, collector = COLLECTORS[args.scenario]
    passed, failed_command, log_excerpt, measurements = collector(args.build_dir)

    evidence_dir = args.evidence_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)

    repository = "local/self-healing-cicd-demo"
    try:
        remote_url = git("config", "--get", "remote.origin.url")
        if remote_url:
            repository = remote_url.rstrip("/").split("/")[-2] + "/" + remote_url.rstrip("/").split("/")[-1].replace(".git", "")
    except subprocess.CalledProcessError:
        pass

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    sha = git("rev-parse", "HEAD")

    merge_base = None
    try:
        merge_base = git("merge-base", args.base_branch, "HEAD")
    except subprocess.CalledProcessError:
        merge_base = None

    if merge_base:
        changed_files_raw = git("diff", "--name-only", merge_base, "HEAD")
        diff_raw = run(["git", "diff", merge_base, "HEAD"]).stdout
    else:
        changed_files_raw = ""
        diff_raw = ""

    changed_files = [f for f in changed_files_raw.splitlines() if f.strip()]
    diff_text = truncate(diff_raw, evidence_lib.MAX_DIFF_CHARS)

    diff_file = evidence_dir / "diff.patch"
    diff_file.write_text(diff_text)
    log_file = evidence_dir / "failure_log.txt"
    log_file.write_text(log_excerpt)

    policy = simple_yaml.load_file(str(DEFAULT_POLICY_PATH))
    scenario_policy = policy.get("scenarios", {}).get(args.scenario, {})
    relevant_files = sorted(set(
        scenario_policy.get("permitted_paths", [])
    ) | {"src/job_processor.cpp", "include/job_processor.hpp"})

    elapsed_minutes = None
    if args.start_time_epoch is not None:
        elapsed_minutes = round((time.time() - args.start_time_epoch) / 60.0, 2)

    evidence = {
        "schema_version": evidence_lib.SCHEMA_VERSION,
        "scenario": args.scenario,
        "event_source": f"{args.scenario}-collector",
        "repository": repository,
        "branch": branch,
        "triggering_sha": sha,
        "workflow_run": args.run_id,
        "changed_files": changed_files,
        "diff_file": str(diff_file.relative_to(REPO_ROOT)),
        "failure_category": category if not passed else "unsupported",
        "failed_command": failed_command,
        "failure_signature": build_failure_signature(args.scenario, category, measurements)
        if not passed else None,
        "concise_log_file": str(log_file.relative_to(REPO_ROOT)),
        "relevant_files": sorted(relevant_files),
        "measurements": measurements,
        "runtime_budget": {
            "target_minutes": scenario_policy.get("runtime_budget_minutes", 10),
            "elapsed_minutes": elapsed_minutes,
        },
        "attempt_number": args.attempt_number,
    }

    evidence_path = evidence_dir / "evidence.json"

    if not passed:
        errors = evidence_lib.validate_evidence(evidence)
        if errors:
            print("Evidence failed self-validation:", errors, file=sys.stderr)
            return 2
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0
    else:
        # The deterministic check passed: there is nothing to heal. This is
        # the expected state for a healthy default branch. Evidence is not
        # written in this case (failure_category is intentionally
        # "unsupported" and would be rejected by the classifier).
        print(json.dumps({"scenario": args.scenario, "result": "passed",
                           "message": "deterministic check passed; no evidence generated"},
                          indent=2))
        return 1 if args.require_failure else 0


if __name__ == "__main__":
    sys.exit(main())
