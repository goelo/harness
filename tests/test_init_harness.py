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

    def tearDown(self):
        shutil.rmtree(self.project_dir)

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
        result = subprocess.run(args, capture_output=True, text=True)
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
        existing = "# my custom rules\nsecrets.env\n"
        (self.project_dir / ".gitignore").write_text(existing)

        self._run_init()

        content = (self.project_dir / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("secrets.env", content, "user content lost")
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


class TestRtkAutoInstall(unittest.TestCase):
    """v1.6: init auto-installs RTK by default; --no-rtk skips it."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def _run_init(self, *args):
        import subprocess
        import sys

        init_script = Path(__file__).parent.parent / "init-harness.py"
        return subprocess.run(
            [sys.executable, str(init_script), "--target", str(self.project_dir), *args],
            capture_output=True,
            text=True,
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

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def _run_init(self, *args):
        import subprocess
        import sys

        init_script = Path(__file__).parent.parent / "init-harness.py"
        # Always skip RTK in this test class (we're testing caveman in isolation)
        full_args = [sys.executable, str(init_script), "--target", str(self.project_dir)]
        if "--check-deps" not in args:
            full_args.append("--no-rtk")
        full_args.extend(args)
        return subprocess.run(full_args, capture_output=True, text=True)

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
        # Should NOT have actually run the install URL
        self.assertNotIn("git.xiaojukeji.com/morganli/caveman/raw/main/install-internal.sh | bash caveman",
                         combined.lower())


class TestInitHarnessMergesBehavior(unittest.TestCase):
    """Init must merge into existing .claude/settings.json, not overwrite."""

    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def _run_init(self):
        import subprocess
        import sys

        init_script = Path(__file__).parent.parent / "init-harness.py"
        result = subprocess.run(
            [sys.executable, str(init_script), "--target", str(self.project_dir)],
            capture_output=True,
            text=True,
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
