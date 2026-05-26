"""TDD tests for init-harness.py — Slice 1.

Tests verify behavior through the public interface:
  run init → check filesystem state.

No implementation details tested — only observable outcomes.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


class TestInitHarnessCreatesStructure(unittest.TestCase):
    """Running init-harness.py in an empty project creates the expected structure."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        self.home_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.project_dir)
        shutil.rmtree(self.home_dir)

    def _run_init(self, *extra_args):
        """Run init-harness.py targeting self.project_dir.

        Defaults to --no-rtk and --no-caveman so unit tests don't trigger
        system installs. Pass --check-deps explicitly when testing dry-run.
        """
        import subprocess
        import sys

        init_script = Path(__file__).parent.parent / "init-harness.py"
        args = [sys.executable, str(init_script), "--target", str(self.project_dir)]
        if "--check-deps" not in extra_args:
            if "--no-rtk" not in extra_args:
                args.append("--no-rtk")
            if "--no-caveman" not in extra_args:
                args.append("--no-caveman")
        args.extend(extra_args)
        env = os.environ.copy()
        env["HOME"] = str(self.home_dir)
        result = subprocess.run(args, capture_output=True, text=True, env=env)
        return result

    def test_creates_harness_directory_skeleton(self):
        """After init, .harness/ has workflow.md, spec/, scripts/, tasks/, runtime/."""
        result = self._run_init()
        self.assertEqual(result.returncode, 0, result.stderr)

        harness = self.project_dir / ".harness"
        self.assertTrue(harness.is_dir())
        self.assertTrue((harness / "workflow.md").is_file())
        self.assertTrue((harness / "spec").is_dir())
        self.assertTrue((harness / "spec" / "index.md").is_file())
        self.assertTrue((harness / "scripts").is_dir())
        self.assertTrue((harness / "scripts" / "task.py").is_file())
        self.assertTrue((harness / "tasks").is_dir())
        self.assertTrue((harness / "runtime" / "sessions").is_dir())

    def test_creates_claude_hooks(self):
        """After init, .claude/hooks/ has 3 harness-prefixed hook scripts."""
        self._run_init()

        hooks_dir = self.project_dir / ".claude" / "hooks"
        self.assertTrue((hooks_dir / "harness-session-start.py").is_file())
        self.assertTrue((hooks_dir / "harness-workflow-state.py").is_file())
        self.assertTrue((hooks_dir / "harness-inject-context.py").is_file())

    def test_creates_codex_hooks(self):
        """After init, .codex/hooks/ has 3 harness-prefixed hook scripts."""
        self._run_init()

        hooks_dir = self.project_dir / ".codex" / "hooks"
        self.assertTrue((hooks_dir / "harness-session-start.py").is_file())
        self.assertTrue((hooks_dir / "harness-workflow-state.py").is_file())
        self.assertTrue((hooks_dir / "harness-inject-context.py").is_file())

    def test_creates_codex_hooks_json(self):
        """After init, .codex/hooks.json registers Codex hook events."""
        self._run_init()

        hooks_path = self.project_dir / ".codex" / "hooks.json"
        self.assertTrue(hooks_path.is_file(), ".codex/hooks.json was not created")
        hooks_json = json.loads(hooks_path.read_text(encoding="utf-8"))
        hooks = hooks_json.get("hooks", {})

        self.assertIn("SessionStart", hooks)
        self.assertIn("UserPromptSubmit", hooks)
        self.assertIn("PreToolUse", hooks)
        serialized = json.dumps(hooks_json, ensure_ascii=False)
        self.assertIn(".codex/hooks/harness-session-start.py", serialized)
        self.assertIn(".codex/hooks/harness-workflow-state.py", serialized)
        self.assertIn(".codex/hooks/harness-inject-context.py", serialized)
        self.assertIn("spawn_agent", serialized)
        self.assertIn("followup_task", serialized)

    def test_creates_claude_agents(self):
        """v1.6: After init, .claude/agents/ has 3 role agent files."""
        self._run_init()

        agents_dir = self.project_dir / ".claude" / "agents"
        for role in ("architect", "developer", "tester"):
            self.assertTrue(
                (agents_dir / f"{role}.md").is_file(),
                f"agents/{role}.md was not created",
            )
        # Old role files should NOT be created
        for old_role in ("research", "reviewer", "qa"):
            self.assertFalse(
                (agents_dir / f"{old_role}.md").is_file(),
                f"v1.6 should not create agents/{old_role}.md",
            )

    def test_creates_claude_commands(self):
        """After init, .claude/commands/harness/ has continue and finish."""
        self._run_init()

        commands_dir = self.project_dir / ".claude" / "commands" / "harness"
        self.assertTrue((commands_dir / "continue.md").is_file())
        self.assertTrue((commands_dir / "finish.md").is_file())

    def test_creates_settings_with_hooks(self):
        """After init, .claude/settings.json registers 3 hook events."""
        self._run_init()

        settings_path = self.project_dir / ".claude" / "settings.json"
        self.assertTrue(settings_path.is_file())
        settings = json.loads(settings_path.read_text())

        hooks = settings.get("hooks", {})
        self.assertIn("SessionStart", hooks)
        self.assertIn("UserPromptSubmit", hooks)
        self.assertIn("PreToolUse", hooks)

    def test_creates_claude_md_when_absent(self):
        """v1.6: When project has no CLAUDE.md, init creates a 3-role template."""
        self._run_init()

        claude_md = self.project_dir / "CLAUDE.md"
        self.assertTrue(claude_md.is_file(), "CLAUDE.md was not created")
        content = claude_md.read_text(encoding="utf-8")

        # Should mention key harness concepts and all 3 roles
        self.assertIn("harness", content.lower())
        self.assertIn(".harness/", content)
        for role in ("architect", "developer", "tester"):
            self.assertIn(role, content, f"role '{role}' missing from CLAUDE.md")

    def test_creates_agents_md_when_absent(self):
        """When project has no AGENTS.md, init creates the same harness template."""
        self._run_init()

        agents_md = self.project_dir / "AGENTS.md"
        self.assertTrue(agents_md.is_file(), "AGENTS.md was not created")
        content = agents_md.read_text(encoding="utf-8")

        self.assertIn("harness", content.lower())
        self.assertIn(".harness/", content)
        for role in ("architect", "developer", "tester"):
            self.assertIn(role, content, f"role '{role}' missing from AGENTS.md")

    def test_does_not_overwrite_existing_agents_md(self):
        """If AGENTS.md already exists, init appends a harness section but preserves user content."""
        existing_content = "# Project Agents\n\nCustom agent rules here.\n"
        (self.project_dir / "AGENTS.md").write_text(existing_content)

        self._run_init()

        content = (self.project_dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Custom agent rules here.", content)
        self.assertIn("Agent Harness", content)

    def test_idempotent_agents_md_append(self):
        """Running init twice doesn't append the AGENTS.md harness section twice."""
        self._run_init()
        self._run_init()

        content = (self.project_dir / "AGENTS.md").read_text(encoding="utf-8")
        count = content.count("# Agent Harness")
        self.assertEqual(count, 1, f"Found {count} Harness sections, expected 1")

    def test_does_not_overwrite_existing_claude_md(self):
        """If CLAUDE.md already exists, init appends a harness section but preserves user content."""
        existing_content = "# My Project\n\nCustom project rules here.\n"
        (self.project_dir / "CLAUDE.md").write_text(existing_content)

        self._run_init()

        content = (self.project_dir / "CLAUDE.md").read_text(encoding="utf-8")
        # User content preserved
        self.assertIn("Custom project rules here.", content)
        # Harness section appended
        self.assertIn("Agent Harness", content)

    def test_idempotent_claude_md_append(self):
        """Running init twice doesn't append the harness section twice."""
        self._run_init()
        self._run_init()

        content = (self.project_dir / "CLAUDE.md").read_text(encoding="utf-8")
        # Should only contain one Harness section
        count = content.count("# Agent Harness")
        self.assertEqual(count, 1, f"Found {count} Harness sections, expected 1")

    def test_creates_harness_implement_skill(self):
        """v1.5: After init, .claude/skills/harness-implement/SKILL.md exists."""
        self._run_init()

        skill_path = (
            self.project_dir
            / ".claude"
            / "skills"
            / "harness-implement"
            / "SKILL.md"
        )
        self.assertTrue(skill_path.is_file(), "harness-implement SKILL.md not created")

    def test_creates_grill_me_skill(self):
        """After init, .claude/skills/grill-me/SKILL.md exists."""
        self._run_init()

        skill_path = (
            self.project_dir
            / ".claude"
            / "skills"
            / "grill-me"
            / "SKILL.md"
        )
        self.assertTrue(skill_path.is_file(), "grill-me SKILL.md not created")

    def test_creates_deepseek_harness_implement_skill(self):
        """After init, ~/.deepseek/skills/harness-implement/SKILL.md exists."""
        self._run_init()

        skill_path = (
            self.home_dir
            / ".deepseek"
            / "skills"
            / "harness-implement"
            / "SKILL.md"
        )
        self.assertTrue(skill_path.is_file(), "DeepSeek harness-implement SKILL.md not created")
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("name: harness-implement", content)

    def test_creates_deepseek_grill_me_skill(self):
        """After init, ~/.deepseek/skills/grill-me/SKILL.md exists."""
        self._run_init()

        skill_path = (
            self.home_dir
            / ".deepseek"
            / "skills"
            / "grill-me"
            / "SKILL.md"
        )
        self.assertTrue(skill_path.is_file(), "DeepSeek grill-me SKILL.md not created")
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("name: grill-me", content)

    def test_creates_codex_harness_implement_skill(self):
        """After init, ~/.codex/skills/harness-implement/SKILL.md exists."""
        self._run_init()

        skill_path = (
            self.home_dir
            / ".codex"
            / "skills"
            / "harness-implement"
            / "SKILL.md"
        )
        self.assertTrue(skill_path.is_file(), "Codex harness-implement SKILL.md not created")
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("name: harness-implement", content)
        self.assertIn("spawn_agent", content)
        self.assertIn(".codex/hooks.json", content)

    def test_deepseek_harness_skill_uses_context_script_and_agents(self):
        """DeepSeek harness skill uses explicit context.py plus agent_open."""
        self._run_init()

        skill_path = (
            self.home_dir
            / ".deepseek"
            / "skills"
            / "harness-implement"
            / "SKILL.md"
        )
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("DeepSeek TUI does not receive Claude Code hook events", content)
        self.assertIn(".harness/scripts/context.py", content)
        self.assertIn("agent_open", content)
        self.assertNotIn("TeamCreate", content)

    def test_does_not_overwrite_existing_deepseek_skill(self):
        """If a DeepSeek SKILL.md already exists with different content, init skips it."""
        skill_dir = self.home_dir / ".deepseek" / "skills" / "grill-me"
        skill_dir.mkdir(parents=True)
        custom = "---\nname: grill-me\ndescription: my custom deepseek version\n---\n# Custom\n"
        (skill_dir / "SKILL.md").write_text(custom, encoding="utf-8")

        self._run_init()

        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("my custom deepseek version", content)

    def test_grill_me_skill_has_valid_frontmatter(self):
        """grill-me SKILL.md starts with YAML frontmatter."""
        self._run_init()

        skill_path = (
            self.project_dir
            / ".claude"
            / "skills"
            / "grill-me"
            / "SKILL.md"
        )
        content = skill_path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\n"), "grill-me skill missing frontmatter")
        self.assertIn("name: grill-me", content)
        self.assertIn("description:", content)
        self.assertIn("Ask the questions one at a time.", content)

    def test_skill_has_valid_frontmatter(self):
        """SKILL.md starts with YAML frontmatter containing name and description."""
        self._run_init()

        skill_path = (
            self.project_dir
            / ".claude"
            / "skills"
            / "harness-implement"
            / "SKILL.md"
        )
        content = skill_path.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---\n"), "skill missing frontmatter")
        # Required fields
        self.assertIn("name: harness-implement", content)
        self.assertIn("description:", content)

    def test_skill_description_contains_trigger_phrases(self):
        """description (between first --- markers) contains both EN + CN trigger phrases."""
        self._run_init()

        skill_path = (
            self.project_dir
            / ".claude"
            / "skills"
            / "harness-implement"
            / "SKILL.md"
        )
        content = skill_path.read_text(encoding="utf-8")

        # Extract frontmatter
        parts = content.split("---", 2)
        self.assertGreaterEqual(len(parts), 3, "skill has no frontmatter block")
        frontmatter = parts[1]

        # Triggers — at least one of each language
        self.assertIn("design.md", frontmatter)
        self.assertTrue(
            "按照" in frontmatter or "按 design" in frontmatter,
            "Chinese trigger phrase missing from description",
        )
        self.assertTrue(
            "implement" in frontmatter.lower(),
            "English trigger 'implement' missing from description",
        )

    def test_skill_body_describes_flow(self):
        """v1.6: Body mentions all 3 roles + key concepts."""
        self._run_init()

        skill_path = (
            self.project_dir
            / ".claude"
            / "skills"
            / "harness-implement"
            / "SKILL.md"
        )
        content = skill_path.read_text(encoding="utf-8")

        for keyword in (
            "architect",
            "developer",
            "tester",
            "TeamCreate",
            "task.py start",
            "context.architect.jsonl",
            "info.md",
            "bypassPermissions",
        ):
            self.assertIn(keyword, content, f"skill body missing key concept: {keyword}")

    def test_does_not_overwrite_existing_skill(self):
        """If SKILL.md already exists with different content, init skips it."""
        skill_dir = self.project_dir / ".claude" / "skills" / "harness-implement"
        skill_dir.mkdir(parents=True)
        custom = "---\nname: harness-implement\ndescription: my custom version\n---\n# Custom\n"
        (skill_dir / "SKILL.md").write_text(custom)

        self._run_init()

        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("my custom version", content)

    def test_creates_gitignore_when_absent(self):
        """v1.5.4: init creates .gitignore with harness/python/node defaults."""
        self._run_init()

        gitignore = self.project_dir / ".gitignore"
        self.assertTrue(gitignore.is_file())
        content = gitignore.read_text(encoding="utf-8")
        for entry in ("__pycache__/", "node_modules/", ".harness/runtime/", ".DS_Store"):
            self.assertIn(entry, content, f".gitignore missing {entry}")

    def test_gitignore_appends_to_existing(self):
        """If user has a .gitignore already, init appends harness defaults below."""
        existing = "# my custom rules\nprivate.env\n"
        (self.project_dir / ".gitignore").write_text(existing)

        self._run_init()

        content = (self.project_dir / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("private.env", content, "user content lost")
        self.assertIn("__pycache__/", content, "harness defaults not appended")

    def test_gitignore_idempotent(self):
        """Running init twice doesn't double-append harness defaults."""
        self._run_init()
        self._run_init()

        content = (self.project_dir / ".gitignore").read_text(encoding="utf-8")
        count = content.count("# harness defaults")
        self.assertEqual(count, 1, f"appended {count} times, expected 1")

    def test_creates_team_cleanup_script(self):
        """v1.5.4: init deploys team_cleanup.py to .harness/scripts/."""
        self._run_init()

        script = self.project_dir / ".harness" / "scripts" / "team_cleanup.py"
        self.assertTrue(script.is_file(), "team_cleanup.py not created")
        content = script.read_text(encoding="utf-8")
        # Should be the real one, not stub
        self.assertIn("find_team_processes", content, "stub deployed instead of real script")

    def test_creates_context_script(self):
        """init deploys context.py for runtimes without Claude hooks."""
        self._run_init()

        script = self.project_dir / ".harness" / "scripts" / "context.py"
        self.assertTrue(script.is_file(), "context.py not created")
        content = script.read_text(encoding="utf-8")
        self.assertIn("Build role-specific harness context", content)

    def test_context_script_outputs_role_context(self):
        """context.py emits task docs, manifest files, info.md, and prompt."""
        import subprocess
        import sys

        self._run_init()

        harness = self.project_dir / ".harness"
        task_dir = harness / "tasks" / "05-25-context-demo"
        task_dir.mkdir(parents=True)
        (task_dir / "proposal.md").write_text("# Proposal\n\nContext proposal\n", encoding="utf-8")
        (task_dir / "design.md").write_text("# Design\n\nContext design\n", encoding="utf-8")
        (task_dir / "tasks.md").write_text("# Tasks\n\nContext tasks\n", encoding="utf-8")
        (task_dir / "info.md").write_text("# Info\n\nContext info\n", encoding="utf-8")
        (task_dir / "context.developer.jsonl").write_text(
            '{"file": ".harness/spec/index.md", "reason": "team spec"}\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(harness / "scripts" / "context.py"),
                "developer",
                "--task",
                "05-25-context-demo",
                "--prompt",
                "Build it",
            ],
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Injected Context", result.stdout)
        self.assertIn("Team Coding Spec", result.stdout)
        self.assertIn("Context proposal", result.stdout)
        self.assertIn("Context design", result.stdout)
        self.assertIn("Context tasks", result.stdout)
        self.assertIn("Context info", result.stdout)
        self.assertIn("## Task", result.stdout)
        self.assertIn("Build it", result.stdout)

    def test_embedded_inject_hook_template_reads_task_package_docs(self):
        """Standalone init fallback installs a working inject-context hook."""
        import subprocess
        import sys

        standalone_dir = self.project_dir / "standalone"
        standalone_dir.mkdir()
        standalone_init = standalone_dir / "init-harness.py"
        shutil.copy2(Path(__file__).parent.parent / "init-harness.py", standalone_init)

        result = subprocess.run(
            [
                sys.executable,
                str(standalone_init),
                "--target",
                str(self.project_dir),
                "--no-rtk",
                "--no-caveman",
            ],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.home_dir)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        harness = self.project_dir / ".harness"
        task_dir = harness / "tasks" / "05-22-embedded"
        task_dir.mkdir(parents=True)
        (task_dir / "proposal.md").write_text(
            "# Proposal\n\nEmbedded task proposal\n", encoding="utf-8"
        )
        (task_dir / "design.md").write_text(
            "# Design\n\nEmbedded task design\n", encoding="utf-8"
        )
        (task_dir / "tasks.md").write_text(
            "# Tasks\n\nEmbedded task list\n", encoding="utf-8"
        )
        (task_dir / "context.developer.jsonl").write_text(
            '{"file": ".harness/spec/index.md", "reason": "team spec"}\n',
            encoding="utf-8",
        )
        (harness / "runtime" / "sessions" / "sess-embedded.json").write_text(
            json.dumps({"current_task": ".harness/tasks/05-22-embedded"}),
            encoding="utf-8",
        )

        hook_path = self.project_dir / ".claude" / "hooks" / "harness-inject-context.py"
        output = subprocess.run(
            [sys.executable, str(hook_path)],
            input=json.dumps(
                {
                    "cwd": str(self.project_dir),
                    "session_id": "sess-embedded",
                    "tool_name": "Agent",
                    "tool_input": {
                        "subagent_type": "developer",
                        "prompt": "Build it",
                    },
                }
            ),
            capture_output=True,
            text=True,
            cwd=str(self.project_dir),
        )
        self.assertEqual(output.returncode, 0, output.stderr)

        payload = json.loads(output.stdout)
        prompt = payload["hookSpecificOutput"]["updatedInput"]["prompt"]
        self.assertIn("Embedded task proposal", prompt)
        self.assertIn("Embedded task design", prompt)
        self.assertIn("Embedded task list", prompt)


class TestRtkAutoInstall(unittest.TestCase):
    """v1.6: init auto-installs RTK by default; --no-rtk skips it."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        self.home_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.project_dir)
        shutil.rmtree(self.home_dir)

    def _run_init(self, *args):
        import subprocess
        import sys

        init_script = Path(__file__).parent.parent / "init-harness.py"
        return subprocess.run(
            [sys.executable, str(init_script), "--target", str(self.project_dir), *args],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.home_dir)},
        )

    def test_no_rtk_flag_reports_skipped(self):
        """--no-rtk: skip install, report 'skipped' in output."""
        result = self._run_init("--no-rtk")
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr
        self.assertIn("rtk", combined.lower())
        self.assertIn("skip", combined.lower())

    def test_check_deps_does_not_install(self):
        """--check-deps: report status without running curl."""
        result = self._run_init("--check-deps")
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr
        # Should mention rtk + dry-run / check-deps mode
        self.assertIn("rtk", combined.lower())
        # And NOT actually attempt curl
        self.assertNotIn("curl -fsSL https://raw.githubusercontent", combined)

    def test_check_deps_reports_when_rtk_present(self):
        """If rtk is on PATH, --check-deps reports 'installed'."""
        # We can't reliably guarantee rtk is or isn't on PATH; just verify the
        # output mentions install status (one of: installed/missing/skipped).
        result = self._run_init("--check-deps")
        self.assertEqual(result.returncode, 0)
        combined = (result.stdout + result.stderr).lower()
        # Output should contain at least one of these status words for rtk
        self.assertTrue(
            any(s in combined for s in ("installed", "not installed", "missing", "skipped", "would install")),
            f"no rtk status found in output: {combined[:500]}",
        )

    def test_help_mentions_no_rtk_and_check_deps(self):
        """--help should document the new flags."""
        import subprocess
        import sys
        init_script = Path(__file__).parent.parent / "init-harness.py"
        result = subprocess.run(
            [sys.executable, str(init_script), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--no-rtk", result.stdout)
        self.assertIn("--no-caveman", result.stdout)
        self.assertIn("--check-deps", result.stdout)


class TestCavemanAutoInstall(unittest.TestCase):
    """v1.6: init auto-installs Caveman by default; --no-caveman skips it."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        self.home_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.project_dir)
        shutil.rmtree(self.home_dir)

    def _run_init(self, *args):
        import subprocess
        import sys

        init_script = Path(__file__).parent.parent / "init-harness.py"
        # Always skip RTK in this test class (we're testing caveman in isolation)
        full_args = [sys.executable, str(init_script), "--target", str(self.project_dir)]
        if "--check-deps" not in args:
            full_args.append("--no-rtk")
        full_args.extend(args)
        return subprocess.run(
            full_args,
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.home_dir)},
        )

    def test_no_caveman_flag_reports_skipped(self):
        result = self._run_init("--no-caveman")
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr
        self.assertIn("caveman", combined.lower())
        self.assertIn("skip", combined.lower())

    def test_check_deps_reports_caveman_status(self):
        """--check-deps reports caveman status without running install."""
        result = self._run_init("--check-deps", "--no-rtk")
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = (result.stdout + result.stderr).lower()
        self.assertIn("caveman", combined)
        # Should NOT try to run a Caveman installer in the public build.
        self.assertIn("unavailable", combined.lower())


