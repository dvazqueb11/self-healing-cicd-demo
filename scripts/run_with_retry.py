#!/usr/bin/env python3
"""Run a command and retry once/twice on transient infrastructure failures.

This helper is intentionally generic and dependency-free so CI can reuse it
for test/coverage/benchmark stages that are deterministic but can still fail
for non-deterministic runner reasons (OOM kills, transient I/O, etc.).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from typing import Sequence


DEFAULT_RETRY_PATTERNS = [
    r"resource temporarily unavailable",
    r"temporary failure",
    r"cannot allocate memory",
    r"out of memory",
    r"no space left on device",
    r"killed",
]


def _compile_patterns(patterns: Sequence[str]) -> list[re.Pattern[str]]:
    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]


def _should_retry(exit_code: int, output: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    # Common transient termination codes seen on CI runners.
    if exit_code in (137, 143):
        return True
    return any(pattern.search(output) for pattern in patterns)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Total attempts including the first run (default: 2).",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=1.0,
        help="Sleep duration before retrying (default: 1s).",
    )
    parser.add_argument(
        "--retry-pattern",
        action="append",
        default=[],
        help="Regex pattern indicating a retryable transient failure. May be repeated.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run. Prefix with '--' to separate runner args.",
    )
    args = parser.parse_args()

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]

    if args.max_attempts < 1:
        parser.error("--max-attempts must be >= 1")
    if not command:
        parser.error("missing command to execute")

    retry_patterns = args.retry_pattern or DEFAULT_RETRY_PATTERNS
    compiled_patterns = _compile_patterns(retry_patterns)

    for attempt in range(1, args.max_attempts + 1):
        print(
            f"[retry-runner] attempt {attempt}/{args.max_attempts}: {' '.join(command)}",
            file=sys.stderr,
        )
        result = subprocess.run(command, capture_output=True, text=True)
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)

        if result.returncode == 0:
            return 0

        combined_output = f"{result.stdout}\n{result.stderr}"
        can_retry = attempt < args.max_attempts and _should_retry(
            result.returncode, combined_output, compiled_patterns
        )
        if not can_retry:
            print(
                f"[retry-runner] command failed (exit={result.returncode}); not retrying",
                file=sys.stderr,
            )
            return result.returncode

        print(
            f"[retry-runner] transient failure detected; retrying after "
            f"{args.retry_delay_seconds:.1f}s",
            file=sys.stderr,
        )
        time.sleep(args.retry_delay_seconds)

    return 1


if __name__ == "__main__":
    sys.exit(main())
