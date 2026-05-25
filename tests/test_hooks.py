"""TDD tests for hook scripts — Slice 3 (v1.1 with 5 roles).

Tests simulate Claude Code hook behavior:
  stdin = JSON → script → stdout = JSON with hookSpecificOutput.

Each hook is tested through its subprocess interface.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _run_hook(hook_path: Path, stdin_data: dict, cwd: str | None = None) -> dict:
    """Run a hook script with JSON stdin, return parsed stdout."""
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


class TestWorkflowStateHook(unittest.TestCase):
    """workflow-state hook emits correct <workflow-state> based on task status."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        harness = self.project_dir / ".harness"
        (harness / "runtime" / "sessions").mkdir(parents=True)
        (harness / "tasks").mkdir(parents=True)

        # Write workflow.md with state blocks
        (harness / "workflow.md").write_text(
            "[workflow-state:no_task]\nNo active task. Create one.\n[/workflow-state:no_task]\n\n"
            "[workflow-state:planning]\nTask in planning. Confirm design.md.\n[/workflow-state:planning]\n\n"
            "[workflow-state:in_progress]\nTask active. Dispatch developer.\n[/workflow-state:in_progress]\n",
            encoding="utf-8",
        )

        self.hook_path = Path(__file__).parent.parent / "harness_hooks" / "harness-workflow-state.py"

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def test_no_task_emits_no_task_state(self):
        output = _run_hook(self.hook_path, {"cwd": str(self.project_dir)})
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("<workflow-state>", ctx)
        self.assertIn("No active task", ctx)

    def test_planning_task_emits_planning_state(self):
        harness = self.project_dir / ".harness"
        task_dir = harness / "tasks" / "05-19-test"
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(
            json.dumps({"status": "planning", "title": "Test"}), encoding="utf-8"
        )
        session_dir = harness / "runtime" / "sessions"
        (session_dir / "test-session.json").write_text(
            json.dumps({"current_task": ".harness/tasks/05-19-test"}), encoding="utf-8"
        )

        output = _run_hook(
            self.hook_path,
            {"cwd": str(self.project_dir), "session_id": "test-session"},
        )
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("planning", ctx.lower())
        self.assertIn("Confirm design.md", ctx)

    def test_in_progress_emits_in_progress_state(self):
        harness = self.project_dir / ".harness"
        task_dir = harness / "tasks" / "05-19-work"
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(
            json.dumps({"status": "in_progress", "title": "Work"}), encoding="utf-8"
        )
        session_dir = harness / "runtime" / "sessions"
        (session_dir / "test-session.json").write_text(
            json.dumps({"current_task": ".harness/tasks/05-19-work"}), encoding="utf-8"
        )

        output = _run_hook(
            self.hook_path,
            {"cwd": str(self.project_dir), "session_id": "test-session"},
        )
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("in_progress", ctx)
        self.assertIn("Dispatch developer", ctx)


