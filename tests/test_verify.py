"""Tests for .harness/scripts/verify.py evidence generation."""

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
        self.tasks_dir = self.project_dir / "docs" / "tasks"
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

    def write_config(self, *, lint="", typecheck="", test="true", coverage="", required=None, denied=None):
        config = {
            "commands": {
                "lint": lint,
                "type": typecheck,
                "test": test,
                "coverage": coverage,
            },
            "required": required if required is not None else ["test", "scope"],
            "scope": {
                "denied": denied if denied is not None else [".harness/runtime/**", "docs/standards/**"],
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
                json.dumps({"current_task": f"docs/tasks/{name}"}) + "\n",
                encoding="utf-8",
            )
        subprocess.run(
            ["git", "add", ".harness/scripts/verify.py", ".harness/verify.json", str(task_dir.relative_to(self.project_dir))],
            cwd=self.project_dir,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"add harness config {name}"],
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


class TestVerifyAll(VerifyScriptTestCase):
    def test_all_requires_only_configured_required_checks(self):
        self.write_config(test="true", required=["test", "scope"])
        self.write_task(allowed=["src/**"])
        (self.project_dir / "src").mkdir()
        (self.project_dir / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")

        result = self.run_verify("all")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        verify_result = json.loads((self.write_task_dir() / "verify-result.json").read_text(encoding="utf-8"))
        self.assertTrue(verify_result["success"])
        self.assertEqual([item["name"] for item in verify_result["commands"]], ["test"])
        self.assertIn("src/app.py", verify_result["changedFiles"])

    def test_all_fails_when_required_command_missing(self):
        self.write_config(test="", required=["test", "scope"])
        self.write_task()

        result = self.run_verify("all")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commands.test", result.stderr)
        verify_result = json.loads((self.write_task_dir() / "verify-result.json").read_text(encoding="utf-8"))
        self.assertFalse(verify_result["success"])

    def test_scope_uses_docs_tasks_and_task_argument(self):
        self.write_config()
        self.write_task("05-26-current", allowed=["src/**"], make_current=True)
        self.write_task("05-26-other", allowed=["docs/**"], make_current=False)
        (self.project_dir / "docs" / "notes").mkdir(parents=True)
        (self.project_dir / "docs" / "notes" / "plan.md").write_text("# plan\n", encoding="utf-8")

        result = self.run_verify("scope", "--task", "05-26-other")

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_scope_fails_for_denied_file(self):
        self.write_config(denied=["src/generated/**"])
        self.write_task(allowed=["src/**"])
        (self.project_dir / "src" / "generated").mkdir(parents=True)
        (self.project_dir / "src" / "generated" / "api.py").write_text("x = 1\n", encoding="utf-8")

        result = self.run_verify("scope")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("denied", result.stderr)

    def write_task_dir(self) -> Path:
        return self.tasks_dir / "05-26-demo"


class TestRedGreenEvidence(VerifyScriptTestCase):
    def setUp(self):
        super().setUp()
        self.write_config()
        self.task_dir = self.write_task()

    def test_red_records_expected_failure(self):
        result = self.run_verify(
            "red",
            "--command",
            "exit 7",
            "--target-test",
            "TestCreateOrder",
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        data = json.loads((self.task_dir / "test-result.red.json").read_text(encoding="utf-8"))
        self.assertTrue(data["expectedFailureObserved"])
        self.assertEqual(data["exitCode"], 7)
        self.assertEqual(data["targetTests"], ["TestCreateOrder"])

    def test_red_records_contract_coverage(self):
        result = self.run_verify(
            "red",
            "--command",
            "exit 7",
            "--target-test",
            "TestCreateOrder",
            "--contract-coverage",
            "BC-001=TestCreateOrder",
            "--uncovered-contract",
            "BC-002",
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        data = json.loads((self.task_dir / "test-result.red.json").read_text(encoding="utf-8"))
        self.assertEqual(data["contractCoverage"], {"BC-001": ["TestCreateOrder"]})
        self.assertEqual(data["uncoveredContracts"], ["BC-002"])

    def test_red_fails_when_command_passes(self):
        result = self.run_verify(
            "red",
            "--command",
            "true",
            "--target-test",
            "TestCreateOrder",
        )

        self.assertNotEqual(result.returncode, 0)
        data = json.loads((self.task_dir / "test-result.red.json").read_text(encoding="utf-8"))
        self.assertFalse(data["expectedFailureObserved"])

    def test_green_records_expected_pass(self):
        result = self.run_verify(
            "green",
            "--command",
            "true",
            "--target-test",
            "TestCreateOrder",
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        data = json.loads((self.task_dir / "test-result.green.json").read_text(encoding="utf-8"))
        self.assertTrue(data["expectedPassObserved"])
        self.assertEqual(data["targetTests"], ["TestCreateOrder"])

    def test_green_records_contract_coverage(self):
        result = self.run_verify(
            "green",
            "--command",
            "true",
            "--target-test",
            "TestCreateOrder",
            "--contract-coverage",
            "BC-001=TestCreateOrder,TestCreateOrderAudit",
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        data = json.loads((self.task_dir / "test-result.green.json").read_text(encoding="utf-8"))
        self.assertEqual(data["contractCoverage"], {"BC-001": ["TestCreateOrder", "TestCreateOrderAudit"]})
        self.assertEqual(data["uncoveredContracts"], [])


if __name__ == "__main__":
    unittest.main()
