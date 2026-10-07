#!/usr/bin/env python3
"""Deterministic coverage measurement for job_processor.cpp.

This is a lightweight coverage mechanism built directly on `gcov` (no
external coverage library). It:

  1. Locates the .gcda/.gcno files produced by a coverage-instrumented
     build (see CMakeLists.txt's ENABLE_COVERAGE option).
  2. Runs `gcov` against the job_processor.cpp translation unit only.
  3. Parses the resulting .gcov annotation file to compute line coverage
     for src/job_processor.cpp specifically (the only production source
     file in this demo).
  4. Compares the result against the configured threshold and emits a
     JSON report consumed by the policy engine and evidence collector.

Usage:
    scripts/measure_coverage.py --build-dir build --threshold 95 \
        --output build/coverage.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_SOURCE = "src/job_processor.cpp"
DEFAULT_THRESHOLD = 95.0


def find_gcda(build_dir: Path) -> Path:
    candidates = list(build_dir.rglob("job_processor.cpp.gcda"))
    # Only consider the library target's object directory, not the test
    # binary's (job_processor_tests has its own translation units but not
    # this one, so there should be exactly one match).
    if not candidates:
        raise SystemExit(
            "No coverage data found. Build with -DENABLE_COVERAGE=ON and "
            "run the test suite first."
        )
    return candidates[0]


def run_gcov(gcda_path: Path) -> str:
    obj_dir = gcda_path.parent
    result = subprocess.run(
        ["gcov", gcda_path.name],
        cwd=obj_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    gcov_file = obj_dir / "job_processor.cpp.gcov"
    if not gcov_file.exists():
        raise SystemExit(f"gcov did not produce expected output:\n{result.stdout}\n{result.stderr}")
    contents = gcov_file.read_text()

    # gcov also annotates every transitively-included header (STL headers,
    # etc). We only need our own source file's report, so clean up the rest
    # to avoid cluttering the build directory.
    for stray in obj_dir.glob("*.gcov"):
        if stray != gcov_file:
            stray.unlink()

    return contents


def parse_gcov(contents: str) -> dict:
    covered_lines = []
    uncovered_lines = []

    for raw_line in contents.splitlines():
        parts = raw_line.split(":", 2)
        if len(parts) < 3:
            continue
        count_field, line_no_field = parts[0].strip(), parts[1].strip()
        if not line_no_field.isdigit():
            continue
        line_no = int(line_no_field)
        if line_no == 0:
            continue  # header metadata lines
        if count_field == "-":
            continue  # non-executable line
        if count_field.startswith("#"):
            uncovered_lines.append(line_no)
        else:
            covered_lines.append(line_no)

    total = len(covered_lines) + len(uncovered_lines)
    percent = 100.0 if total == 0 else (len(covered_lines) / total) * 100.0
    return {
        "covered_lines": sorted(covered_lines),
        "uncovered_lines": sorted(uncovered_lines),
        "executable_line_count": total,
        "covered_line_count": len(covered_lines),
        "coverage_percent": round(percent, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", default="build", type=Path)
    parser.add_argument("--threshold", default=DEFAULT_THRESHOLD, type=float)
    parser.add_argument("--output", default=None, type=Path)
    args = parser.parse_args()

    build_dir = (REPO_ROOT / args.build_dir) if not args.build_dir.is_absolute() else args.build_dir
    gcda_path = find_gcda(build_dir)
    gcov_contents = run_gcov(gcda_path)
    coverage = parse_gcov(gcov_contents)

    report = {
        "source_file": TARGET_SOURCE,
        "threshold_percent": args.threshold,
        "passed": coverage["coverage_percent"] >= args.threshold,
        **coverage,
    }

    output_text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output_path = (REPO_ROOT / args.output) if not args.output.is_absolute() else args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text + "\n")
    print(output_text)

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
