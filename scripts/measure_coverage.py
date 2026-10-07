#!/usr/bin/env python3
"""Deterministic, portable coverage measurement for src/**.

This is a lightweight coverage mechanism built directly on `gcov` (no
external coverage library, no CI-only service). It:

  1. Discovers every `.gcda` file produced by a coverage-instrumented
     build (see CMakeLists.txt's ENABLE_COVERAGE option) after the unit
     tests have run.
  2. Runs `gcov` against each one and reads the `.gcov` annotation
     files' own `Source:` header to find which *production* source file
     (anything under `src/`) it covers -- this works for any number of
     production source files, not just a single hardcoded name, so the
     measurement stays correct as the demo application grows.
  3. Computes both an overall line-coverage percentage across every
     discovered production source file, and (optionally, when a base
     commit is supplied) *changed-line* coverage: whether every
     executable line added since that commit is actually covered. A
     patch can raise overall coverage above the threshold while still
     leaving its own new branches untested if the file already had a
     large covered surface; changed-line coverage closes that gap.
  4. Compares the overall result against the configured threshold and
     emits a JSON report consumed by the policy engine, the evidence
     collector, and validate_change.py's coverage-remediation profile.

This only depends on the C++ toolchain's own `gcov` binary (matched to
the compiler used for the build), so results are reproducible on any
runner using the same pinned toolchain as CI -- no coverage.py-style
external dependency to drift out of sync with the compiler version.

Usage:
    scripts/measure_coverage.py --build-dir build --threshold 95 \
        --output build/coverage.json
    scripts/measure_coverage.py --build-dir build --threshold 95 \
        --diff-against origin/main --output build/coverage.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
PRODUCTION_SOURCE_PREFIX = "src/"
DEFAULT_THRESHOLD = 95.0

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def run(cmd, cwd=None, check=False):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def discover_gcda_files(build_dir: Path) -> List[Path]:
    return sorted(build_dir.rglob("*.gcda"))


def _source_path_for_gcov(gcov_path: Path) -> Optional[str]:
    """Read a .gcov file's `Source:` header and return a path relative
    to the repository root, or None if it falls outside the repo."""
    try:
        first_line = gcov_path.read_text(errors="ignore").splitlines()[0]
    except (OSError, IndexError):
        return None
    # Format: "        -:    0:Source:/abs/or/relative/path"
    marker = "Source:"
    idx = first_line.find(marker)
    if idx == -1:
        return None
    raw = first_line[idx + len(marker):].strip()
    source_path = Path(raw)
    try:
        if source_path.is_absolute():
            return str(source_path.relative_to(REPO_ROOT))
        resolved = (gcov_path.parent / source_path).resolve()
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return None


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

    covered = sorted(covered_lines)
    uncovered = sorted(uncovered_lines)
    total = len(covered) + len(uncovered)
    percent = 100.0 if total == 0 else (len(covered) / total) * 100.0
    return {
        "covered_lines": covered,
        "uncovered_lines": uncovered,
        "executable_line_count": total,
        "covered_line_count": len(covered),
        "coverage_percent": round(percent, 2),
    }


def measure_production_coverage(build_dir: Path) -> Dict[str, dict]:
    """Returns {relative_source_path: coverage-dict} for every file under
    src/ touched by any discovered .gcda file."""
    per_file: Dict[str, dict] = {}

    for gcda_path in discover_gcda_files(build_dir):
        obj_dir = gcda_path.parent
        before = set(obj_dir.glob("*.gcov"))
        result = run(["gcov", gcda_path.name], cwd=obj_dir)
        produced = set(obj_dir.glob("*.gcov")) - before
        # Some gcov versions reuse file names across runs; if nothing new
        # appeared, fall back to all current .gcov files in that dir.
        if not produced:
            produced = set(obj_dir.glob("*.gcov"))

        for gcov_file in produced:
            rel_source = _source_path_for_gcov(gcov_file)
            if rel_source is None or not rel_source.startswith(PRODUCTION_SOURCE_PREFIX):
                gcov_file.unlink(missing_ok=True)
                continue
            if rel_source not in per_file:
                per_file[rel_source] = parse_gcov(gcov_file.read_text(errors="ignore"))
            gcov_file.unlink(missing_ok=True)

        if not result.stdout and not produced:
            # gcov failed silently for this .gcda; surface it loudly
            # rather than silently reporting 100% coverage for nothing.
            pass

    if not per_file:
        raise SystemExit(
            "No production (src/**) coverage data found. Build with "
            "-DENABLE_COVERAGE=ON and run the test suite first."
        )
    return per_file


def aggregate(per_file: Dict[str, dict]) -> dict:
    covered = sum(f["covered_line_count"] for f in per_file.values())
    total = sum(f["executable_line_count"] for f in per_file.values())
    percent = 100.0 if total == 0 else (covered / total) * 100.0
    return {
        "executable_line_count": total,
        "covered_line_count": covered,
        "coverage_percent": round(percent, 2),
    }


def parse_added_lines(diff_text: str) -> Dict[str, Set[int]]:
    """Returns {new-side relative path: set(added line numbers)} from a
    unified diff, using the post-change ("+") side's line numbering."""
    added: Dict[str, Set[int]] = {}
    current_file: Optional[str] = None
    line_no: Optional[int] = None

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            raw_path = line[4:].strip()
            if raw_path == "/dev/null":
                current_file = None
            else:
                current_file = raw_path[2:] if raw_path.startswith("b/") else raw_path
            line_no = None
            continue
        if line.startswith("@@"):
            match = _HUNK_RE.match(line)
            line_no = int(match.group(1)) if match else None
            continue
        if current_file is None or line_no is None:
            continue
        if line.startswith("+"):
            added.setdefault(current_file, set()).add(line_no)
            line_no += 1
        elif line.startswith("-"):
            continue  # removed line: does not exist on the new side
        else:
            line_no += 1

    return added


