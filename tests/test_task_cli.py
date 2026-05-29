"""Tests for task.py CLI with docs/tasks state machine."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _copy_task_script(project_dir: Path) -> None:
    scripts = project_dir / ".harness" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    real_task = Path(__file__).parent.parent / "harness_scripts" / "task.py"
    shutil.copy(real_task, scripts / "task.py")


def _run_task(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HARNESS_CONTEXT_ID"] = "test-session-001"
    return subprocess.run(
        [sys.executable, ".harness/scripts/task.py", *args],
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env=env,
    )


class TaskCliTestCase(unittest.TestCase):
    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        (self.project_dir / ".harness" / "runtime" / "sessions").mkdir(parents=True)
        (self.project_dir / "docs" / "tasks").mkdir(parents=True)
        (self.project_dir / "docs" / "standards").mkdir(parents=True)
        (self.project_dir / "docs" / "standards" / "index.md").write_text(
            "# 团队工程规范\n", encoding="utf-8"
        )
        _copy_task_script(self.project_dir)

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def task_dir(self) -> Path:
        tasks = [
            path
            for path in (self.project_dir / "docs" / "tasks").iterdir()
            if path.is_dir() and path.name != "archive"
        ]
        self.assertEqual(len(tasks), 1)
        return tasks[0]


class TestTaskCreate(TaskCliTestCase):
    def test_create_uses_docs_tasks_and_clarify_phase(self):
        result = _run_task(self.project_dir, "create", "订单超时控制", "--slug", "order-timeout")
        self.assertEqual(result.returncode, 0, result.stderr)

        task_dir = self.project_dir / "docs" / "tasks" / f"{task_dir_prefix()}-order-timeout"
        self.assertTrue(task_dir.is_dir())
        self.assertFalse((self.project_dir / ".harness" / "tasks").exists())

        data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(data["status"], "in_progress")
        self.assertEqual(data["phase"], "clarify")
        self.assertEqual(data["executionMode"], "agent-team")
        self.assertEqual(data["originIntent"], "requirement-development")
        self.assertEqual(data["phaseHistory"], [])

        self.assertTrue((task_dir / "clarification.jsonl").is_file())
        self.assertEqual((task_dir / "clarification.jsonl").read_text(encoding="utf-8"), "")
        for role in ("architect", "developer", "tester"):
            manifest = task_dir / f"context.{role}.jsonl"
            self.assertTrue(manifest.is_file())
            self.assertIn("_example", manifest.read_text(encoding="utf-8"))

        session = json.loads(
            (
                self.project_dir
                / ".harness"
                / "runtime"
                / "sessions"
                / "test-session-001.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(session["current_task"], f"docs/tasks/{task_dir.name}")

    def test_create_can_record_confirmation_origin(self):
        result = _run_task(
            self.project_dir,
            "create",
            "只确认需求",
            "--origin-intent",
            "requirement-confirmation",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.task_dir() / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(data["originIntent"], "requirement-confirmation")


class TestClarifyAndAdvance(TaskCliTestCase):
    def setUp(self):
        super().setUp()
        result = _run_task(self.project_dir, "create", "订单超时控制", "--slug", "order-timeout")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.task = self.task_dir()

    def test_advance_plan_requires_confirmed_clarification(self):
        result = _run_task(self.project_dir, "advance", "plan")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("clarification", result.stderr)
        data = json.loads((self.task / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(data["phase"], "clarify")
        self.assertEqual(data["phaseHistory"][-1]["event"], "advance_failed")

    def test_clarify_confirm_renders_markdown_and_allows_plan(self):
        result = _run_task(
            self.project_dir,
            "clarify",
            "confirm",
            "--development-intent",
            "增加订单超时控制能力",
            "--acceptance-criterion",
            "超时订单会被拒绝",
            "--boundary",
            "本次不修改支付流程",
            "--source-doc",
            "inline-request",
            "--source-hash",
            "sha256:test",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.task / "clarification.md").is_file())
        self.assertIn("增加订单超时控制能力", (self.task / "clarification.md").read_text(encoding="utf-8"))

        advance = _run_task(self.project_dir, "advance", "plan")
        self.assertEqual(advance.returncode, 0, advance.stderr)
        data = json.loads((self.task / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(data["phase"], "plan")
        self.assertEqual(data["sourceDocHash"], "sha256:test")

    def test_advance_red_checks_plan_scope_and_manifests(self):
        _confirm(self.project_dir)
        self.assertEqual(_run_task(self.project_dir, "advance", "plan").returncode, 0)

        missing = _run_task(self.project_dir, "advance", "red")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("implementation-plan.md", missing.stderr)

        write_valid_plan_package(self.project_dir, self.task)
        red = _run_task(self.project_dir, "advance", "red")
        self.assertEqual(red.returncode, 0, red.stderr)
        data = json.loads((self.task / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(data["phase"], "red")

    def test_intent_set_records_history(self):
        result = _run_task(self.project_dir, "intent", "set", "requirement-confirmation")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = _run_task(self.project_dir, "intent", "set", "requirement-development")
        self.assertEqual(result.returncode, 0, result.stderr)

        data = json.loads((self.task / "task.json").read_text(encoding="utf-8"))
        self.assertEqual(data["originIntent"], "requirement-development")
        self.assertEqual(data["phaseHistory"][-1]["event"], "origin_intent_updated")


class TestReviewAndArchive(TaskCliTestCase):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init"], cwd=self.project_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "tester"], cwd=self.project_dir, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=self.project_dir, check=True)
        (self.project_dir / "README.md").write_text("# demo\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.project_dir, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.project_dir, check=True, capture_output=True)
        self.assertEqual(_run_task(self.project_dir, "create", "订单超时控制").returncode, 0)
        self.task = self.task_dir()

    def test_review_record_writes_changed_files(self):
        (self.project_dir / "feature.txt").write_text("new\n", encoding="utf-8")
        result = _run_task(
            self.project_dir,
            "review",
            "record",
            "--spec-compliance",
            "passed",
            "--code-quality",
            "passed",
            "--summary",
            "符合实现计划",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        review = json.loads((self.task / "review-result.json").read_text(encoding="utf-8"))
        self.assertEqual(review["headRef"], "working-tree")
        self.assertIn("feature.txt", review["changedFiles"])
        self.assertEqual(review["specCompliance"]["status"], "passed")

    def test_archive_requires_done_phase(self):
        result = _run_task(self.project_dir, "archive", self.task.name)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("phase=done", result.stderr)

        data = json.loads((self.task / "task.json").read_text(encoding="utf-8"))
        data["phase"] = "done"
        data["status"] = "done"
        (self.task / "task.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (self.task / "verify-result.json").write_text(
            json.dumps({"success": True, "changedFiles": []}) + "\n",
            encoding="utf-8",
        )
        result = _run_task(self.project_dir, "archive", self.task.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        archived = list((self.project_dir / "docs" / "tasks" / "archive").rglob("task.json"))
        self.assertEqual(len(archived), 1)


def task_dir_prefix() -> str:
    from datetime import datetime

    return datetime.now().strftime("%m-%d")


def _confirm(project_dir: Path) -> None:
    result = _run_task(
        project_dir,
        "clarify",
        "confirm",
        "--development-intent",
        "增加订单超时控制能力",
        "--acceptance-criterion",
        "超时订单会被拒绝",
        "--boundary",
        "本次不修改支付流程",
        "--source-doc",
        "inline-request",
        "--source-hash",
        "sha256:test",
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)


def write_valid_plan_package(project_dir: Path, task_dir: Path) -> None:
    (project_dir / "src").mkdir(exist_ok=True)
    (project_dir / "src" / "order.py").write_text("x = 1\n", encoding="utf-8")
    (project_dir / "tests").mkdir(exist_ok=True)
    (project_dir / "tests" / "test_order.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (task_dir / "implementation-plan.md").write_text(
        """# 实现计划

## 开发意图摘要
增加订单超时控制能力。

## 影响范围
订单服务和测试。

## 技术方案
在订单服务中补充超时判断。

## 可测试契约
超时订单会被拒绝。

## Slice 顺序
1. 增加测试。

## 验证方式
运行订单测试。

## 已知限制
本次不修改支付流程。
""",
        encoding="utf-8",
    )
    (task_dir / "scope.json").write_text(
        json.dumps({"allowed": ["src/**", "tests/**"], "denied": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    for role in ("architect", "developer", "tester"):
        (task_dir / f"context.{role}.jsonl").write_text(
            '{"file":"src/order.py","reason":"本次需求相关实现"}\n',
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
