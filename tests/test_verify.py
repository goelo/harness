"""Tests for .harness/scripts/verify.py quality gates."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
VERIFY_SCRIPT = REPO_ROOT / "harness_scripts" / "verify.py"


class VerifyScriptTestCase(unittest.TestCase):
    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        self.harness_dir = self.project_dir / ".harness"
        self.scripts_dir = self.harness_dir / "scripts"
        self.tasks_dir = self.harness_dir / "tasks"
        self.sessions_dir = self.harness_dir / "runtime" / "sessions"
        self.scripts_dir.mkdir(parents=True)
        self.tasks_dir.mkdir(parents=True)
        self.sessions_dir.mkdir(parents=True)
        shutil.copy2(VERIFY_SCRIPT, self.scripts_dir / "verify.py")
        subprocess.run(["git", "init"], cwd=self.project_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "tester"], cwd=self.project_dir, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=self.project_dir, check=True)
        (self.project_dir / ".gitignore").write_text(".harness/runtime/\n", encoding="utf-8")
        (self.project_dir / "README.md").write_text("# demo\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore", "README.md"], cwd=self.project_dir, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.project_dir, check=True, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def write_config(self, *, lint="true", typecheck="true", test="true", coverage="true", denied=None):
        config = {
            "commands": {
                "lint": lint,
                "type": typecheck,
                "test": test,
                "coverage": coverage,
            },
            "scope": {
                "denied": denied if denied is not None else [".harness/runtime/**"],
            },
        }
        (self.harness_dir / "verify.json").write_text(
            json.dumps(config, indent=2) + "\n",
            encoding="utf-8",
        )

    def write_task(self, name="05-26-demo", *, allowed=None, denied=None, make_current=True):
        task_dir = self.tasks_dir / name
        task_dir.mkdir(parents=True)
        (task_dir / "scope.json").write_text(
            json.dumps(
                {
                    "allowed": allowed if allowed is not None else ["src/**"],
                    "denied": denied if denied is not None else [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if make_current:
            (self.sessions_dir / "local.json").write_text(
                json.dumps({"current_task": f".harness/tasks/{name}"}) + "\n",
                encoding="utf-8",
            )
        subprocess.run(
            ["git", "add", ".harness/scripts/verify.py", ".harness/verify.json", str(task_dir.relative_to(self.project_dir))],
            cwd=self.project_dir,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"add harness task {name}"],
            cwd=self.project_dir,
            check=True,
            capture_output=True,
        )
        return task_dir

    def run_verify(self, *args):
        env = {**os.environ, "HARNESS_CONTEXT_ID": "local"}
        return subprocess.run(
            [sys.executable, ".harness/scripts/verify.py", *args],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
            env=env,
        )


class TestVerifyCommands(VerifyScriptTestCase):
    def test_all_fails_when_required_command_missing(self):
        self.write_config(typecheck="")
        self.write_task()

        result = self.run_verify("all")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commands.type", result.stderr)

    def test_subcommand_runs_configured_command_and_returns_exit_code(self):
        self.write_config(lint="exit 7")
        self.write_task()

        result = self.run_verify("lint")

        self.assertEqual(result.returncode, 7)
        self.assertIn("lint", result.stdout)

    def test_all_runs_commands_and_scope_when_everything_passes(self):
        self.write_config()
        self.write_task(allowed=["src/**"])
        (self.project_dir / "src").mkdir()
        (self.project_dir / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")

        result = self.run_verify("all")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("coverage", result.stdout)
        self.assertIn("scope", result.stdout)


class TestVerifyScope(VerifyScriptTestCase):
    def test_scope_allows_allowed_changed_file(self):
        self.write_config()
        self.write_task(allowed=["src/**"])
        (self.project_dir / "src").mkdir()
        (self.project_dir / "src" / "service.py").write_text("x = 1\n", encoding="utf-8")

        result = self.run_verify("scope")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_scope_fails_for_file_outside_allowed_range(self):
        self.write_config()
        self.write_task(allowed=["src/**"])
        (self.project_dir / "docs").mkdir()
        (self.project_dir / "docs" / "plan.md").write_text("# plan\n", encoding="utf-8")

        result = self.run_verify("scope")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not allowed", result.stderr)
        self.assertIn("docs/plan.md", result.stderr)

    def test_scope_fails_for_denied_file_even_when_allowed(self):
        self.write_config(denied=["src/generated/**"])
        self.write_task(allowed=["src/**"])
        (self.project_dir / "src" / "generated").mkdir(parents=True)
        (self.project_dir / "src" / "generated" / "api.py").write_text("x = 1\n", encoding="utf-8")

        result = self.run_verify("scope")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("denied", result.stderr)
        self.assertIn("src/generated/api.py", result.stderr)

    def test_scope_includes_untracked_files(self):
        self.write_config()
        self.write_task(allowed=["src/**"])
        (self.project_dir / "notes.txt").write_text("new\n", encoding="utf-8")

        result = self.run_verify("scope")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("notes.txt", result.stderr)

    def test_scope_uses_task_argument_over_current_task(self):
        self.write_config()
        self.write_task("05-26-current", allowed=["src/**"], make_current=True)
        self.write_task("05-26-other", allowed=["docs/**"], make_current=False)
        (self.project_dir / "docs").mkdir()
        (self.project_dir / "docs" / "plan.md").write_text("# plan\n", encoding="utf-8")

        result = self.run_verify("scope", "--task", "05-26-other")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
