"""Tests for init-harness.py observable install behavior."""

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
INIT_SCRIPT = REPO_ROOT / "init-harness.py"


class InitHarnessTestCase(unittest.TestCase):
    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        self.home_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.project_dir)
        shutil.rmtree(self.home_dir)

    def run_init(self, *extra_args):
        args = [sys.executable, str(INIT_SCRIPT), "--target", str(self.project_dir)]
        if "--check-deps" not in extra_args:
            if "--no-rtk" not in extra_args:
                args.append("--no-rtk")
            if "--no-caveman" not in extra_args:
                args.append("--no-caveman")
        args.extend(extra_args)
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.home_dir)},
        )


class TestInitHarnessStructure(InitHarnessTestCase):
    def test_creates_harness_and_docs_structure(self):
        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stderr)

        harness = self.project_dir / ".harness"
        self.assertTrue((harness / "workflow.md").is_file())
        self.assertTrue((harness / "verify.json").is_file())
        self.assertTrue((harness / "runtime" / "sessions").is_dir())
        self.assertTrue((harness / "scripts" / "task.py").is_file())
        self.assertTrue((harness / "scripts" / "verify.py").is_file())
        self.assertTrue((harness / "scripts" / "context.py").is_file())
        self.assertFalse((harness / "tasks").exists())
        self.assertFalse((harness / "spec").exists())

        self.assertTrue((self.project_dir / "docs" / "tasks").is_dir())
        self.assertTrue((self.project_dir / "docs" / "standards").is_dir())
        self.assertTrue((self.project_dir / "docs" / "index.md").is_file())
        self.assertTrue((self.project_dir / "docs" / "standards" / "index.md").is_file())

    def test_verify_config_template_uses_required_checks(self):
        self.run_init()

        config = json.loads((self.project_dir / ".harness" / "verify.json").read_text(encoding="utf-8"))

        self.assertEqual(config["required"], ["test", "scope"])
        self.assertEqual(sorted(config["commands"].keys()), ["coverage", "lint", "test", "type"])
        self.assertIn(".harness/runtime/**", config["scope"]["denied"])
        self.assertIn("docs/standards/**", config["scope"]["denied"])

    def test_does_not_overwrite_existing_verify_config(self):
        harness = self.project_dir / ".harness"
        harness.mkdir()
        existing = {"required": ["lint"], "commands": {"lint": "custom lint"}, "scope": {"denied": ["custom/**"]}}
        (harness / "verify.json").write_text(json.dumps(existing), encoding="utf-8")

        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stderr)

        config = json.loads((harness / "verify.json").read_text(encoding="utf-8"))
        self.assertEqual(config, existing)

    def test_docs_index_is_preserved_and_augmented(self):
        docs = self.project_dir / "docs"
        docs.mkdir()
        (docs / "index.md").write_text("# Existing Docs\n\n业务文档说明。\n", encoding="utf-8")

        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stderr)

        content = (docs / "index.md").read_text(encoding="utf-8")
        self.assertIn("业务文档说明", content)
        self.assertIn("docs/tasks/", content)
        self.assertIn("docs/standards/", content)

    def test_gitignore_is_idempotent(self):
        self.run_init()
        self.run_init()

        content = (self.project_dir / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".harness/runtime/", content)
        self.assertIn("__pycache__/", content)
        self.assertEqual(content.count("# harness defaults"), 1)


