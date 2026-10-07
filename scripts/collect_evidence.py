#!/usr/bin/env python3
"""Deterministic evidence collector for a real pull request's CI run.

Runs all three deterministic checks (unit tests, coverage including
changed-line coverage, performance benchmark) against the already-built
tree, determines the single active `failure_category` from the actual
measurements (not from a scenario id), captures a normalized,
size-limited diff and log excerpt against the PR's own base commit, and
writes a signed evidence.json document conforming to
framework/schemas/evidence-schema-v1.json (schema_version "2.0").

This script performs no AI reasoning: every field is derived
mechanically from command output, git metadata, or CI-provided context
(repository/PR/branch/SHA/run id), and it is intended to run exactly
once, in the same CI job that built and tested the code, immediately
before that job reports failure -- see docs/architecture.md#known-limitations
for why this placement matters for the evidence's integrity signature.
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

# Category-specific file prefixes used only to narrow `relevant_files`
# down from the PR's full changed-file list -- this is a hint for the
# agent, not a policy decision (the policy engine re-derives permitted
# scope from the policy file's categories.<category> block).
CATEGORY_RELEVANT_PREFIXES = {
    "unit-test-failure": ("src/", "include/"),
    "performance-regression": ("src/", "include/"),
    "coverage-gap": ("tests/", "src/", "include/"),
}


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


def collect_unit_tests(build_dir: Path):
    result = run(["ctest", "--output-on-failure", "-E", "performance_policy"], cwd=build_dir)
    failing_tests = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("FAIL "):
            # Format: "FAIL <test-name> | <file>:<line> | <expr>"
            name = line[len("FAIL "):].split(" |", 1)[0].strip()
            if name not in failing_tests:
                failing_tests.append(name)
    passed = result.returncode == 0
    return {
        "passed": passed,
        "failed_command": "ctest --output-on-failure -E performance_policy",
        "log_excerpt": truncate(result.stdout, evidence_lib.MAX_CONCISE_LOG_CHARS),
        "measurements": {"failing_tests": failing_tests, "unit_tests_passed": passed},
    }


def collect_coverage(build_dir: Path, base_sha: str):
    coverage_json_path = build_dir / "coverage.json"
    result = run([
        sys.executable, str(REPO_ROOT / "scripts" / "measure_coverage.py"),
        "--build-dir", str(build_dir),
        "--threshold", str(measure_coverage.DEFAULT_THRESHOLD),
        "--diff-against", base_sha,
        "--output", str(coverage_json_path),
    ])
    report = json.loads(coverage_json_path.read_text()) if coverage_json_path.exists() else {}
    measurements = {
        "coverage_percent": report.get("coverage_percent"),
        "threshold_percent": report.get("threshold_percent"),
        "uncovered_lines": report.get("uncovered_lines", []),
        "source_files": report.get("source_files", []),
        "changed_line_coverage": report.get("changed_line_coverage"),
    }
    return {
        "passed": result.returncode == 0,
        "failed_command": f"scripts/measure_coverage.py --threshold {measure_coverage.DEFAULT_THRESHOLD} "
                           f"--diff-against {base_sha}",
        "log_excerpt": truncate(result.stdout, evidence_lib.MAX_CONCISE_LOG_CHARS),
        "measurements": measurements,
    }


def collect_benchmark(build_dir: Path):
    binary = build_dir / "performance_check"
    result = run([str(binary)])
    stdout = result.stdout

    def extract(key):
        for line in stdout.splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1]
        return None

    median_ms = float(extract("median_ms")) if extract("median_ms") else None
    threshold_ms = float(extract("threshold_ms")) if extract("threshold_ms") else None
    return {
        "passed": result.returncode == 0,
        "failed_command": "build/performance_check",
        "log_excerpt": truncate(stdout, evidence_lib.MAX_CONCISE_LOG_CHARS),
        "measurements": {"median_ms": median_ms, "threshold_ms": threshold_ms},
    }


def determine_category(unit_result, coverage_result, benchmark_result) -> str:
    """Deterministic priority order when more than one check fails:
    a broken build/test suite is fixed before coverage is even
    meaningful to measure, and a benchmark regression is the least
    urgent of the three. Each run only ever acts on a single category;
    the others' measurements are still included for context."""
    if not unit_result["passed"]:
        return "unit-test-failure"
    if not coverage_result["passed"]:
        return "coverage-gap"
    if not benchmark_result["passed"]:
        return "performance-regression"
    return "unsupported"


