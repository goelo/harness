"""TDD tests for team_cleanup.py — v1.5.4."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


def _run(*args, env_extra=None):
    script = Path(__file__).parent.parent / "harness_scripts" / "team_cleanup.py"
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestTeamCleanupConfigDir(unittest.TestCase):
    """Cleanup must find and remove team config dir under HOME/.claude/teams/."""

    def setUp(self):
        self.tmp_home = Path(tempfile.mkdtemp())
        self.team_name = "test-team-xyz"
        self.team_dir = self.tmp_home / ".claude" / "teams" / self.team_name
        self.team_dir.mkdir(parents=True)
        (self.team_dir / "config.json").write_text(
            json.dumps({"members": []}), encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_home, ignore_errors=True)

    def test_removes_team_config_dir(self):
        result = _run(self.team_name, env_extra={"HOME": str(self.tmp_home)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.team_dir.exists(), "team config dir not removed")

    def test_dry_run_does_not_remove(self):
        result = _run(self.team_name, "--dry-run", env_extra={"HOME": str(self.tmp_home)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.team_dir.exists(), "dry-run should not remove dir")

    def test_no_config_no_error(self):
        """When no config dir exists (already cleaned), exit 0 without error."""
        shutil.rmtree(self.team_dir)
        result = _run(self.team_name, env_extra={"HOME": str(self.tmp_home)})
        self.assertEqual(result.returncode, 0, result.stderr)


class TestTeamCleanupProcesses(unittest.TestCase):
    """Cleanup must find and kill processes whose cmdline contains the team name."""

    def setUp(self):
        self.tmp_home = Path(tempfile.mkdtemp())
        self.team_name = "harness-test-team-9X8Y7Z"  # unique enough to not collide

    def tearDown(self):
        shutil.rmtree(self.tmp_home, ignore_errors=True)

    def test_kills_matching_process(self):
        """Spawn a sleep process with the team name in its argv, run cleanup, verify it dies."""
        # Spawn a long-running sleep process whose argv contains the team name.
        # We use `sh -c "exec -a <name> sleep ..."` to set argv[0].
        # Simpler: just sleep with team_name as an argument.
        proc = subprocess.Popen(
            ["python3", "-c",
             f"import sys, time; sys.argv = ['{self.team_name}-marker']; time.sleep(60)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(0.3)  # let process start
            self.assertIsNone(proc.poll(), "spawned process died early")

            result = _run(self.team_name, env_extra={"HOME": str(self.tmp_home)})
            # script should detect and kill
            self.assertEqual(result.returncode, 0, f"stderr={result.stderr}\nstdout={result.stdout}")

            # give it time to die
            for _ in range(30):
                if proc.poll() is not None:
                    break
                time.sleep(0.1)

            self.assertIsNotNone(proc.poll(), "process not killed after cleanup")
        finally:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
