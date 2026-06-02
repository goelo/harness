"""Integration test for the docs/tasks state machine."""

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
        result = self._run(init_script, "--target", str(self.project_dir), "--no-rtk", "--no-caveman", "--no-cooper")
        self.assertEqual(result.returncode, 0, f"init failed: {result.stderr}")

        # 2. Create task
        result = self._run(
            str(self.project_dir / ".harness" / "scripts" / "task.py"),
            "create", "Implement auth",
        )
        self.assertEqual(result.returncode, 0, f"create failed: {result.stderr}")

        # Find task dir
        tasks_dir = self.project_dir / "docs" / "tasks"
        task_dirs = [d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive"]
        self.assertEqual(len(task_dirs), 1)
        task_dir = task_dirs[0]

        # Verify clarify phase.
        data = json.loads((task_dir / "task.json").read_text())
        self.assertEqual(data["status"], "in_progress")
        self.assertEqual(data["phase"], "clarify")

        # 3. Confirm requirement and enter doc-plan.
        result = self._run(
            str(self.project_dir / ".harness" / "scripts" / "task.py"),
            "clarify", "confirm",
            "--development-intent", "实现登录接口。",
            "--acceptance-criterion", "登录成功返回 token。",
            "--boundary", "本次不实现注册。",
            "--source-doc", "inline-request",
            "--source-hash", "sha256:integration",
        )
        self.assertEqual(result.returncode, 0, f"clarify failed: {result.stderr}")
        result = self._run(str(self.project_dir / ".harness" / "scripts" / "task.py"), "advance", "doc-plan")
        self.assertEqual(result.returncode, 0, f"advance doc-plan failed: {result.stderr}")

        # 4. Write plan evidence and enter RED.
        (task_dir / "implementation-plan.md").write_text(
            """# 实现计划

## 开发意图摘要
实现登录接口。

## 影响范围
新增认证模块和测试。

## 技术方案
使用现有 HTTP 层。

## 可测试契约
登录成功返回 token。

## 业务契约覆盖
BC-001 由登录成功测试覆盖。

## Slice 顺序
1. 登录接口。

## 验证方式
运行目标测试。

## 已知限制
本次不实现注册。
""",
            encoding="utf-8",
        )
        (task_dir / "scope.json").write_text(json.dumps({"allowed": ["docs/tasks/**"], "denied": []}), encoding="utf-8")
        for role in ("architect", "developer", "tester"):
            (task_dir / f"context.{role}.jsonl").write_text(
                '{"file": "docs/standards/index.md", "reason": "团队工程规范"}\n',
                encoding="utf-8",
            )
        result = self._run(str(self.project_dir / ".harness" / "scripts" / "task.py"), "advance", "red")
        self.assertEqual(result.returncode, 0, f"advance red failed: {result.stderr}")

        data = json.loads((task_dir / "task.json").read_text())
        self.assertEqual(data["phase"], "red")

        # 5. Workflow state hook should emit the current phase.
        output = self._run_hook(wf_hook, {
            "cwd": str(self.project_dir),
            "session_id": "integration-test-session",
        })
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("Phase: red", ctx)

        # 6. Write RED and GREEN evidence, then inject context for developer.
        result = self._run(
            str(self.project_dir / ".harness" / "scripts" / "verify.py"),
            "red",
            "--command", "false",
            "--target-test", "auth::login",
        )
        self.assertEqual(result.returncode, 0, f"verify red failed: {result.stderr}")
        result = self._run(str(self.project_dir / ".harness" / "scripts" / "task.py"), "advance", "green")
        self.assertEqual(result.returncode, 0, f"advance green failed: {result.stderr}")

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
        self.assertIn("实现登录接口", new_prompt)
        self.assertIn("implementation-plan.md", new_prompt)
        self.assertIn("docs/standards/index.md", new_prompt)

        result = self._run(
            str(self.project_dir / ".harness" / "scripts" / "verify.py"),
            "green",
            "--command", "true",
            "--target-test", "auth::login",
        )
        self.assertEqual(result.returncode, 0, f"verify green failed: {result.stderr}")
        result = self._run(str(self.project_dir / ".harness" / "scripts" / "task.py"), "advance", "review")
        self.assertEqual(result.returncode, 0, f"advance review failed: {result.stderr}")
        result = self._run(
            str(self.project_dir / ".harness" / "scripts" / "task.py"),
            "review", "record",
            "--spec-compliance", "passed",
            "--code-quality", "passed",
            "--summary", "通过",
        )
        self.assertEqual(result.returncode, 0, f"review record failed: {result.stderr}")
        result = self._run(str(self.project_dir / ".harness" / "scripts" / "task.py"), "advance", "validate")
        self.assertEqual(result.returncode, 0, f"advance validate failed: {result.stderr}")

        verify_config = json.loads((self.project_dir / ".harness" / "verify.json").read_text(encoding="utf-8"))
        verify_config["commands"]["test"] = "true"
        (self.project_dir / ".harness" / "verify.json").write_text(json.dumps(verify_config), encoding="utf-8")
        result = self._run(str(self.project_dir / ".harness" / "scripts" / "verify.py"), "all")
        self.assertEqual(result.returncode, 0, f"verify all failed: {result.stderr}")
        result = self._run(str(self.project_dir / ".harness" / "scripts" / "task.py"), "advance", "done")
        self.assertEqual(result.returncode, 0, f"advance done failed: {result.stderr}")

        # 7. Archive.
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
