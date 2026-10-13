from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUNNER = REPO_ROOT / "scripts" / "run_with_retry.py"


class RetryRunnerTests(unittest.TestCase):
    def _write_flaky_script(self, script_path: Path):
        script_path.write_text(
            "import pathlib, sys\n"
            "state = pathlib.Path(sys.argv[1])\n"
            "count = int(state.read_text() or '0') if state.exists() else 0\n"
            "count += 1\n"
            "state.write_text(str(count))\n"
            "if count == 1:\n"
            "    print('transient infra glitch')\n"
            "    sys.exit(1)\n"
            "print('recovered')\n"
            "sys.exit(0)\n"
        )

    def _write_permanent_failure_script(self, script_path: Path):
        script_path.write_text(
            "import pathlib, sys\n"
            "state = pathlib.Path(sys.argv[1])\n"
            "count = int(state.read_text() or '0') if state.exists() else 0\n"
            "count += 1\n"
            "state.write_text(str(count))\n"
            "print('real assertion failure')\n"
            "sys.exit(1)\n"
        )

    def test_retries_transient_failure_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            flaky_script = tmp_dir / "flaky.py"
            state_file = tmp_dir / "state.txt"
            self._write_flaky_script(flaky_script)

            result = subprocess.run(
                [
                    sys.executable, str(RUNNER),
                    "--max-attempts", "2",
                    "--retry-delay-seconds", "0",
                    "--retry-pattern", "transient infra glitch",
                    "--",
                    sys.executable, str(flaky_script), str(state_file),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual(state_file.read_text().strip(), "2")

    def test_does_not_retry_non_retryable_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            fail_script = tmp_dir / "fail.py"
            state_file = tmp_dir / "state.txt"
            self._write_permanent_failure_script(fail_script)

            result = subprocess.run(
                [
                    sys.executable, str(RUNNER),
                    "--max-attempts", "3",
                    "--retry-delay-seconds", "0",
                    "--retry-pattern", "transient infra glitch",
                    "--",
                    sys.executable, str(fail_script), str(state_file),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(state_file.read_text().strip(), "1")


if __name__ == "__main__":
    unittest.main()