def build_failure_signature(category: str, measurements: dict) -> str:
    if category == "unit-test-failure":
        key = ",".join(sorted(measurements.get("failing_tests") or []))
    elif category == "coverage-gap":
        key = f"{len(measurements.get('uncovered_lines') or [])}-uncovered"
    elif category == "performance-regression":
        key = "median-exceeds-threshold"
    else:
        key = "none"
    return f"{category}:{key}"[:200]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", default=REPO_ROOT / "build", type=Path)
    parser.add_argument("--repository", required=True, help="owner/repo")
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--base-branch", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-branch", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--evidence-dir", default=REPO_ROOT / ".evidence", type=Path)
    parser.add_argument("--attempt-number", default=1, type=int)
    parser.add_argument(
        "--scenario", default=None, choices=sorted(evidence_lib.SCENARIOS),
        help="Optional provenance only, set by the optional demo-fixture "
             "helper scripts. Never used for classification or policy.",
    )
    parser.add_argument("--start-time-epoch", type=float, default=None,
                         help="Epoch seconds the run started; used to compute "
                              "runtime_budget.elapsed_minutes.")
    parser.add_argument("--require-failure", action="store_true",
                         help="Exit non-zero if none of the three deterministic "
                              "checks failed (i.e. there is nothing to heal).")
    args = parser.parse_args()

    build_dir = args.build_dir
    unit_result = collect_unit_tests(build_dir)
    coverage_result = collect_coverage(build_dir, args.base_sha)
    benchmark_result = collect_benchmark(build_dir)

    category = determine_category(unit_result, coverage_result, benchmark_result)
    by_category = {
        "unit-test-failure": unit_result,
        "coverage-gap": coverage_result,
        "performance-regression": benchmark_result,
    }

    evidence_dir = args.evidence_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)

    changed_files_raw = git("diff", "--name-only", args.base_sha, args.head_sha)
    diff_raw = run(["git", "diff", args.base_sha, args.head_sha]).stdout
    changed_files = [f for f in changed_files_raw.splitlines() if f.strip()]
    diff_text = truncate(diff_raw, evidence_lib.MAX_DIFF_CHARS)

    diff_file = evidence_dir / "diff.patch"
    diff_file.write_text(diff_text)

    measurements = {
        **unit_result["measurements"],
        **coverage_result["measurements"],
        **benchmark_result["measurements"],
    }

    if category == "unsupported":
        print(json.dumps({"result": "passed",
                           "message": "all deterministic checks passed; no evidence generated"},
                          indent=2))
        return 1 if args.require_failure else 0

    active = by_category[category]
    log_file = evidence_dir / "failure_log.txt"
    log_file.write_text(active["log_excerpt"])

    policy = simple_yaml.load_file(str(DEFAULT_POLICY_PATH))
    category_policy = policy.get("categories", {}).get(category, {})
    relevant_prefixes = CATEGORY_RELEVANT_PREFIXES.get(category, ())
    relevant_files = sorted({
        f for f in changed_files if any(f.startswith(p) for p in relevant_prefixes)
    }) or sorted(changed_files)

    elapsed_minutes = None
    if args.start_time_epoch is not None:
        elapsed_minutes = round((time.time() - args.start_time_epoch) / 60.0, 2)

    evidence = {
        "schema_version": evidence_lib.SCHEMA_VERSION,
        "scenario": args.scenario,
        "event_source": "scripts/collect_evidence.py",
        "repository": args.repository,
        "pr_number": args.pr_number,
        "base_branch": args.base_branch,
        "base_sha": args.base_sha,
        "head_branch": args.head_branch,
        "head_sha": args.head_sha,
        "workflow_run_id": str(args.workflow_run_id),
        "changed_files": changed_files,
        "diff_file": str(diff_file.relative_to(REPO_ROOT)),
        "failure_category": category,
        "failed_command": active["failed_command"],
        "failure_signature": build_failure_signature(category, measurements),
        "concise_log_file": str(log_file.relative_to(REPO_ROOT)),
        "relevant_files": relevant_files,
        "measurements": measurements,
        "runtime_budget": {
            "target_minutes": category_policy.get("runtime_budget_minutes", 10),
            "elapsed_minutes": elapsed_minutes,
        },
        "attempt_number": args.attempt_number,
    }
    evidence["signature"] = evidence_lib.compute_signature(evidence)

    errors = evidence_lib.validate_evidence(evidence)
    if errors:
        print("Evidence failed self-validation:", errors, file=sys.stderr)
        return 2

    evidence_path = evidence_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
