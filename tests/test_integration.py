"""Integration test — full harness loop.

Simulates the complete lifecycle:
  init → create task → start → dispatch implement (hook injects) → archive
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestFullHarnessLoop(unittest.TestCase):
    """End-to-end lifecycle through init, task management, and hooks."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        self.env = os.environ.copy()
        self.env["HARNESS_CONTEXT_ID"] = "integration-test-session"

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def _run(self, *cmd: str, cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, *cmd],
            capture_output=True,
            text=True,
            cwd=cwd or str(self.project_dir),
            env=self.env,
        )

    def _run_hook(self, hook_path: str, stdin_data: dict) -> dict:
        result = subprocess.run(
            [sys.executable, hook_path],
            input=json.dumps(stdin_data),
            capture_output=True,
            text=True,
            cwd=str(self.project_dir),
            env=self.env,
        )
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)

    def test_full_loop(self):
        """init → create → start → hook inject → archive completes without error."""
        init_script = str(Path(__file__).parent.parent / "init-harness.py")
        task_script = str(Path(__file__).parent.parent / "harness_scripts" / "task.py")
        inject_hook = str(Path(__file__).parent.parent / "harness_hooks" / "harness-inject-context.py")
        wf_hook = str(Path(__file__).parent.parent / "harness_hooks" / "harness-workflow-state.py")

        # 1. Init
        result = self._run(init_script, "--target", str(self.project_dir))
        self.assertEqual(result.returncode, 0, f"init failed: {result.stderr}")

        # Copy real task.py into .harness/scripts/ (init writes a stub)
        real_task = Path(__file__).parent.parent / "harness_scripts" / "task.py"
        shutil.copy(real_task, self.project_dir / ".harness" / "scripts" / "task.py")

        # 2. Create task
        result = self._run(
            str(self.project_dir / ".harness" / "scripts" / "task.py"),
            "create", "Implement auth",
        )
        self.assertEqual(result.returncode, 0, f"create failed: {result.stderr}")

        # Find task dir
        tasks_dir = self.project_dir / ".harness" / "tasks"
        task_dirs = [d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive"]
        self.assertEqual(len(task_dirs), 1)
        task_dir = task_dirs[0]

        # Verify planning status
        data = json.loads((task_dir / "task.json").read_text())
        self.assertEqual(data["status"], "planning")

        # 3. Write active task package docs + curate context manifests.
        (task_dir / "proposal.md").write_text("# Auth Proposal\n\n- Login endpoint\n")
        (task_dir / "design.md").write_text("# Auth Design\n\n- JWT claims\n")
        (task_dir / "tasks.md").write_text("# Auth Tasks\n\n- Add endpoint tests\n")
        for role in ("architect", "developer", "tester"):
            (task_dir / f"context.{role}.jsonl").write_text(
                '{"file": ".harness/spec/index.md", "reason": "team spec"}\n'
            )

        # 4. Start task
        result = self._run(
            str(self.project_dir / ".harness" / "scripts" / "task.py"),
            "start", task_dir.name,
        )
        self.assertEqual(result.returncode, 0, f"start failed: {result.stderr}")

        data = json.loads((task_dir / "task.json").read_text())
        self.assertEqual(data["status"], "in_progress")

        # 5. Workflow state hook should now emit in_progress
        output = self._run_hook(wf_hook, {
            "cwd": str(self.project_dir),
            "session_id": "integration-test-session",
        })
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("in_progress", ctx)

        # 6. Inject context hook for developer agent (renamed from implement in v1.1)
        output = self._run_hook(inject_hook, {
            "cwd": str(self.project_dir),
            "session_id": "integration-test-session",
            "tool_name": "Agent",
            "tool_input": {
                "subagent_type": "developer",
                "prompt": "Build the login endpoint",
            },
        })
        updated = output.get("hookSpecificOutput", {}).get("updatedInput", {})
        new_prompt = updated.get("prompt", "")
        self.assertIn("Login endpoint", new_prompt)
        self.assertIn("JWT claims", new_prompt)
        self.assertIn("Add endpoint tests", new_prompt)

        # 7. Archive
        result = self._run(
            str(self.project_dir / ".harness" / "scripts" / "task.py"),
            "archive", task_dir.name,
        )
        self.assertEqual(result.returncode, 0, f"archive failed: {result.stderr}")

        # Original gone, archived
        self.assertFalse(task_dir.exists())
        archive_dir = tasks_dir / "archive"
        archived = list(archive_dir.rglob("task.json"))
        self.assertTrue(len(archived) > 0)
        data = json.loads(archived[0].read_text())
        self.assertEqual(data["status"], "archived")


if __name__ == "__main__":
    unittest.main()
