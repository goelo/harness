"""TDD tests for task.py CLI — Slice 2.

Tests verify task lifecycle through the CLI interface:
  create → planning, start → in_progress, finish → clears session, archive → moves dir.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# The init script sets up .harness/scripts/task.py as a stub.
# We'll test the real task.py that lives at the project root level .harness/scripts/task.py.


def _run_task(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    """Run task.py in the given project directory."""
    task_script = project_dir / ".harness" / "scripts" / "task.py"
    env = os.environ.copy()
    env["HARNESS_CONTEXT_ID"] = "test-session-001"
    return subprocess.run(
        [sys.executable, str(task_script), *args],
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env=env,
    )


def _run_task_without_session(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    """Run task.py without HARNESS_CONTEXT_ID, matching Codex shell behavior."""
    task_script = project_dir / ".harness" / "scripts" / "task.py"
    env = os.environ.copy()
    env.pop("HARNESS_CONTEXT_ID", None)
    return subprocess.run(
        [sys.executable, str(task_script), *args],
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env=env,
    )


class TestTaskCreate(unittest.TestCase):
    """task.py create produces a task directory with correct initial state."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        # Bootstrap harness structure
        harness = self.project_dir / ".harness"
        (harness / "tasks").mkdir(parents=True)
        (harness / "runtime" / "sessions").mkdir(parents=True)
        (harness / "scripts").mkdir(parents=True)
        # Copy real task.py (we'll write it)
        real_task = Path(__file__).parent.parent / "harness_scripts" / "task.py"
        if real_task.is_file():
            shutil.copy(real_task, harness / "scripts" / "task.py")

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def test_create_makes_task_directory(self):
        """create produces .harness/tasks/<MM-DD-slug>/ with task.json status=planning."""
        result = _run_task(self.project_dir, "create", "Build login page")
        self.assertEqual(result.returncode, 0, result.stderr)

        # Find created task dir
        tasks_dir = self.project_dir / ".harness" / "tasks"
        task_dirs = [d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive"]
        self.assertEqual(len(task_dirs), 1)

        task_dir = task_dirs[0]
        self.assertTrue((task_dir / "task.json").is_file())

        data = json.loads((task_dir / "task.json").read_text())
        self.assertEqual(data["status"], "planning")
        self.assertEqual(data["title"], "Build login page")

    def test_create_seeds_context_manifests(self):
        """v1.6: create produces 3 role-specific JSONL manifests (architect/developer/tester).

        Roles requiring manifests: architect, developer, tester.
        """
        _run_task(self.project_dir, "create", "Add auth")

        tasks_dir = self.project_dir / ".harness" / "tasks"
        task_dirs = [d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive"]
        task_dir = task_dirs[0]

        for role in ("architect", "developer", "tester"):
            manifest = task_dir / f"context.{role}.jsonl"
            self.assertTrue(manifest.is_file(), f"context.{role}.jsonl not created")

        # Old roles should NOT have manifests
        for old_role in ("research", "reviewer", "qa"):
            manifest = task_dir / f"context.{old_role}.jsonl"
            self.assertFalse(manifest.is_file(),
                f"context.{old_role}.jsonl should not exist in v1.6")

    def test_create_makes_research_directory(self):
        """create produces an empty research/ subdirectory."""
        _run_task(self.project_dir, "create", "Research APIs")

        tasks_dir = self.project_dir / ".harness" / "tasks"
        task_dirs = [d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive"]
        task_dir = task_dirs[0]

        self.assertTrue((task_dir / "research").is_dir())

    def test_create_activates_session(self):
        """create auto-sets the active task in runtime/sessions/."""
        _run_task(self.project_dir, "create", "My task")

        session_file = (
            self.project_dir / ".harness" / "runtime" / "sessions" / "test-session-001.json"
        )
        self.assertTrue(session_file.is_file())
        data = json.loads(session_file.read_text())
        self.assertIn("current_task", data)


class TestTaskStart(unittest.TestCase):
    """task.py start flips status from planning to in_progress, gated on Phase 1.3."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        harness = self.project_dir / ".harness"
        (harness / "tasks").mkdir(parents=True)
        (harness / "runtime" / "sessions").mkdir(parents=True)
        (harness / "scripts").mkdir(parents=True)
        real_task = Path(__file__).parent.parent / "harness_scripts" / "task.py"
        if real_task.is_file():
            shutil.copy(real_task, harness / "scripts" / "task.py")

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def _curate_all_manifests(self, task_dir: Path) -> None:
        """v1.6: add a real entry to all 3 manifests so Phase 1.3 gate passes."""
        for role in ("architect", "developer", "tester"):
            (task_dir / f"context.{role}.jsonl").write_text(
                '{"file": ".harness/spec/index.md", "reason": "spec"}\n',
                encoding="utf-8",
            )

    def test_start_flips_to_in_progress_when_manifests_curated(self):
        """start succeeds when all 3 manifests have real entries."""
        _run_task(self.project_dir, "create", "Test task")
        tasks_dir = self.project_dir / ".harness" / "tasks"
        task_dir = next(d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive")

        self._curate_all_manifests(task_dir)

        result = _run_task(self.project_dir, "start", task_dir.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((task_dir / "task.json").read_text())
        self.assertEqual(data["status"], "in_progress")

    def test_start_fails_when_manifests_seed_only(self):
        """start refuses when any manifest still has only the _example seed row."""
        _run_task(self.project_dir, "create", "Test task")
        tasks_dir = self.project_dir / ".harness" / "tasks"
        task_dir = next(d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive")

        # Don't curate — manifests are seed-only
        result = _run_task(self.project_dir, "start", task_dir.name)
        self.assertNotEqual(result.returncode, 0, "start should have failed but didn't")

        # Helpful error message
        combined = (result.stdout + result.stderr).lower()
        self.assertTrue(
            "manifest" in combined or "phase 1.3" in combined or "curate" in combined,
            f"Error message should mention manifest/curate. Got:\n{result.stdout}\n{result.stderr}",
        )

        # Status NOT changed
        data = json.loads((task_dir / "task.json").read_text())
        self.assertEqual(data["status"], "planning")

    def test_start_fails_when_partial_curation(self):
        """start refuses when only some manifests are curated."""
        _run_task(self.project_dir, "create", "Test task")
        tasks_dir = self.project_dir / ".harness" / "tasks"
        task_dir = next(d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive")

        # Only curate developer
        (task_dir / "context.developer.jsonl").write_text(
            '{"file": ".harness/spec/index.md", "reason": "spec"}\n',
            encoding="utf-8",
        )

        result = _run_task(self.project_dir, "start", task_dir.name)
        self.assertNotEqual(result.returncode, 0)

    def test_start_force_bypasses_gate(self):
        """start --force bypasses the Phase 1.3 gate (escape hatch for special cases)."""
        _run_task(self.project_dir, "create", "Test task")
        tasks_dir = self.project_dir / ".harness" / "tasks"
        task_dir = next(d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive")

        result = _run_task(self.project_dir, "start", task_dir.name, "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((task_dir / "task.json").read_text())
        self.assertEqual(data["status"], "in_progress")


class TestTaskArchive(unittest.TestCase):
    """task.py archive moves task to archive/YYYY-MM/."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        harness = self.project_dir / ".harness"
        (harness / "tasks" / "archive").mkdir(parents=True)
        (harness / "runtime" / "sessions").mkdir(parents=True)
        (harness / "scripts").mkdir(parents=True)
        real_task = Path(__file__).parent.parent / "harness_scripts" / "task.py"
        if real_task.is_file():
            shutil.copy(real_task, harness / "scripts" / "task.py")

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def test_archive_moves_to_archive_dir(self):
        """archive moves task directory under archive/YYYY-MM/."""
        _run_task(self.project_dir, "create", "Done task")

        tasks_dir = self.project_dir / ".harness" / "tasks"
        task_dirs = [d for d in tasks_dir.iterdir() if d.is_dir() and d.name != "archive"]
        task_dir = task_dirs[0]
        task_name = task_dir.name

        # Start then archive
        _run_task(self.project_dir, "start", task_name)
        result = _run_task(self.project_dir, "archive", task_name)
        self.assertEqual(result.returncode, 0, result.stderr)

        # Original location gone
        self.assertFalse(task_dir.exists())

        # Now in archive/YYYY-MM/
        archive_dir = tasks_dir / "archive"
        archived = list(archive_dir.rglob("task.json"))
        self.assertTrue(len(archived) > 0, "No archived task.json found")

        data = json.loads(archived[0].read_text())
        self.assertEqual(data["status"], "archived")


class TestTaskCurrent(unittest.TestCase):
    """task.py current reports the active task."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        harness = self.project_dir / ".harness"
        (harness / "tasks").mkdir(parents=True)
        (harness / "runtime" / "sessions").mkdir(parents=True)
        (harness / "scripts").mkdir(parents=True)
        real_task = Path(__file__).parent.parent / "harness_scripts" / "task.py"
        if real_task.is_file():
            shutil.copy(real_task, harness / "scripts" / "task.py")

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def test_current_shows_active_task(self):
        """current outputs the active task name and status."""
        _run_task(self.project_dir, "create", "Active work")
        result = _run_task(self.project_dir, "current")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Active work", result.stdout)

    def test_current_uses_local_session_when_context_id_missing(self):
        """Codex shell commands have no HARNESS_CONTEXT_ID, so task.py uses local session."""
        create = _run_task_without_session(self.project_dir, "create", "Codex active work")
        self.assertEqual(create.returncode, 0, create.stderr)

        session_file = (
            self.project_dir / ".harness" / "runtime" / "sessions" / "local.json"
        )
        self.assertTrue(session_file.is_file())

        current = _run_task_without_session(self.project_dir, "current")
        self.assertEqual(current.returncode, 0, current.stderr)
        self.assertIn("Codex active work", current.stdout)


if __name__ == "__main__":
    unittest.main()
