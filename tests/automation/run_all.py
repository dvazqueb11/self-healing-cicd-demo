#!/usr/bin/env python3
"""Run the full automation test suite (tests/automation/*).

This suite exercises the deterministic framework itself: evidence
schema validation, the classifier, the policy engine, fixture
apply/reset, and the public-repo scanner. It has no dependency on the
C++ build and runs in well under a second.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

AUTOMATION_DIR = Path(__file__).resolve().parent


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(str(AUTOMATION_DIR), pattern="test_*.py", top_level_dir=str(AUTOMATION_DIR))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