class TestSessionStartHook(unittest.TestCase):
    """session-start hook injects active task info and role list."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        harness = self.project_dir / ".harness"
        (harness / "runtime" / "sessions").mkdir(parents=True)
        (harness / "tasks").mkdir(parents=True)
        (harness / "workflow.md").write_text("# Workflow\n", encoding="utf-8")

        self.hook_path = Path(__file__).parent.parent / "harness_hooks" / "harness-session-start.py"

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def test_emits_session_start_event(self):
        output = _run_hook(self.hook_path, {"cwd": str(self.project_dir)})
        self.assertEqual(
            output.get("hookSpecificOutput", {}).get("hookEventName"), "SessionStart"
        )

    def test_includes_all_5_roles(self):
        """Output mentions all 5 agent roles."""
        output = _run_hook(self.hook_path, {"cwd": str(self.project_dir)})
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        for role in ("research", "architect", "developer", "reviewer", "qa"):
            self.assertIn(role, ctx, f"role '{role}' missing from session-start output")

    def test_includes_active_task_info(self):
        harness = self.project_dir / ".harness"
        task_dir = harness / "tasks" / "05-19-feature"
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(
            json.dumps({"status": "in_progress", "title": "Build feature"}),
            encoding="utf-8",
        )
        (harness / "runtime" / "sessions" / "sess-1.json").write_text(
            json.dumps({"current_task": ".harness/tasks/05-19-feature"}),
            encoding="utf-8",
        )

        output = _run_hook(
            self.hook_path, {"cwd": str(self.project_dir), "session_id": "sess-1"}
        )
        ctx = output.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIn("Build feature", ctx)
        self.assertIn("in_progress", ctx)

    def test_exports_context_id_to_claude_env_file(self):
        """SessionStart hook appends `export HARNESS_CONTEXT_ID=...` to CLAUDE_ENV_FILE.

        Without this, task.py invocations from Bash tool can't resolve session
        identity and fail with "No session identity".
        """
        env_file = self.project_dir / "claude_env"
        env_file.write_text("", encoding="utf-8")

        # Run hook with CLAUDE_ENV_FILE set in env
        result = subprocess.run(
            [sys.executable, str(self.hook_path)],
            input=json.dumps({"cwd": str(self.project_dir), "session_id": "sess-xyz"}),
            capture_output=True,
            text=True,
            env={**os.environ, "CLAUDE_ENV_FILE": str(env_file)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        env_content = env_file.read_text(encoding="utf-8")
        self.assertIn("HARNESS_CONTEXT_ID=", env_content)
        # Should match the session_id (or derived from it)
        self.assertIn("sess-xyz", env_content)
        # Should be a valid shell export line
        self.assertTrue(
            "export HARNESS_CONTEXT_ID=" in env_content,
            f"Missing export keyword: {env_content!r}",
        )


class TestInjectContextHookAllRoles(unittest.TestCase):
    """v1.6: inject-context hook supports 3 roles (architect/developer/tester)."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        harness = self.project_dir / ".harness"
        (harness / "runtime" / "sessions").mkdir(parents=True)

        # Common task setup
        task_dir = harness / "tasks" / "05-19-mvp"
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(
            json.dumps({"status": "in_progress", "title": "MVP task"}),
            encoding="utf-8",
        )
        # v1.7: design doc lives at project root, NOT inside task dir.
        (self.project_dir / "design.md").write_text(
            "# Requirements\n\n- Feature A\n", encoding="utf-8"
        )
        (task_dir / "info.md").write_text("# Design\n\nUse PostgreSQL.\n", encoding="utf-8")

        # Spec
        spec_dir = harness / "spec"
        spec_dir.mkdir(parents=True)
        (spec_dir / "index.md").write_text("# Spec\nUse TypeScript.\n", encoding="utf-8")
        (spec_dir / "testing.md").write_text("# Testing\nTable-driven tests.\n", encoding="utf-8")

        # Research file
        research_dir = task_dir / "research"
        research_dir.mkdir(parents=True)
        (research_dir / "framework-choice.md").write_text(
            "# Framework\nGin chosen.\n", encoding="utf-8"
        )

        # Role-specific manifests
        (task_dir / "context.architect.jsonl").write_text(
            '{"file": ".harness/spec/index.md", "reason": "team conventions for design"}\n',
            encoding="utf-8",
        )
        (task_dir / "context.developer.jsonl").write_text(
            '{"file": ".harness/spec/index.md", "reason": "coding style"}\n',
            encoding="utf-8",
        )
        (task_dir / "context.tester.jsonl").write_text(
            '{"file": ".harness/spec/testing.md", "reason": "test conventions"}\n',
            encoding="utf-8",
        )

        # Session pointer
        (harness / "runtime" / "sessions" / "sess-1.json").write_text(
            json.dumps({"current_task": ".harness/tasks/05-19-mvp"}),
            encoding="utf-8",
        )

        self.hook_path = Path(__file__).parent.parent / "harness_hooks" / "harness-inject-context.py"

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def _dispatch(self, role: str, prompt: str = "Do work") -> str:
        """Dispatch a sub-agent via the hook, return the modified prompt."""
        output = _run_hook(self.hook_path, {
            "cwd": str(self.project_dir),
            "session_id": "sess-1",
            "tool_name": "Agent",
            "tool_input": {"subagent_type": role, "prompt": prompt},
        })
        return output.get("hookSpecificOutput", {}).get("updatedInput", {}).get("prompt", "")

    def test_architect_gets_prd_research_and_manifest(self):
        """architect reads project-root design.md + research/*.md + context.architect.jsonl files."""
        prompt = self._dispatch("architect", "Decide framework")
        self.assertIn("Feature A", prompt, "design.md not injected")
        # Manifest references spec/index.md whose content is "Use TypeScript"
        self.assertIn("Use TypeScript", prompt, "Spec content not injected")
        # Architect special: research/*.md is auto-included
        self.assertIn("Gin chosen", prompt, "research file not auto-included for architect")

    def test_developer_gets_prd_info_and_manifest(self):
        """developer reads project-root design.md + info.md + context.developer.jsonl files."""
        prompt = self._dispatch("developer", "Implement add endpoint")
        self.assertIn("Feature A", prompt, "design.md not injected")
        self.assertIn("Use PostgreSQL", prompt, "info.md not injected")
        self.assertIn("Use TypeScript", prompt, "developer manifest not loaded")

    def test_task_package_docs_override_project_root_design(self):
        """task package proposal/design/tasks docs are injected before root design fallback."""
        task_dir = self.project_dir / ".harness" / "tasks" / "05-19-mvp"
        (task_dir / "proposal.md").write_text(
            "# Proposal\n\nTask package proposal\n", encoding="utf-8"
        )
        (task_dir / "design.md").write_text(
            "# Task Design\n\nTask package design\n", encoding="utf-8"
        )
        (task_dir / "tasks.md").write_text(
            "# Tasks\n\nTask package task list\n", encoding="utf-8"
        )

        prompt = self._dispatch("developer", "Implement add endpoint")

        self.assertIn("Task package proposal", prompt)
        self.assertIn("Task package design", prompt)
        self.assertIn("Task package task list", prompt)
        self.assertNotIn("Feature A", prompt, "root design.md should be fallback only")

    def test_project_root_design_is_fallback_when_task_package_docs_missing(self):
        """project-root design.md is still injected for older task packages."""
        prompt = self._dispatch("developer", "Implement add endpoint")

        self.assertIn("Feature A", prompt, "root design.md fallback not injected")

    def test_tester_gets_prd_info_and_manifest(self):
        """tester reads project-root design.md + info.md + context.tester.jsonl files."""
        prompt = self._dispatch("tester", "Write tests")
        self.assertIn("Feature A", prompt)
        self.assertIn("Use PostgreSQL", prompt)
        self.assertIn("Table-driven tests", prompt, "tester manifest not loaded")

    def test_old_role_names_rejected(self):
        """v1.6: old role names (research/reviewer/qa) are no longer recognized."""
        for old_role in ("research", "reviewer", "qa"):
            output = _run_hook(self.hook_path, {
                "cwd": str(self.project_dir),
                "session_id": "sess-1",
                "tool_name": "Agent",
                "tool_input": {"subagent_type": old_role, "prompt": "x"},
            })
            self.assertTrue(
                output.get("_empty") or output.get("_returncode") == 0,
                f"old role '{old_role}' should silently exit, got: {output}",
            )

    def test_each_role_gets_its_own_manifest_only(self):
        """developer should NOT leak tester's testing manifest, tester should NOT leak developer's."""
        dev_prompt = self._dispatch("developer", "Write code")
        tester_prompt = self._dispatch("tester", "Write tests")

        # developer manifest references spec/index.md → "Use TypeScript"
        # tester manifest references spec/testing.md → "Table-driven tests"
        self.assertIn("Use TypeScript", dev_prompt)
        self.assertNotIn("Table-driven tests", dev_prompt,
            "developer leaked tester manifest content")

        self.assertIn("Table-driven tests", tester_prompt)

    def test_ignores_unknown_role(self):
        output = _run_hook(self.hook_path, {
            "cwd": str(self.project_dir),
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "unknown-role", "prompt": "x"},
        })
        self.assertTrue(
            output.get("_empty") or output.get("_returncode") == 0,
            f"Expected silent exit, got: {output}",
        )

    def test_skips_seed_rows_in_jsonl(self):
        """Seed rows (no file field) are skipped without error."""
        task_dir = self.project_dir / ".harness" / "tasks" / "05-19-mvp"
        (task_dir / "context.developer.jsonl").write_text(
            '{"_example": "seed row"}\n'
            '{"file": ".harness/spec/index.md", "reason": "guidelines"}\n',
            encoding="utf-8",
        )

        prompt = self._dispatch("developer", "Build it")
        self.assertIn("Use TypeScript", prompt)
        self.assertNotIn("_example", prompt)

    def test_codex_spawn_agent_infers_role_from_task_name(self):
        """Codex spawn_agent has no subagent_type, so role is inferred from task_name."""
        output = _run_hook(self.hook_path, {
            "cwd": str(self.project_dir),
            "session_id": "sess-1",
            "tool_name": "spawn_agent",
            "tool_input": {
                "task_name": "harness_developer",
                "agent_type": "worker",
                "message": "GREEN phase. Build it.",
            },
        })

        updated = output.get("hookSpecificOutput", {}).get("updatedInput", {})
        message = updated.get("message", "")
        self.assertIn("Use TypeScript", message)
        self.assertIn("Feature A", message)
        self.assertIn("Use PostgreSQL", message)
        self.assertIn("GREEN phase. Build it.", message)

    def test_codex_followup_task_infers_role_from_target(self):
        """Codex followup_task receives the role name through target."""
        output = _run_hook(self.hook_path, {
            "cwd": str(self.project_dir),
            "session_id": "sess-1",
            "tool_name": "followup_task",
            "tool_input": {
                "target": "harness_tester",
                "message": "VALIDATE phase. Add edge cases.",
            },
        })

        updated = output.get("hookSpecificOutput", {}).get("updatedInput", {})
        message = updated.get("message", "")
        self.assertIn("Table-driven tests", message)
        self.assertIn("Feature A", message)
        self.assertIn("Use PostgreSQL", message)
        self.assertIn("VALIDATE phase. Add edge cases.", message)


if __name__ == "__main__":
    unittest.main()