class TestInitHarnessSkills(InitHarnessTestCase):
    def test_creates_new_and_compat_skills_for_claude_and_codex(self):
        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stderr)

        claude_skills = self.project_dir / ".claude" / "skills"
        codex_skills = self.home_dir / ".codex" / "skills"
        for base in (claude_skills, codex_skills):
            for skill_name in (
                "requirement-confirmation",
                "requirement-development",
                "harness-implement",
                "grill-me",
                "harness-configure-verify",
            ):
                self.assertTrue((base / skill_name / "SKILL.md").is_file(), f"missing {base}/{skill_name}")

        confirmation = (claude_skills / "requirement-confirmation" / "SKILL.md").read_text(encoding="utf-8")
        development = (claude_skills / "requirement-development" / "SKILL.md").read_text(encoding="utf-8")
        harness_compat = (claude_skills / "harness-implement" / "SKILL.md").read_text(encoding="utf-8")
        grill_compat = (claude_skills / "grill-me" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("name: requirement-confirmation", confirmation)
        self.assertIn("每次只提出一个问题", confirmation)
        self.assertIn("confirmedBy", confirmation)
        self.assertIn("name: requirement-development", development)
        self.assertIn("requirement-confirmation", development)
        self.assertIn("task.py advance", development)
        self.assertIn("name: harness-implement", harness_compat)
        self.assertIn("requirement-development", harness_compat)
        self.assertIn("name: grill-me", grill_compat)
        self.assertIn("requirement-confirmation", grill_compat)

    def test_managed_skills_refresh_without_overwriting_custom_skills(self):
        managed_dir = self.project_dir / ".claude" / "skills" / "harness-implement"
        managed_dir.mkdir(parents=True)
        (managed_dir / "SKILL.md").write_text(
            "---\nname: harness-implement\ndescription: old\n---\n\nWalks the AI through the full v1.6 harness TDD flow.\n",
            encoding="utf-8",
        )
        custom_dir = self.project_dir / ".claude" / "skills" / "requirement-development"
        custom_dir.mkdir(parents=True)
        (custom_dir / "SKILL.md").write_text(
            "---\nname: requirement-development\ndescription: custom\n---\n\n# Custom\n",
            encoding="utf-8",
        )

        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stderr)

        managed = (managed_dir / "SKILL.md").read_text(encoding="utf-8")
        custom = (custom_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("requirement-development", managed)
        self.assertIn("custom", custom)

    def test_removes_managed_deepseek_skills_and_preserves_custom(self):
        managed = self.home_dir / ".deepseek" / "skills" / "requirement-development"
        managed.mkdir(parents=True)
        (managed / "SKILL.md").write_text(
            "---\nname: requirement-development\ndescription: old\n---\n\n需求开发\n\ntask.py advance\n",
            encoding="utf-8",
        )
        custom = self.home_dir / ".deepseek" / "skills" / "grill-me"
        custom.mkdir(parents=True)
        (custom / "SKILL.md").write_text(
            "---\nname: grill-me\ndescription: custom\n---\n\n# Custom\n",
            encoding="utf-8",
        )

        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertFalse(managed.exists())
        self.assertTrue((custom / "SKILL.md").is_file())


class TestInitHarnessHooksAndInstructions(InitHarnessTestCase):
    def test_creates_hooks_settings_and_instruction_files(self):
        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stderr)

        for base in (self.project_dir / ".claude" / "hooks", self.project_dir / ".codex" / "hooks"):
            self.assertTrue((base / "harness-session-start.py").is_file())
            self.assertTrue((base / "harness-workflow-state.py").is_file())
            self.assertTrue((base / "harness-inject-context.py").is_file())

        settings = json.loads((self.project_dir / ".claude" / "settings.json").read_text(encoding="utf-8"))
        codex_hooks = json.loads((self.project_dir / ".codex" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("PreToolUse", settings["hooks"])
        self.assertIn("PreToolUse", codex_hooks["hooks"])
        claude_pre_tool = json.dumps(settings["hooks"]["PreToolUse"], ensure_ascii=False)
        for matcher in ("Task", "Agent", "Write", "Edit", "MultiEdit", "Bash"):
            self.assertIn(matcher, claude_pre_tool)

        for name in ("CLAUDE.md", "AGENTS.md"):
            content = (self.project_dir / name).read_text(encoding="utf-8")
            self.assertIn("# Agent Harness", content)
            self.assertIn("docs/tasks/", content)
            self.assertIn("requirement-confirmation", content)
            self.assertIn("clarify -> doc-plan -> red -> green -> review -> validate -> done -> archived", content)

    def test_instruction_append_is_idempotent(self):
        (self.project_dir / "AGENTS.md").write_text("# Existing\n\n规则。\n", encoding="utf-8")

        self.run_init()
        self.run_init()

        content = (self.project_dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("规则", content)
        self.assertEqual(content.count("# Agent Harness"), 1)

    def test_existing_hooks_are_preserved_and_harness_hooks_are_idempotent(self):
        claude_dir = self.project_dir / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo existing"}]}]}}),
            encoding="utf-8",
        )
        codex_dir = self.project_dir / ".codex"
        codex_dir.mkdir(parents=True)
        (codex_dir / "hooks.json").write_text(
            json.dumps({"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [{"type": "command", "command": "echo existing"}]}]}}),
            encoding="utf-8",
        )

        self.run_init()
        self.run_init()

        settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
        codex = json.loads((codex_dir / "hooks.json").read_text(encoding="utf-8"))
        claude_serialized = json.dumps(settings, ensure_ascii=False)
        codex_serialized = json.dumps(codex, ensure_ascii=False)
        self.assertIn("echo existing", claude_serialized)
        self.assertIn("echo existing", codex_serialized)
        self.assertEqual(claude_serialized.count("harness-session-start.py"), 1)
        self.assertEqual(codex_serialized.count("harness-session-start.py"), 1)


class TestInitHarnessContextScripts(InitHarnessTestCase):
    def test_context_script_outputs_docs_task_context(self):
        result = self.run_init()
        self.assertEqual(result.returncode, 0, result.stderr)

        task_dir = self.project_dir / "docs" / "tasks" / "05-28-context"
        task_dir.mkdir(parents=True)
        (task_dir / "clarification.md").write_text("# 需求确认\n\n开发意图。\n", encoding="utf-8")
        (task_dir / "implementation-plan.md").write_text("# 实现计划\n\n## 开发意图摘要\n内容。\n", encoding="utf-8")
        (task_dir / "context.developer.jsonl").write_text(
            '{"file":"docs/standards/index.md","reason":"团队工程规范"}\n',
            encoding="utf-8",
        )

        output = subprocess.run(
            [
                sys.executable,
                str(self.project_dir / ".harness" / "scripts" / "context.py"),
                "developer",
                "--task",
                "docs/tasks/05-28-context",
                "--prompt",
                "继续开发",
            ],
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
        )

        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn("## Injected Context", output.stdout)
        self.assertIn("docs/standards/index.md", output.stdout)
        self.assertIn("clarification.md", output.stdout)
        self.assertIn("implementation-plan.md", output.stdout)
        self.assertIn("继续开发", output.stdout)

    def test_embedded_inject_hook_template_reads_docs_task_context(self):
        standalone_dir = self.project_dir / "standalone"
        standalone_dir.mkdir()
        standalone_init = standalone_dir / "init-harness.py"
        shutil.copy2(INIT_SCRIPT, standalone_init)

        result = subprocess.run(
            [sys.executable, str(standalone_init), "--target", str(self.project_dir), "--no-rtk", "--no-caveman"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.home_dir)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        task_dir = self.project_dir / "docs" / "tasks" / "05-28-embedded"
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(json.dumps({"status": "in_progress", "phase": "green"}), encoding="utf-8")
        (task_dir / "clarification.md").write_text("# 需求确认\n\n嵌入式上下文。\n", encoding="utf-8")
        (task_dir / "implementation-plan.md").write_text("# 实现计划\n\n嵌入式计划。\n", encoding="utf-8")
        (task_dir / "context.developer.jsonl").write_text(
            '{"file":"docs/standards/index.md","reason":"团队工程规范"}\n',
            encoding="utf-8",
        )
        sessions = self.project_dir / ".harness" / "runtime" / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        (sessions / "sess-embedded.json").write_text(
            json.dumps({"current_task": "docs/tasks/05-28-embedded"}),
            encoding="utf-8",
        )

        output = subprocess.run(
            [sys.executable, str(self.project_dir / ".claude" / "hooks" / "harness-inject-context.py")],
            input=json.dumps(
                {
                    "cwd": str(self.project_dir),
                    "session_id": "sess-embedded",
                    "tool_name": "Agent",
                    "tool_input": {"task_name": "harness_developer", "prompt": "Build it"},
                }
            ),
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
        )

        self.assertEqual(output.returncode, 0, output.stderr)
        payload = json.loads(output.stdout)
        prompt = payload["hookSpecificOutput"]["updatedInput"]["prompt"]
        self.assertIn("嵌入式上下文", prompt)
        self.assertIn("嵌入式计划", prompt)
        self.assertIn("docs/standards/index.md", prompt)


class TestDependencyFlags(InitHarnessTestCase):
    def test_no_rtk_and_no_caveman_flags_report_skipped(self):
        result = self.run_init("--no-rtk", "--no-caveman")
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr
        self.assertIn("rtk", combined.lower())
        self.assertIn("caveman", combined.lower())
        self.assertIn("skipped", combined.lower())

    def test_check_deps_reports_without_writing_project_files(self):
        result = self.run_init("--check-deps", "--no-rtk", "--no-caveman")
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr
        self.assertIn("Check-deps", combined)
        self.assertFalse((self.project_dir / ".harness").exists())

    def test_help_mentions_dependency_flags(self):
        result = subprocess.run([sys.executable, str(INIT_SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--no-rtk", result.stdout)
        self.assertIn("--no-caveman", result.stdout)
        self.assertIn("--check-deps", result.stdout)


if __name__ == "__main__":
    unittest.main()