class TestInitHarnessMergesBehavior(unittest.TestCase):
    """Init must merge into existing .claude/settings.json, not overwrite."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        self.home_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.project_dir)
        shutil.rmtree(self.home_dir)

    def _run_init(self):
        import subprocess
        import sys

        init_script = Path(__file__).parent.parent / "init-harness.py"
        result = subprocess.run(
            [sys.executable, str(init_script), "--target", str(self.project_dir)],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.home_dir)},
        )
        return result

    def test_preserves_existing_settings(self):
        """Existing hooks in settings.json are preserved after init."""
        claude_dir = self.project_dir / ".claude"
        claude_dir.mkdir(parents=True)
        existing_settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo existing"}],
                    }
                ]
            },
            "permissions": {"allow": ["Bash(git *)"]},
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing_settings))

        self._run_init()

        settings = json.loads((claude_dir / "settings.json").read_text())
        # Original Bash matcher still present
        pre_tool = settings["hooks"]["PreToolUse"]
        bash_matchers = [h for h in pre_tool if h.get("matcher") == "Bash"]
        self.assertTrue(len(bash_matchers) > 0, "Existing Bash hook was lost")
        # Permissions preserved
        self.assertIn("permissions", settings)
        self.assertIn("Bash(git *)", settings["permissions"]["allow"])

    def test_idempotent_no_duplicate_hooks(self):
        """Running init twice does not duplicate hook entries."""
        self._run_init()
        self._run_init()

        settings = json.loads(
            (self.project_dir / ".claude" / "settings.json").read_text()
        )
        # SessionStart should have exactly one harness hook entry
        session_start = settings["hooks"]["SessionStart"]
        harness_hooks = [
            h
            for h in session_start
            if any(
                "harness-session-start" in hook.get("command", "")
                for hook in h.get("hooks", [])
            )
        ]
        self.assertEqual(len(harness_hooks), 1, "Duplicate SessionStart hook detected")

    def test_codex_hooks_preserve_existing_entries(self):
        """Existing hooks in .codex/hooks.json are preserved after init."""
        codex_dir = self.project_dir / ".codex"
        codex_dir.mkdir(parents=True)
        existing_hooks = {
            "hooks": {
                "SessionStart": [
                    {
                        "matcher": "startup",
                        "hooks": [{"type": "command", "command": "echo existing"}],
                    }
                ]
            }
        }
        (codex_dir / "hooks.json").write_text(
            json.dumps(existing_hooks, indent=2),
            encoding="utf-8",
        )

        self._run_init()

        hooks_json = json.loads((codex_dir / "hooks.json").read_text(encoding="utf-8"))
        session_start = hooks_json["hooks"]["SessionStart"]
        self.assertTrue(
            any(
                any(hook.get("command") == "echo existing" for hook in entry.get("hooks", []))
                for entry in session_start
            ),
            "Existing Codex hook was lost",
        )
        self.assertTrue(
            any(
                any("harness-session-start" in hook.get("command", "") for hook in entry.get("hooks", []))
                for entry in session_start
            ),
            "Harness Codex hook was not added",
        )

    def test_codex_hooks_idempotent(self):
        """Running init twice does not duplicate Codex hook entries."""
        self._run_init()
        self._run_init()

        hooks_json = json.loads(
            (self.project_dir / ".codex" / "hooks.json").read_text(encoding="utf-8")
        )
        serialized = json.dumps(hooks_json, ensure_ascii=False)
        self.assertEqual(serialized.count("harness-session-start.py"), 1)
        self.assertEqual(serialized.count("harness-workflow-state.py"), 1)
        self.assertEqual(serialized.count("harness-inject-context.py"), 2)

    def test_does_not_overwrite_existing_agents(self):
        """If .claude/agents/developer.md already exists, init skips it."""
        agents_dir = self.project_dir / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "developer.md").write_text("# My custom developer agent\n")

        self._run_init()

        content = (agents_dir / "developer.md").read_text()
        self.assertIn("My custom developer agent", content)


if __name__ == "__main__":
    unittest.main()