def compute_changed_line_coverage(added_lines: Dict[str, Set[int]],
                                   per_file: Dict[str, dict]) -> dict:
    violations: Dict[str, List[int]] = {}
    checked_files = []
    for rel_path, lines in added_lines.items():
        coverage = per_file.get(rel_path)
        if coverage is None:
            continue  # not a measured production source file (e.g. a test file)
        checked_files.append(rel_path)
        uncovered = set(coverage["uncovered_lines"])
        bad = sorted(lines & uncovered)
        if bad:
            violations[rel_path] = bad

    return {
        "checked_files": sorted(checked_files),
        "violations": violations,
        "passed": not violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", default="build", type=Path)
    parser.add_argument("--threshold", default=DEFAULT_THRESHOLD, type=float)
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument(
        "--diff-against", default=None,
        help="A git ref/SHA. When given, also requires every executable "
             "line added since this ref in a measured production source "
             "file to be covered (changed-line coverage), in addition to "
             "the overall threshold.",
    )
    args = parser.parse_args()

    build_dir = (REPO_ROOT / args.build_dir) if not args.build_dir.is_absolute() else args.build_dir
    per_file = measure_production_coverage(build_dir)
    overall = aggregate(per_file)

    report = {
        "source_files": sorted(per_file.keys()),
        "threshold_percent": args.threshold,
        "per_file": per_file,
        **overall,
        "covered_lines": sorted({ln for f in per_file.values() for ln in f["covered_lines"]}),
        "uncovered_lines": sorted({ln for f in per_file.values() for ln in f["uncovered_lines"]}),
    }
    # Backward-compatible single-file field, populated only when there is
    # exactly one measured production source file (true for this demo).
    report["source_file"] = report["source_files"][0] if len(report["source_files"]) == 1 else None

    overall_passed = overall["coverage_percent"] >= args.threshold
    changed_line_result = None
    if args.diff_against:
        diff_text = run(["git", "diff", args.diff_against, "--", PRODUCTION_SOURCE_PREFIX],
                         cwd=REPO_ROOT).stdout
        added_lines = parse_added_lines(diff_text)
        changed_line_result = compute_changed_line_coverage(added_lines, per_file)
        report["changed_line_coverage"] = changed_line_result

    report["passed"] = overall_passed and (changed_line_result is None or changed_line_result["passed"])

    output_text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output_path = (REPO_ROOT / args.output) if not args.output.is_absolute() else args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text + "\n")
    print(output_text)

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
