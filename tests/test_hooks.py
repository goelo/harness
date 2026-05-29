"""Tests for harness hook scripts under docs/tasks state machine."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _run_hook(hook_path: Path, stdin_data: dict, cwd: str | None = None) -> dict:
    result = subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(stdin_data),
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        return {"_error": result.stderr, "_returncode": result.returncode}
    if not result.stdout.strip():
        return {"_empty": True}
    return json.loads(result.stdout)


class HookTestCase(unittest.TestCase):
    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        harness = self.project_dir / ".harness"
        (harness / "runtime" / "sessions").mkdir(parents=True)
        (self.project_dir / "docs" / "tasks").mkdir(parents=True)
        (self.project_dir / "docs" / "standards").mkdir(parents=True)
        (self.project_dir / "docs" / "standards" / "index.md").write_text(
            "# 团队工程规范\n使用 Go 单元测试。\n", encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def write_task(self, phase: str = "green") -> Path:
        task_dir = self.project_dir / "docs" / "tasks" / "05-28-order"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.json").write_text(
            json.dumps(
                {
                    "status": "in_progress",
                    "phase": phase,
                    "title": "订单超时控制",
                    "executionMode": "agent-team",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (task_dir / "clarification.md").write_text("# 需求确认\n\n开发意图已确认。\n", encoding="utf-8")
        (task_dir / "implementation-plan.md").write_text("# 实现计划\n\n使用 PostgreSQL。\n", encoding="utf-8")
        (self.project_dir / "src").mkdir(exist_ok=True)
        (self.project_dir / "src" / "order.py").write_text("x = 1\n", encoding="utf-8")
        for role in ("architect", "developer", "tester"):
            (task_dir / f"context.{role}.jsonl").write_text(
                '{"file":"src/order.py","reason":"相关实现"}\n',
                encoding="utf-8",
            )
        (self.project_dir / ".harness" / "runtime" / "sessions" / "sess-1.json").write_text(
            json.dumps({"current_task": "docs/tasks/05-28-order"}),
            encoding="utf-8",
        )
        return task_dir


class TestWorkflowStateHook(HookTestCase):
    def setUp(self):
        super().setUp()
        (self.project_dir / ".harness" / "workflow.md").write_text(
            "[workflow-phase:no_task]\n没有当前任务。\n[/workflow-phase:no_task]\n\n"
            "[workflow-phase:clarify]\n当前处于需求确认阶段。\n[/workflow-phase:clarify]\n\n"
            "[workflow-phase:green]\n当前处于编码实现阶段。\n[/workflow-phase:green]\n",
            encoding="utf-8",
        )
        self.hook_path = Path(__file__).parent.parent / "harness_hooks" / "harness-workflow-state.py"

    def test_no_task_uses_no_task_phase(self):
        output = _run_hook(self.hook_path, {"cwd": str(self.project_dir)})
        ctx = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("<workflow-state>", ctx)
        self.assertIn("没有当前任务", ctx)

    def test_task_uses_phase_not_status(self):
        self.write_task(phase="green")
        output = _run_hook(self.hook_path, {"cwd": str(self.project_dir), "session_id": "sess-1"})
        ctx = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Phase: green", ctx)
        self.assertIn("编码实现阶段", ctx)


class TestSessionStartHook(HookTestCase):
    def setUp(self):
        super().setUp()
        self.hook_path = Path(__file__).parent.parent / "harness_hooks" / "harness-session-start.py"

    def test_includes_active_task_phase_and_natural_language_commands(self):
        self.write_task(phase="plan")
        output = _run_hook(self.hook_path, {"cwd": str(self.project_dir), "session_id": "sess-1"})
        ctx = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("订单超时控制", ctx)
        self.assertIn("plan", ctx)
        self.assertIn("继续需求开发", ctx)
        self.assertIn("查看当前需求开发状态", ctx)

    def test_exports_context_id_to_claude_env_file(self):
        env_file = self.project_dir / "claude_env"
        env_file.write_text("", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(self.hook_path)],
            input=json.dumps({"cwd": str(self.project_dir), "session_id": "sess-xyz"}),
            capture_output=True,
            text=True,
            env={**os.environ, "CLAUDE_ENV_FILE": str(env_file)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("export HARNESS_CONTEXT_ID=", env_file.read_text(encoding="utf-8"))


class TestInjectContextHook(HookTestCase):
    def setUp(self):
        super().setUp()
        self.hook_path = Path(__file__).parent.parent / "harness_hooks" / "harness-inject-context.py"

    def dispatch(self, role: str, *, phase: str, prompt: str = "Do work") -> dict:
        self.write_task(phase=phase)
        return _run_hook(
            self.hook_path,
            {
                "cwd": str(self.project_dir),
                "session_id": "sess-1",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": role, "prompt": prompt},
            },
        )

    def test_developer_green_gets_fixed_context(self):
        output = self.dispatch("developer", phase="green", prompt="实现代码")
        prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
        self.assertIn("开发意图已确认", prompt)
        self.assertIn("使用 PostgreSQL", prompt)
        self.assertIn("使用 Go 单元测试", prompt)
        self.assertIn("x = 1", prompt)
        self.assertIn("实现代码", prompt)

    def test_wrong_role_for_phase_is_blocked(self):
        output = self.dispatch("developer", phase="red", prompt="实现代码")
        ctx = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("当前阶段 red 不允许调用 developer", ctx)
        self.assertNotIn("updatedInput", output["hookSpecificOutput"])

    def test_architect_does_not_auto_read_research_directory(self):
        task_dir = self.write_task(phase="plan")
        research = task_dir / "research"
        research.mkdir()
        (research / "secret.md").write_text("# Research\n不应自动注入。\n", encoding="utf-8")
        output = _run_hook(
            self.hook_path,
            {
                "cwd": str(self.project_dir),
                "session_id": "sess-1",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": "architect", "prompt": "规划"},
            },
        )
        prompt = output["hookSpecificOutput"]["updatedInput"]["prompt"]
        self.assertNotIn("不应自动注入", prompt)

    def test_codex_spawn_agent_infers_role_from_task_name(self):
        self.write_task(phase="green")
        output = _run_hook(
            self.hook_path,
            {
                "cwd": str(self.project_dir),
                "session_id": "sess-1",
                "tool_name": "spawn_agent",
                "tool_input": {
                    "task_name": "harness_developer",
                    "agent_type": "worker",
                    "message": "GREEN phase. Build it.",
                },
            },
        )
        message = output["hookSpecificOutput"]["updatedInput"]["message"]
        self.assertIn("使用 PostgreSQL", message)
        self.assertIn("GREEN phase. Build it.", message)


if __name__ == "__main__":
    unittest.main()
