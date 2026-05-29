#!/usr/bin/env python3
"""Initialize lightweight agent harness in a project.

Usage:
    python3 init-harness.py [--target <dir>]

Creates .harness/ (task state, workflow, spec) and merges hook/agent/command
entries into .claude/ without overwriting existing content.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

RTK_INSTALL_URL = (
    "https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh"
)
CAVEMAN_INSTALL_URL = (
    "https://git.xiaojukeji.com/morganli/caveman/raw/main/install-internal.sh"
)

HARNESS_HOOKS = {
    "SessionStart": [
        {
            "matcher": "startup",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 .claude/hooks/harness-session-start.py",
                    "timeout": 10,
                }
            ],
        }
    ],
    "UserPromptSubmit": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 .claude/hooks/harness-workflow-state.py",
                    "timeout": 5,
                }
            ],
        }
    ],
    "PreToolUse": [
        {
            "matcher": "Task",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 .claude/hooks/harness-inject-context.py",
                    "timeout": 30,
                }
            ],
        },
        {
            "matcher": "Agent",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 .claude/hooks/harness-inject-context.py",
                    "timeout": 30,
                }
            ],
        },
    ],
}

CODEX_HOOKS = {
    "SessionStart": [
        {
            "matcher": "startup|resume",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 .codex/hooks/harness-session-start.py",
                    "timeout": 10,
                    "statusMessage": "Loading harness context...",
                }
            ],
        }
    ],
    "UserPromptSubmit": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 .codex/hooks/harness-workflow-state.py",
                    "timeout": 5,
                }
            ],
        }
    ],
    "PreToolUse": [
        {
            "matcher": "spawn_agent",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 .codex/hooks/harness-inject-context.py",
                    "timeout": 30,
                }
            ],
        },
        {
            "matcher": "followup_task",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 .codex/hooks/harness-inject-context.py",
                    "timeout": 30,
                }
            ],
        },
    ],
}


def _is_harness_hook_entry(entry: dict) -> bool:
    """Check if a hook entry was created by this harness."""
    for hook in entry.get("hooks", []):
        cmd = hook.get("command", "")
        if "harness-" in cmd and ".claude/hooks/" in cmd:
            return True
    return False


def _is_harness_codex_hook_entry(entry: dict) -> bool:
    """Check if a Codex hook entry was created by this harness."""
    for hook in entry.get("hooks", []):
        cmd = hook.get("command", "")
        if "harness-" in cmd and ".codex/hooks/" in cmd:
            return True
    return False


def merge_hooks_json(path: Path, harness_hooks: dict, is_harness_entry) -> None:
    """Merge harness hooks into a hooks.json-style file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        config = json.loads(path.read_text(encoding="utf-8"))
    else:
        config = {}

    hooks = config.setdefault("hooks", {})
    for event_name, harness_entries in harness_hooks.items():
        existing = hooks.get(event_name, [])
        existing = [entry for entry in existing if not is_harness_entry(entry)]
        existing.extend(harness_entries)
        hooks[event_name] = existing

    path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def merge_settings(target: Path) -> None:
    """Merge harness hooks into existing .claude/settings.json."""
    merge_hooks_json(target / ".claude" / "settings.json", HARNESS_HOOKS, _is_harness_hook_entry)


def merge_codex_hooks(target: Path) -> None:
    """Merge harness hooks into .codex/hooks.json."""
    merge_hooks_json(target / ".codex" / "hooks.json", CODEX_HOOKS, _is_harness_codex_hook_entry)


def create_harness_skeleton(target: Path) -> None:
    """Create .harness/ directory structure."""
    harness = target / ".harness"

    (harness / "runtime" / "sessions").mkdir(parents=True, exist_ok=True)
    (harness / "scripts").mkdir(parents=True, exist_ok=True)
    create_docs_skeleton(target)

    _write_if_missing(harness / "workflow.md", WORKFLOW_MD)
    _write_if_missing(harness / "verify.json", VERIFY_JSON_TEMPLATE)

    # Deploy real scripts from sibling harness_scripts/ when available
    src_scripts = Path(__file__).parent / "harness_scripts"
    script_files = {
        "task.py": TASK_PY_STUB,
        "team_cleanup.py": TEAM_CLEANUP_STUB,
        "context.py": CONTEXT_PY_STUB,
        "verify.py": VERIFY_PY_STUB,
    }
    for filename, stub in script_files.items():
        real = src_scripts / filename
        content = real.read_text(encoding="utf-8") if real.is_file() else stub
        target_file = harness / "scripts" / filename
        if not target_file.is_file():
            target_file.write_text(content, encoding="utf-8")

    # Project-root .gitignore — append harness/python/node defaults if absent
    create_gitignore(target)


def create_docs_skeleton(target: Path) -> None:
    """Create docs/tasks and docs/standards without taking over project docs."""
    docs = target / "docs"
    tasks = docs / "tasks"
    standards = docs / "standards"
    docs.mkdir(parents=True, exist_ok=True)
    tasks.mkdir(parents=True, exist_ok=True)
    standards.mkdir(parents=True, exist_ok=True)
    _write_if_missing(docs / "index.md", DOCS_INDEX_MD)
    _write_if_missing(standards / "index.md", STANDARDS_INDEX_MD)
    _append_harness_docs_index(docs / "index.md")


def _append_harness_docs_index(path: Path) -> None:
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    if "## Harness" in content and "docs/tasks/" in content and "docs/standards/" in content:
        return
    section = """\

## Harness

| 目录 | 内容 |
| --- | --- |
| `docs/tasks/` | 需求开发任务包，每个子目录对应一次需求开发 |
| `docs/standards/` | 团队长期工程规范，供需求开发过程自动注入上下文 |
"""
    sep = "" if content.endswith("\n") or not content else "\n"
    path.write_text(content + sep + section.lstrip("\n"), encoding="utf-8")


def create_gitignore(target: Path) -> None:
    """Create or augment project-root .gitignore with harness defaults."""
    gitignore = target / ".gitignore"
    if not gitignore.is_file():
        gitignore.write_text(GITIGNORE_TEMPLATE, encoding="utf-8")
        return

    existing = gitignore.read_text(encoding="utf-8")
    if "# harness defaults" in existing:
        return  # already augmented
    sep = "" if existing.endswith("\n") else "\n"
    gitignore.write_text(existing + sep + "\n" + GITIGNORE_TEMPLATE, encoding="utf-8")


def create_claude_hooks(target: Path) -> None:
    """Write hook scripts to .claude/hooks/.

    Prefer real implementations from sibling harness_hooks/ when running
    from the dev repo. Fall back to embedded stubs if not found.
    """
    hooks_dir = target / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    src_dir = Path(__file__).parent / "harness_hooks"
    hook_files = {
        "harness-session-start.py": HOOK_SESSION_START,
        "harness-workflow-state.py": HOOK_WORKFLOW_STATE,
        "harness-inject-context.py": HOOK_INJECT_CONTEXT,
    }
    for filename, stub in hook_files.items():
        real = src_dir / filename
        content = real.read_text(encoding="utf-8") if real.is_file() else stub
        (hooks_dir / filename).write_text(content, encoding="utf-8")


def create_codex_hooks(target: Path) -> None:
    """Write hook scripts to .codex/hooks/."""
    hooks_dir = target / ".codex" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    src_dir = Path(__file__).parent / "harness_hooks"
    hook_files = {
        "harness-session-start.py": HOOK_SESSION_START,
        "harness-workflow-state.py": HOOK_WORKFLOW_STATE,
        "harness-inject-context.py": HOOK_INJECT_CONTEXT,
    }
    for filename, stub in hook_files.items():
        real = src_dir / filename
        content = real.read_text(encoding="utf-8") if real.is_file() else stub
        (hooks_dir / filename).write_text(content, encoding="utf-8")


def create_claude_agents(target: Path) -> None:
    """Write 3 role agent files (v1.6), skipping existing ones."""
    agents_dir = target / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    _write_if_missing(agents_dir / "architect.md", AGENT_ARCHITECT)
    _write_if_missing(agents_dir / "developer.md", AGENT_DEVELOPER)
    _write_if_missing(agents_dir / "tester.md", AGENT_TESTER)


def create_claude_commands(target: Path) -> None:
    """Write command files."""
    commands_dir = target / ".claude" / "commands" / "harness"
    commands_dir.mkdir(parents=True, exist_ok=True)

    _write_if_missing(commands_dir / "continue.md", CMD_CONTINUE)
    _write_if_missing(commands_dir / "finish.md", CMD_FINISH)


MANAGED_SKILL_MARKER = "<!-- harness-managed-skill -->"

LEGACY_MANAGED_SKILL_MARKERS = {
    "requirement-confirmation": (
        "需求确认",
        "development_intent",
    ),
    "requirement-development": (
        "需求开发",
        "task.py advance",
    ),
    "harness-implement": (
        "Walks the AI through the full v1.6 harness TDD flow",
        "DeepSeek TUI does not receive Claude Code hook events",
        "Codex supports project hooks through `.codex/hooks.json`",
        "requirement-development",
    ),
    "harness-configure-verify": (
        "Configure `.harness/verify.json` for the current project",
        "Present the recommended JSON patch and wait for confirmation",
    ),
    "grill-me": (
        "Interview me relentlessly about every aspect of this plan",
        "Ask the questions one at a time.",
        "requirement-confirmation",
    ),
}


def _looks_like_managed_skill(content: str, skill_name: str) -> bool:
    """Return true when an existing skill was generated by this installer."""
    if f"name: {skill_name}" not in content:
        return False
    if MANAGED_SKILL_MARKER in content:
        return True
    return any(marker in content for marker in LEGACY_MANAGED_SKILL_MARKERS.get(skill_name, ()))


def _write_managed_skill(path: Path, content: str, skill_name: str) -> None:
    """Write a harness skill, refreshing official managed versions only."""
    if not path.is_file():
        path.write_text(content, encoding="utf-8")
        return

    existing = path.read_text(encoding="utf-8")
    if _looks_like_managed_skill(existing, skill_name):
        path.write_text(content, encoding="utf-8")


def create_skill_files(skills_dir: Path, harness_implement: str | None = None) -> None:
    """Write harness skill files into a skills directory."""
    requirement_confirmation_dir = skills_dir / "requirement-confirmation"
    requirement_confirmation_dir.mkdir(parents=True, exist_ok=True)
    _write_managed_skill(
        requirement_confirmation_dir / "SKILL.md",
        SKILL_REQUIREMENT_CONFIRMATION,
        "requirement-confirmation",
    )

    requirement_development_dir = skills_dir / "requirement-development"
    requirement_development_dir.mkdir(parents=True, exist_ok=True)
    _write_managed_skill(
        requirement_development_dir / "SKILL.md",
        SKILL_REQUIREMENT_DEVELOPMENT,
        "requirement-development",
    )

    harness_implement = harness_implement or SKILL_HARNESS_IMPLEMENT_COMPAT
    harness_skill_dir = skills_dir / "harness-implement"
    harness_skill_dir.mkdir(parents=True, exist_ok=True)
    _write_managed_skill(harness_skill_dir / "SKILL.md", harness_implement, "harness-implement")

    configure_verify_skill_dir = skills_dir / "harness-configure-verify"
    configure_verify_skill_dir.mkdir(parents=True, exist_ok=True)
    _write_managed_skill(
        configure_verify_skill_dir / "SKILL.md",
        SKILL_HARNESS_CONFIGURE_VERIFY,
        "harness-configure-verify",
    )

    grill_me_skill_dir = skills_dir / "grill-me"
    grill_me_skill_dir.mkdir(parents=True, exist_ok=True)
    _write_managed_skill(grill_me_skill_dir / "SKILL.md", SKILL_GRILL_ME_COMPAT, "grill-me")


def create_claude_skills(target: Path) -> None:
    """Write skill files for Claude Code (v1.5+)."""
    create_skill_files(target / ".claude" / "skills")


DEEPSEEK_SKILL_NAMES = (
    "requirement-confirmation",
    "requirement-development",
    "harness-implement",
    "harness-configure-verify",
    "grill-me",
)


def remove_managed_deepseek_skills() -> None:
    """Remove legacy harness-managed DeepSeek skills while preserving custom files."""
    skills_dir = Path.home() / ".deepseek" / "skills"
    for skill_name in DEEPSEEK_SKILL_NAMES:
        skill_dir = skills_dir / skill_name
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        content = skill_file.read_text(encoding="utf-8")
        if _looks_like_managed_skill(content, skill_name):
            shutil.rmtree(skill_dir)


def create_codex_skills() -> None:
    """Write skill files for Codex."""
    create_skill_files(Path.home() / ".codex" / "skills", SKILL_HARNESS_IMPLEMENT_COMPAT)


HARNESS_SECTION_MARKER = "# Agent Harness"


def create_harness_instruction_md(target: Path, filename: str) -> None:
    """Create or append the harness section to an agent instruction file.

    - No file → create with full harness template
    - Existing file without harness section → append harness section
    - Existing file with harness section → idempotent (no change)
    """
    instruction_md = target / filename

    if not instruction_md.is_file():
        instruction_md.write_text(CLAUDE_MD_TEMPLATE, encoding="utf-8")
        return

    existing = instruction_md.read_text(encoding="utf-8")
    if HARNESS_SECTION_MARKER in existing:
        return  # already has the section, leave it alone

    # Append harness section after user content
    separator = "" if existing.endswith("\n") else "\n"
    instruction_md.write_text(
        existing + separator + "\n" + HARNESS_SECTION + "\n",
        encoding="utf-8",
    )


def create_claude_md(target: Path) -> None:
    create_harness_instruction_md(target, "CLAUDE.md")


def create_agents_md(target: Path) -> None:
    create_harness_instruction_md(target, "AGENTS.md")


def _write_if_missing(path: Path, content: str) -> None:
    """Write file only if it doesn't exist."""
    if not path.is_file():
        path.write_text(content, encoding="utf-8")


# =============================================================================
# Template content
# =============================================================================

WORKFLOW_MD = """\
# Workflow

## States

[workflow-state:no_task]
No active task. Describe what you want to accomplish — main session creates a task to track it.

For harness implementation requests, run **Mandatory grill-me** against the
project-root design/spec/requirements document before `task.py create`. Ask one
question at a time. If a question can be answered by exploring the codebase,
explore the codebase instead of asking. Create the task only after the design
source and grill-me answers are confirmed.
[/workflow-state:no_task]

[workflow-state:planning]
Task is in planning. Required steps in this exact order:

  1. Design source — project root (NO copy):
     a. Confirm a design document exists at project root: `design.md`,
        `spec.md`, or `requirements.md` (in that priority order). Hooks read
        it directly — do NOT copy it into the task dir.
     b. If missing or too vague, work with the user (or invoke grill-me) to
        produce one. Confirm before proceeding.

  2. **Mandatory grill-me**:
     a. Verify grill-me was completed before `task.py create`.
     b. If not, stop curation and run grill-me now before any agent dispatch.
     c. Ask one question at a time; explore the codebase when the answer is
        discoverable locally.

  3. Optional: gather external info via `research/*.md` (architect can do this).

  4. **Curate 3 manifests** (Phase 1.3 — required before any agent dispatch):
     - `context.architect.jsonl`  — at least .harness/spec/index.md
     - `context.developer.jsonl`  — spec + relevant research
     - `context.tester.jsonl`     — spec + testing conventions
     Each file MUST have at least one row with a `file` field
     (not just the `_example` seed row).

  5. Dispatch `architect` agent → writes `info.md` and `scope.json`
     (now has spec via manifest).

  6. (Optional) Refine manifests if architect's design uncovers needs not yet in manifests.

  7. Run: `python3 .harness/scripts/task.py start <task-dir>`.
     This command WILL FAIL if manifests are still seed-only.

WHY this order: architect itself reads context.architect.jsonl to see team
specs while designing. If you dispatch architect before curating, it designs
without team conventions. Manifest curation must precede ALL sub-agent dispatch.
[/workflow-state:planning]

[workflow-state:in_progress]
Task is active. **TDD is the default workflow** (red-green-refactor).
**Do not create 3 persistent teammates by default.** Main session must first
ask the user whether to enable 3-teammate Teams mode for this task.

## Confirm execution mode once per task (right after task.py start)

Return to the user with the slice plan and ask whether to enable 3-teammate
Teams mode. Use Teams mode only after explicit confirmation.

If confirmed, bootstrap once:

  TeamCreate(team_name: "<task-slug>", description: "<task title>")

This creates a shared TaskList visible to all teammates. Main session = team lead.

If not confirmed, keep execution in the main session and dispatch individual
roles only when a phase actually needs a specialist.

## Permission mode for all sub-agent calls

If main session was started with `--dangerously-skip-permissions` (autonomous mode),
ALL Agent / SendMessage calls MUST pass `mode: "bypassPermissions"` so sub-agents
don't stall on approval prompts.

## Confirmed Teams mode: spawn 3 execution teammates ONCE

After TeamCreate, spawn 3 persistent teammates once for the whole task:

  Agent(team_name, name: "architect", subagent_type: "architect", mode: "bypassPermissions", prompt: "Stand by ...")
  Agent(team_name, name: "developer", subagent_type: "developer", mode: "bypassPermissions", prompt: "Stand by ...")
  Agent(team_name, name: "tester",    subagent_type: "tester",    mode: "bypassPermissions", prompt: "Stand by ...")

The PreToolUse hook fires on each Agent call → injects PRD + info.md + role
manifest into each teammate. Context persists across all subsequent SendMessage.

## Per-slice TDD dispatch

In confirmed Teams mode, dispatch via SendMessage.

For each implementation slice, send messages in TDD order, waiting for idle
between each:

  1. SendMessage(to: "tester",    message: "RED phase. Slice N: <X>. Write failing tests.")
  2. SendMessage(to: "developer", message: "GREEN phase. Slice N. Make tester's tests pass.")
  3. SendMessage(to: "architect", message: "REVIEW phase. Slice N. Refactor + verify design conformance.")
  4. SendMessage(to: "tester",    message: "VALIDATE phase. Slice N. Add edge case tests.")

After all 4 idle: main session runs `python3 .harness/scripts/verify.py all`.
If verification fails, fix failures before any commit. If verification passes,
main session commits.

In main-session mode, perform the same TDD order without creating the 3
persistent teammates. Use a one-off sub-agent only when the current phase needs
that role's specialist context, then return results to the main session before
continuing.

If design deviation: architect updates info.md and SendMessage developer + tester
"info.md updated, please re-read".

## Cleanup at task end

Single TeamDelete kills team config. Then run team_cleanup.py to kill the
sub-agent processes (TeamDelete alone leaves them running):

  python3 .harness/scripts/team_cleanup.py <task-slug>

**Sub-agents must NOT commit.** Main session owns git.
[/workflow-state:in_progress]

[workflow-state:archived]
Task is archived. No active task.
[/workflow-state:archived]
"""

SPEC_INDEX_MD = """\
# Team Coding Spec

Add your team's coding conventions here.
This file is referenced by context manifests to inject guidelines into sub-agents.
"""

TASK_PY_STUB = """\
#!/usr/bin/env python3
\"\"\"Task management CLI. Placeholder — full implementation in Slice 2.\"\"\"
print("task.py: not yet implemented")
"""

TEAM_CLEANUP_STUB = """\
#!/usr/bin/env python3
\"\"\"team_cleanup.py — placeholder. Real implementation in harness_scripts/.\"\"\"
import sys
print("team_cleanup.py: real implementation not deployed", file=sys.stderr)
sys.exit(1)
"""

CONTEXT_PY_STUB = """\
#!/usr/bin/env python3
\"\"\"context.py — placeholder. Real implementation in harness_scripts/.\"\"\"
import sys
print("context.py: real implementation not deployed", file=sys.stderr)
sys.exit(1)
"""

VERIFY_PY_STUB = """\
#!/usr/bin/env python3
\"\"\"verify.py — placeholder. Real implementation in harness_scripts/.\"\"\"
import sys
print("verify.py: real implementation not deployed", file=sys.stderr)
sys.exit(1)
"""

DOCS_INDEX_MD = """\
# 文档索引

项目文档通过本文件登记主要目录用途。

## Harness

| 目录 | 内容 |
| --- | --- |
| `docs/tasks/` | 需求开发任务包，每个子目录对应一次需求开发 |
| `docs/standards/` | 团队长期工程规范，供需求开发过程自动注入上下文 |
"""

STANDARDS_INDEX_MD = """\
# 团队工程规范索引

此目录保存团队长期维护的工程规范。需求开发过程中会固定注入本索引文件，具体规范文件由任务的 `context.<role>.jsonl` 明确引用。
"""

VERIFY_JSON_TEMPLATE = """\
{
  "required": ["test", "scope"],
  "commands": {
    "lint": "",
    "type": "",
    "test": "",
    "coverage": ""
  },
  "scope": {
    "denied": [
      ".harness/runtime/**",
      "docs/standards/**"
    ]
  }
}
"""

GITIGNORE_TEMPLATE = """\
# harness defaults — keep these so __pycache__ etc. don't leak into commits

# harness runtime state (session pointers — local, never commit)
.harness/runtime/

# Python
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Node
node_modules/
dist/
build/
.vite/
coverage/

# OS
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
*.swp
"""

HOOK_SESSION_START = """\
#!/usr/bin/env python3
\"\"\"SessionStart hook — injects active task and role list. Placeholder.\"\"\"
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "Harness: no active task."}}))
"""

HOOK_WORKFLOW_STATE = """\
#!/usr/bin/env python3
\"\"\"UserPromptSubmit hook — injects workflow-state breadcrumb. Placeholder.\"\"\"
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "<workflow-state>no_task</workflow-state>"}}))
"""

HOOK_INJECT_CONTEXT = '''\
#!/usr/bin/env python3
"""PreToolUse hook — injects task context into sub-agent prompts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

STANDARD_ROLES = ("architect", "developer", "tester")
KNOWN_ROLES = STANDARD_ROLES
TASK_CONTEXT_FILENAMES = ("proposal.md", "design.md", "tasks.md")
ROOT_DESIGN_FILENAMES = ("design.md", "spec.md", "requirements.md")


def find_project_design(root: Path) -> Path | None:
    for name in ROOT_DESIGN_FILENAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def read_task_context_docs(task_dir: Path) -> list[tuple[str, str]]:
    results = []
    for name in TASK_CONTEXT_FILENAMES:
        content = read_file_safe(task_dir / name)
        if content:
            results.append((name, content))
    return results


def read_design_context(root: Path, task_dir: Path) -> list[tuple[str, str]]:
    task_docs = read_task_context_docs(task_dir)
    if task_docs:
        return task_docs

    design_path = find_project_design(root)
    if design_path is None:
        return []
    design = read_file_safe(design_path)
    return [(design_path.name, design)] if design else []


def find_harness_root(start: Path) -> Path | None:
    cur = start.resolve()
    while cur != cur.parent:
        if (cur / ".harness").is_dir():
            return cur
        cur = cur.parent
    return None


def resolve_session_key(data: dict) -> str | None:
    for key in ("session_id", "sessionId"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def get_active_task_dir(root: Path, data: dict) -> Path | None:
    sessions_dir = root / ".harness" / "runtime" / "sessions"
    if not sessions_dir.is_dir():
        return None

    key = resolve_session_key(data)
    session_file = None
    if key:
        candidate = sessions_dir / f"{key}.json"
        if candidate.is_file():
            session_file = candidate
    else:
        files = list(sessions_dir.glob("*.json"))
        if len(files) == 1:
            session_file = files[0]

    if not session_file:
        return None

    session = json.loads(session_file.read_text(encoding="utf-8"))
    task_ref = session.get("current_task")
    if not task_ref:
        return None

    task_dir = root / task_ref
    return task_dir if task_dir.is_dir() else None


def read_file_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return ""


def read_jsonl_context(root: Path, jsonl_path: Path) -> list[tuple[str, str]]:
    if not jsonl_path.is_file():
        return []

    results = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        file_path = item.get("file") or item.get("path")
        if not file_path:
            continue
        content = read_file_safe(root / file_path)
        if content:
            results.append((file_path, content))
    return results


def read_directory_md_files(directory: Path) -> list[tuple[str, str]]:
    if not directory.is_dir():
        return []
    results = []
    for f in sorted(directory.glob("*.md")):
        content = read_file_safe(f)
        if content:
            results.append((f.name, content))
    return results


def build_standard_role_context(root: Path, task_dir: Path, role: str) -> str:
    parts = []

    manifest = task_dir / f"context.{role}.jsonl"
    for file_path, content in read_jsonl_context(root, manifest):
        parts.append(f"=== {file_path} ===\\n{content}")

    for filename, content in read_design_context(root, task_dir):
        parts.append(f"=== {filename} ===\\n{content}")

    info = read_file_safe(task_dir / "info.md")
    if info:
        parts.append(f"=== info.md ===\\n{info}")

    if role == "architect":
        for filename, content in read_directory_md_files(task_dir / "research"):
            parts.append(f"=== research/{filename} ===\\n{content}")

    return "\\n\\n".join(parts)


def infer_role(tool_input: dict) -> str:
    direct_role = (
        tool_input.get("subagent_type")
        or tool_input.get("subagentType")
        or tool_input.get("role")
        or ""
    )
    if direct_role in KNOWN_ROLES:
        return direct_role

    for key in ("task_name", "name", "target"):
        value = tool_input.get(key)
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        for role in KNOWN_ROLES:
            if role in lowered:
                return role

    return ""


def prompt_field(tool_input: dict) -> str:
    if "prompt" in tool_input:
        return "prompt"
    if "message" in tool_input:
        return "message"
    return "prompt"


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = data.get("tool_input", {})
    role = infer_role(tool_input)

    if role not in KNOWN_ROLES:
        return 0

    cwd = data.get("cwd") or "."
    root = find_harness_root(Path(cwd))
    if root is None:
        return 0

    task_dir = get_active_task_dir(root, data)
    if task_dir is None:
        return 0
    context = build_standard_role_context(root, task_dir, role)

    if not context:
        return 0

    field = prompt_field(tool_input)
    original_prompt = tool_input.get(field, "")
    new_prompt = f"## Injected Context\\n\\n{context}\\n\\n---\\n\\n## Task\\n\\n{original_prompt}"

    updated_input = {**tool_input, field: new_prompt}
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": updated_input,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

AGENT_ARCHITECT = """\
---
name: architect
description: Designs (info.md), reviews diff vs design, refactors when needed. Absorbs research and review duties.
tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
---
# Architect Agent (v1.6: design + review + refactor)

Your job is **technical decomposition + design review**. You absorb the duties
of the old `research` and `reviewer` roles too.

**Input**: project-root `design.md` (or `spec.md` / `requirements.md`)
describing product + constraints. Read it, don't rewrite it.

**Outputs by phase**:
1. **Plan phase** → write `info.md` (technical breakdown with testable contracts)
   and `scope.json` (allowed/denied file change scope for this task)
2. **Execute phase, REVIEW step** → review developer's diff vs info.md, refactor for
   clarity, DM developer if changes needed
3. **Execute phase, RE-ENGAGE** → when tester or developer flags design deviation,
   update info.md, broadcast to teammates

**You do NOT author requirements**. If the design doc is incomplete, raise
questions to the main session.

## Research is your job too

If design needs external info (frameworks, library APIs), you research yourself
using your tools (Read, Glob, Grep, WebSearch, WebFetch). Persist substantial
findings to `{task_dir}/research/*.md`; otherwise inline into info.md rationale.

## Persistence (Teams mode)

You persist across slices. Before each task message, **re-read the project-root
design doc and your prior info.md** — they may have evolved. When you UPDATE
info.md mid-execution, SendMessage developer + tester so they re-read.

## Plan outputs

Write `info.md` with this structure:

1. **Module breakdown** — files/packages, dependency direction, naming
2. **Interface contracts** (testable — see below)
3. **Slice order** — which slice first, what each unlocks
4. **Risks / trade-offs**

Also write `scope.json` in the same task directory:

```json
{
  "allowed": ["src/**", "tests/**"],
  "denied": []
}
```

`allowed` must list the file or directory globs this task is expected to modify.
`denied` lists task-specific exclusions. The main session verifies this file
with `python3 .harness/scripts/verify.py all` before each slice commit.

## Interface contracts MUST be testable

```
### POST /api/v1/todos

Request:  {title: string (required, 1..200 chars), priority: "P0"|"P1"|"P2"}
Response 200: {id: int, title: string, done: false, priority: "...", created_at: ISO8601}
Response 400: {error: "title required" | "title too long", code: "VALIDATION"}
Header (always): X-Request-Id: <uuid>
```

This shape lets tester write failing tests BEFORE developer codes.

Bad: "POST /todos creates a todo" — too vague.

## Anchor tables — formula must drive expected values

If you write test anchor tables (inputs + expected results), **expected column
must be derivable from formula column**, not hand-typed.

Bad (typo-prone): `| "password1" | length 20 + lowercase 10 + digit 15 | 35 |` ← 35 ≠ 20+10+15=45

Good: list only formula; tester computes expected during RED phase.

## REVIEW step (after developer GREEN)

1. Run test suite — confirm GREEN baseline
2. `git diff` to see developer's changes
3. For each change, compare to: PRD criteria, info.md design, team spec
4. Look for: duplication, unclear naming, long functions, missing error handling, lint
5. **Refactor in small steps** — run tests after each. Must stay GREEN.
6. If deviation can't be fixed by refactor: update info.md (you own design),
   notify developer + tester via SendMessage

## Rules
- Read all `research/*.md` and the project-root design doc before designing
- **Every contract testable** — tester challenges anything vague
- Do NOT write product code (developer's GREEN job)
- Do NOT modify tests (tester's domain)
- Do NOT run git commit
- Tests must pass before AND after every refactor step
- Keep `scope.json` current if the approved slice plan changes
"""

AGENT_DEVELOPER = """\
---
name: developer
description: GREEN-phase implementer. Writes minimal code to pass tests tester already wrote.
tools: Read, Write, Edit, Bash, Glob, Grep
---
# Developer Agent (TDD GREEN phase)

You implement features such that the failing tests `tester` already wrote start
passing. You are NOT a from-scratch author — you respond to existing tests.

## Persistence (Teams mode)

You persist across slices. Before each new task message, **re-read the
project-root design doc and info.md** — architect may have updated info.md.
If you receive SendMessage saying "info.md updated", re-read immediately.

## Workflow

1. Run test suite — verify tests are RED as expected
2. Read failing tests carefully (they describe the contract precisely)
3. Read info.md (architect's design) and the project-root design doc
4. Read injected spec files (context.developer.jsonl)
5. Write **minimum code** to make tests pass
6. Run tests until GREEN
7. Report files modified + green test count

## TDD discipline

- **Don't write code no test demands.** Pulled to add functionality? Tests are
  missing — STOP, recommend tester re-run RED.
- **Don't optimize / refactor.** That's architect's REVIEW job.
- **If tests are wrong** (test asks for X but PRD says Y): STOP, report.
  Don't quietly fix the test.
- **If you need design clarification**: SendMessage architect (peer DM). Don't
  guess at info.md gaps.

## Rules
- Tests written by tester MUST exist before you write code
- Follow info.md design — don't reinvent architecture
- Do NOT run git commit
- Do NOT spawn other sub-agents
- Do NOT write or modify tests — that's tester's domain
"""

AGENT_TESTER = """\
---
name: tester
description: Test author. RED phase writes failing tests; VALIDATE phase adds edge cases after GREEN.
tools: Read, Write, Edit, Bash, Glob, Grep
---
# Tester Agent (TDD RED + VALIDATE phases)

You own quality. You run BEFORE developer (RED) AND AFTER architect's review
(VALIDATE). Your dispatch message tells you which mode.

## Persistence (Teams mode)

You persist across slices. Before each new task message, **re-read the
project-root design doc and info.md** — info.md may have been updated by architect.

## Mode A — RED (no production code yet)

Goal: write failing tests locking down behavior info.md promises.

1. Read PRD acceptance criteria
2. Read info.md — focus on testable contracts (request/response, error codes)
3. Read existing tests (if any)
4. For slice in scope, write tests that:
   - Cover each contract in info.md (happy path)
   - Cover each error case info.md lists (400, 500, validation)
   - Use the actual interface (don't mock the system under test)
5. Run tests — confirm they FAIL with expected reason (interface missing)
6. Report: which tests written, which contract each covers, RED proof

**You do NOT write production code in RED.** Tests must fail with "function
not defined" / "404" / etc.

## Mode B — VALIDATE (after architect REVIEW, tests GREEN)

Goal: harden coverage with edges contracts didn't enumerate.

1. Run full test suite — confirm GREEN baseline
2. Identify coverage gaps: empty/null/zero, boundary values, concurrency,
   cross-module integration
3. Write additional tests for these
4. Run suite — must stay GREEN (or RED if real bug found)
5. If a real production bug surfaces: fix the production code (you may)
6. Report: new tests, bugs found+fixed, coverage status

## TDD discipline

- **In RED: never write production code.** Tests must fail first.
- **In VALIDATE: modify production code only if a test reveals a real bug.**
  Don't add features.
- **If a contract in info.md is untestable** (vague, missing error cases):
  STOP, recommend re-engaging architect.

## Rules
- You can modify tests AND production code when fixing test-revealed bugs
- Do NOT run git commit
- Do NOT redesign features
"""


CMD_CONTINUE = """\
Check the current harness state and advise on next steps.

1. Read `.harness/runtime/sessions/` to find active task
2. Read task.json for status
3. Report current phase and recommended action
"""

CMD_FINISH = """\
Finish the current task. Steps:

1. Verify all task-related code changes are committed (safety gate)
2. Write `.harness/tasks/<task>/summary.md` with: status, changed files, lessons, next steps
3. Archive the task to `.harness/tasks/archive/YYYY-MM/`
4. Clear the session pointer
"""


SKILL_HARNESS_IMPLEMENT = """\
---
name: harness-implement
description: |
  当协作者要求依据 design.md、spec.md、requirements.md 等需求文档实现功能，
  且当前项目已经安装 harness（.harness/ + .claude/hooks）时使用。
  触发语: "按照 design.md 开发", "implement design.md", "按照详细设计文档开发",
  "用 harness 实现 xxx.md", "follow the harness flow", "走 harness 流程"，
  以及任何把 Markdown 需求文档作为实现依据的表达。
---

# Harness Implement

<!-- harness-managed-skill -->

该 skill 用于执行完整的 harness v1.6 TDD 流程：
读取项目根目录的需求文档 → 创建任务前执行 **Mandatory grill-me** →
architect 生成 `info.md` 和 `scope.json` → 执行模式确认 →
逐个 slice 执行 TDD 阶段（tester RED → developer GREEN →
architect REVIEW → tester VALIDATE）→ `verify.py all` → archive。
三代理 Teams 模式需要按任务单独确认。

## 使用场景

当协作者指定 `design.md`、`spec.md`、`requirements.md` 或类似 Markdown
需求文档，并要求完成实现时使用。项目根目录应当已经存在 `.harness/`
目录，并且 Claude Code hooks 已安装。

以下场景由主会话处理即可：

1. 需求仍处于探索或讨论阶段，尚无需求文档。
2. 只涉及错别字、重命名等极小改动。
3. 项目根目录不存在 `.harness/`。

## 核心原则

需求文档就是 PRD 来源。保持原文完整。architect 的职责是把需求拆解为
可以测试的技术契约，写入 `info.md`，并补充当前任务允许和禁止修改的
文件范围到 `scope.json`。

## Mandatory grill-me

每个 harness 实现请求都必须在 `task.py create` 之前运行 `grill-me`，
即使需求文档看起来已经完整。每次只问一个问题。能通过检查代码回答的
问题，先检查代码。只有在需求来源和 grill-me 回答确认之后，才创建
harness task。

## 流程总览

| Step | Action | Checkpoint? |
|------|--------|-------------|
| 1 | 确认项目根目录存在需求文档（`design.md` / `spec.md` / `requirements.md`）。Hooks 会读取原文件，无需复制。 | — |
| 2 | 在 `task.py create` 之前执行 Mandatory grill-me，并确认回答。 | **YES — 等待确认** |
| 3 | `task.py create "<title>"` | — |
| 4 | 整理 3 个 context manifest（architect/developer/tester）。 | — |
| 5 | 派发 `architect`，生成 `info.md` 和 `scope.json`。 | — |
| 6 | 检查 `info.md` 是否包含可测试契约和 slice 计划。 | — |
| 7 | 确认 slice 计划。 | **YES — 等待确认** |
| 8 | `task.py start <task-dir>` | — |
| 9 | 进行执行模式确认，询问是否启用 3-agent Teams mode。 | **YES — 等待确认** |
| 9a | 如果确认启用：`TeamCreate(...)` 并创建 3 个常驻 teammate。 | — |
| 9b | 如果未确认启用：主会话继续执行，只在阶段需要时派发一个角色。 | — |
| 10 | 每个 slice 执行：tester(RED) → developer(GREEN) → architect(REVIEW) → tester(VALIDATE)。 | 每个 slice **YES** |
| 11 | 运行 `python3 .harness/scripts/verify.py all`，通过后由主会话提交该 slice。 | — |
| 12 | 对剩余 slice 重复步骤 10-11。 | — |
| 13 | 如果启用了 Teams mode：执行 TeamDelete 和 `team_cleanup.py`，然后执行 `task.py archive <task-dir>`。 | — |

## 步骤模板

### 1-3. 启动任务

```bash
# 检查项目根目录是否存在需求文档。
ls design.md spec.md requirements.md 2>/dev/null
```

此时运行 `grill-me`。在需求边界、验收标准和主要设计决策确认之前，
保持在任务创建之前的阶段。

```bash
# 创建 task。Hooks 会读取项目根目录的需求文档，无需复制到 task 目录。
python3 .harness/scripts/task.py create "<short title from design doc>"
```

### 5. 整理 context manifests

每个 manifest 必须至少包含一行带 `file` 字段的真实条目，不能只保留
`_example`。最小示例如下：

```jsonl
# context.architect.jsonl
{"file": ".harness/spec/index.md", "reason": "团队设计约定"}

# context.developer.jsonl
{"file": ".harness/spec/index.md", "reason": "团队编码约定"}

# context.tester.jsonl
{"file": ".harness/spec/index.md", "reason": "团队测试约定"}
```

这 3 个 manifest 由 `task.py create` 创建，初始会带一行 `_example`。
添加真实条目时，使用 `Edit`，必要时使用 `replace_all`；也可以先 `Read`
再 `Write`。

### 6. 派发 architect

```
Agent(
  name: "architect",
  subagent_type: "architect",
  mode: "bypassPermissions",
  prompt: "读取项目根目录的需求文档，生成 info.md，包含：
           (1) 模块拆解，(2) 可测试接口契约，
           (3) slice 顺序，(4) 关键不确定点。
           同时写入 scope.json，包含本任务 allowed/denied 文件 glob。"
)
```

### 9. 激活任务并完成执行模式确认

```bash
python3 .harness/scripts/task.py start <task-dir>
```

向协作者返回：

1. 已确认的 slice 列表。
2. 预计使用的测试命令。
3. 是否建议启用 3-agent Teams mode 的简短判断。

只有在协作者明确确认 Teams mode 之后，才执行 `TeamCreate`。

### 9a. 已确认 Teams mode：启动 team

```
TeamCreate(team_name: "<task-slug>", description: "<task title>")

Agent(team_name: "<slug>", name: "architect", subagent_type: "architect",
      mode: "bypassPermissions", prompt: "Stand by for REVIEW phases per slice.")

Agent(team_name: "<slug>", name: "developer", subagent_type: "developer",
      mode: "bypassPermissions", prompt: "Stand by for GREEN phases per slice.")

Agent(team_name: "<slug>", name: "tester", subagent_type: "tester",
      mode: "bypassPermissions", prompt: "Stand by for RED and VALIDATE phases per slice.")
```

如果使用 TaskCreate 跟踪 slice，应当在 TeamCreate 之后创建，确保任务进入
team 共享 TaskList。

### 9b. 主会话模式

主会话模式下保持同样的 TDD 顺序。只有在当前阶段需要特定角色上下文时，
才派发一次性角色任务，并把结果带回主会话继续处理。

### 11. 每个 slice 的 TDD 循环

启用 Teams mode 时，slice N 按以下方式发送消息：

```
SendMessage(to: "tester",    message: "RED phase. Slice N: <X>. Write failing tests.")
# wait for idle

SendMessage(to: "developer", message: "GREEN phase. Slice N. Make tester's tests pass.")
# wait for idle

SendMessage(to: "architect", message: "REVIEW phase. Slice N. Refactor + verify design conformance.")
# wait for idle

SendMessage(to: "tester",    message: "VALIDATE phase. Slice N. Add edge case tests.")
# wait for idle
```

**提交前**：运行 `python3 .harness/scripts/verify.py all`。该命令会根据
`.harness/verify.json` 和当前 task 的 `scope.json` 执行 lint、类型检查、
测试、覆盖率和文件变更范围检查。

如果 `verify.py all` 失败，先修复失败项。通过后，主会话再执行
`git add` 和 `git commit`。

主会话模式仍然保持相同阶段顺序。小范围阶段可以由主会话处理；需要角色
上下文时，派发 `tester`、`developer` 或 `architect` 作为一次性专家任务。

### 14. 清理

`TeamDelete` 只移除 team 配置和 worktree；实际 sub-agent Claude 进程仍可能
存在。归档前运行 harness 清理脚本：

```
TeamDelete()
```

```bash
python3 .harness/scripts/team_cleanup.py <task-slug>
```

```bash
python3 .harness/scripts/task.py archive <task-dir>
```

## 必须遵守的行为

1. 在 PRD 确认、slice 计划确认、执行模式确认和每个 slice review 点等待确认。
2. 每个 harness 实现请求都必须在 `task.py create` 前执行 Mandatory grill-me。
3. 每个 slice 提交前都必须运行 `python3 .harness/scripts/verify.py all`。
4. 每次 Agent 调用都必须传入 `mode: "bypassPermissions"`。
5. 默认不得创建 3 个执行 teammate。Teams mode 需要在 `task.py start` 后明确确认。
6. Teams mode 确认后，一次性创建 3 个执行 teammate，并在每个 slice 中通过 SendMessage 复用。
7. sub-agent 禁止执行 git commit，提交由主会话负责。
8. tester 或 developer 发现设计偏差时，向 architect 发送 REVIEW 消息；architect 可更新 `info.md`，并通知相关 teammate 重新读取。
9. 归档时执行 `TeamDelete` 和 `team_cleanup.py`。

## 常见错误

| Mistake | Fix |
|---------|-----|
| 重写需求文档 | Hooks 会读取项目根目录的原始文档，该文档就是 PRD 来源。 |
| 跳过 Mandatory grill-me | 回到 `task.py create` 之前，先执行 grill-me。 |
| 提交前跳过 `verify.py all` | 先运行完整验证脚本，再进入提交步骤。 |
| 跳过 manifest 整理 | `task.py start` 会拒绝继续，先整理 3 个 context manifest。 |
| architect 产出的 `info.md` 过于笼统 | 重新派发 architect，并明确要求输出可测试契约。 |
| sub-agent 执行 git commit | 停止该动作，提交由主会话执行。 |
| 忘记 `mode: "bypassPermissions"` | 每次 Agent 调用都传入该字段。 |
| 未确认就创建 3 个 teammate | 先完成执行模式确认。 |
| 跳过 tester(RED) | 回到 TDD 顺序，先补失败测试。 |
| 仅依赖 `TeamDelete` 清理进程 | `TeamDelete` 后继续运行 `team_cleanup.py`。 |
"""


SKILL_HARNESS_IMPLEMENT_CODEX = """\
---
name: harness-implement
description: |
  在 Codex 中，当协作者要求依据 design.md、spec.md、requirements.md 等需求文档
  实现功能，且项目已经初始化 harness 时使用。
  触发语: "按照 design.md 开发", "implement design.md", "按照详细设计文档开发",
  "用 harness 实现 xxx.md", "follow the harness flow", "走 harness 流程"。
---

# Harness Implement for Codex

<!-- harness-managed-skill -->

Codex 通过 `.codex/hooks.json` 接入项目 hook。Harness 使用这些 hook
向 Codex child agents 注入 task 状态和角色上下文。

## 使用场景

当协作者指定 `design.md`、`spec.md`、`requirements.md` 或其他 Markdown
需求文档，并要求在 harness 项目中完成实现时使用。

## Mandatory grill-me

每个 harness 实现请求都必须在 `task.py create` 前运行 `grill-me`。每次只问
一个问题。能通过检查代码回答的问题，先检查代码。只有在需求来源和
grill-me 回答确认后，才创建 task。

## 必要安装内容

项目应当包含：

```text
.harness/
.codex/hooks.json
.codex/hooks/harness-session-start.py
.codex/hooks/harness-workflow-state.py
.codex/hooks/harness-inject-context.py
AGENTS.md
```

首次使用时，Codex 可能要求信任新安装的 hooks。检查这些 hooks 指向项目本地
`.codex/hooks/` 脚本后，再信任 harness hooks。

## 必须执行的流程

| Step | Action |
| --- | --- |
| 1 | 确认项目根目录存在需求文档。 |
| 2 | 在 `task.py create` 前执行 Mandatory grill-me，并确认回答。 |
| 3 | 运行 `python3 .harness/scripts/task.py create "<title>"`。 |
| 4 | 整理 `context.architect.jsonl`、`context.developer.jsonl` 和 `context.tester.jsonl`。 |
| 5 | 使用 `spawn_agent` 创建 `architect`，生成 `info.md` 和 `scope.json`。 |
| 6 | 检查 `info.md` 是否包含可测试契约和 slice 计划。 |
| 7 | 运行 `python3 .harness/scripts/task.py start <task-dir>`。 |
| 8 | 完成执行模式确认，询问是否启用 3-agent mode。 |
| 9 | 如果确认启用，保持 architect/tester/developer child agents 可用；否则只在阶段需要时创建一个角色。 |
| 10 | 每个 slice 执行 tester RED、developer GREEN、architect REVIEW、tester VALIDATE。 |
| 11 | parent session 运行 `python3 .harness/scripts/verify.py all`，并负责 git commit。 |
| 12 | 关闭 child agents 并归档 task。 |

## Codex Agent Dispatch

使用 `spawn_agent` 创建角色 session。`task_name` 中必须包含 harness 角色名，
这样 `PreToolUse` hook 可以推断角色并注入匹配的上下文。

Tester RED:

```text
spawn_agent:
  task_name: harness_tester
  agent_type: worker
  message: RED phase. Slice N: write failing tests only.
```

Developer GREEN:

```text
spawn_agent:
  task_name: harness_developer
  agent_type: worker
  message: GREEN phase. Slice N: make tester's failing tests pass.
```

Architect REVIEW:

```text
spawn_agent:
  task_name: harness_architect
  agent_type: worker
  message: REVIEW phase. Slice N: check design conformance and refactor if needed.
```

继续同一个 slice 或进入下一个 slice 时，可以用 `followup_task` 复用已有角色
session。使用 `wait_agent` 收集结果，角色 session 完成后使用 `close_agent`。

默认不得一次性创建三个角色 agent。`task.py start` 之后先返回 slice 计划并完成
执行模式确认。没有该确认时，只创建当前阶段需要的角色。

## Hook 契约

当 `task_name`、`name` 或 `target` 包含以下角色名时，`PreToolUse` hook 会注入上下文：

```text
architect
developer
tester
```

注入上下文来自：

```text
context.<role>.jsonl
proposal.md
design.md
tasks.md
info.md
research/*.md for architect
```

## 角色边界

1. `architect` 负责写入 `info.md`、检查设计符合性，并可重构代码。
2. `tester` 负责 RED 测试和 VALIDATE 边界测试。
3. `developer` 负责 GREEN 阶段实现代码。
4. parent session 负责最终检查、测试结果解释和 git commit。

## 强制检查

1. `task.py start` 前必须整理三个 context manifest。
2. `task.py create` 前必须运行 Mandatory grill-me。
3. 每个 slice 提交前必须运行 `python3 .harness/scripts/verify.py all`。
4. Codex `task_name` 必须包含角色名。
5. 打开三个角色 agent 前必须完成执行模式确认。
6. parent session 必须验证测试结果后，才能判定 slice 完成。
7. 归档使用 `python3 .harness/scripts/task.py archive <task-dir>`。
"""


SKILL_GRILL_ME = """\
---
name: grill-me
description: 对计划或设计进行连续追问，逐项确认需求边界、验收标准、依赖关系和主要决策。触发语包括 "grill me"。
---

<!-- harness-managed-skill -->

围绕当前计划或设计进行严格追问，直到需求边界、验收标准、依赖关系和主要决策都清楚。

每次只问一个问题。

每个问题都要给出推荐回答，方便协作者确认或修正。

能通过检查代码回答的问题，先检查代码，再继续提问。
"""


SKILL_HARNESS_CONFIGURE_VERIFY = """\
---
name: harness-configure-verify
description: 当 harness 项目需要配置 .harness/verify.json，或者需要设置提交前 lint、类型检查、测试和覆盖率检查时使用。
---

# Harness Configure Verify

<!-- harness-managed-skill -->

为当前项目配置 `.harness/verify.json`。目标是让
`python3 .harness/scripts/verify.py all` 在每个 harness slice 提交前真正执行
lint、类型检查、测试、覆盖率和文件变更范围检查。

该 skill 同时供 Claude Code 和 Codex agents 使用。

## 必须执行的流程

1. 读取当前 `.harness/verify.json`。
2. 检查项目入口文件：`Makefile`、`go.mod`、`package.json`、
   `pyproject.toml`、`Cargo.toml`、`README.md` 和 `scripts/`。
3. 识别不会修改文件的检查命令：
   - `commands.lint`
   - `commands.type`
   - `commands.test`
   - `commands.coverage`
4. 先给出推荐 JSON patch，等待确认后再写入文件。
5. 确认后更新 `.harness/verify.json`。
6. 条件允许时运行重点验证命令，然后报告结果。

## 命令规则

1. 优先选择只检查的命令，避免会重写文件的命令。
2. 避免使用带 `-w`、`--write` 或同类修改参数的 formatter 脚本。
3. 覆盖率阈值由项目自己的 coverage 命令负责，harness 只检查命令退出码。
4. 如果无法从项目文件推断命令，说明不确定的字段，并给出最保守的占位命令。

## 常见示例

Go 项目常用：

```json
{
  "commands": {
    "lint": "test -z \\"$(gofmt -l .)\\" && go vet ./...",
    "type": "go test -run '^$' ./...",
    "test": "go test ./...",
    "coverage": "go test ./... -coverprofile=.harness/runtime/coverage.out"
  },
  "scope": {
    "denied": [".harness/runtime/**", "output/**", "log/**"]
  }
}
```

Node 项目常用 package scripts：

```json
{
  "commands": {
    "lint": "npm run lint",
    "type": "npm run typecheck",
    "test": "npm test",
    "coverage": "npm run coverage"
  },
  "scope": {
    "denied": [".harness/runtime/**", "dist/**", "coverage/**"]
  }
}
```
"""

SKILL_REQUIREMENT_CONFIRMATION = """\
---
name: requirement-confirmation
description: |
  需求确认 skill。用于在需求开发前逐项确认开发意图、验收标准、边界条件、依赖关系和未决问题。
  触发语包括 "需求确认"、"确认需求"、"grill me"、"先问清楚需求"、"需求还要再确认"。
---

# 需求确认

<!-- harness-managed-skill -->

该 skill 是 harness 需求开发前置环节。目标是让开发意图、验收标准、边界条件和关键依赖形成可核验记录，避免模型根据模糊描述自行补全。

## 必须遵守

每次只提出一个问题。

每个问题都给出推荐回答，推荐回答应当基于已知需求文档和代码检查结果。

能够通过检查仓库回答的问题，先检查仓库，再继续提问。

即使 `design.md`、`spec.md` 或 `requirements.md` 内容完整，也必须先复述开发意图，并等待协作者确认。

## 完成标准

确认完成后，通过 harness 内部工具写入 `clarification.jsonl`，并生成 `clarification.md` 阅读快照。有效确认记录必须包含：

| 字段 | 要求 |
| --- | --- |
| `developmentIntent` | 开发者理解的开发意图 |
| `acceptanceCriteria` | 可验证的验收标准 |
| `boundaries` | 明确的范围边界 |
| `openQuestions` | 必须为空数组 |
| `confirmed` | 必须为 `true` |
| `confirmedBy` | 必须为 `collaborator` |
| `sourceDoc` | 需求来源文件或 `inline-request` |
| `sourceDocHash` | 需求来源内容哈希 |

`clarification.jsonl` 是阶段推进门禁依据，`clarification.md` 只作为阅读快照。
"""

SKILL_REQUIREMENT_DEVELOPMENT = """\
---
name: requirement-development
description: |
  需求开发 skill。用于依据 design.md、spec.md、requirements.md 或协作者的内联需求，在 harness 项目中完成流程化开发。
  触发语包括 "按 design.md 开发"、"按照需求开发"、"继续需求开发"、"走 harness 流程"、"implement design.md"。
---

# 需求开发

<!-- harness-managed-skill -->

该 skill 负责组织 harness 需求开发流程。协作者通过自然语言表达任务，模型使用 `.harness/scripts/task.py`、`.harness/scripts/verify.py` 和项目 hooks 维护阶段状态与证据文件。

## 前置要求

进入开发前必须先使用 `requirement-confirmation`。如果当前任务尚未生成有效 `clarification.jsonl` 确认记录，应当自动转入需求确认。

即使需求文档完整，也至少复述开发意图，确认验收标准和范围边界。

## 阶段顺序

| 阶段 | 责任角色 | 必要证据 |
| --- | --- | --- |
| `clarify` | 主会话 | `clarification.jsonl`、`clarification.md` |
| `plan` | `architect` | `implementation-plan.md`、`scope.json`、三份 `context.<role>.jsonl` |
| `red` | `tester` | `test-result.red.json` |
| `green` | `developer` | `test-result.green.json` |
| `review` | `architect` | `review-result.json` |
| `validate` | `tester` | `verify-result.json` |
| `done` | 主会话 | 任务可以归档 |

阶段推进只能通过 `task.py advance <phase>` 完成。`task.json`、`clarification.jsonl`、`clarification.md`、`test-result.red.json`、`test-result.green.json`、`review-result.json` 和 `verify-result.json` 属于受控文件，由 harness 工具生成。

## 计划文件

`implementation-plan.md` 只保存实现计划，固定包含以下章节：

```markdown
# 实现计划

## 开发意图摘要
## 影响范围
## 技术方案
## 可测试契约
## Slice 顺序
## 验证方式
## 已知限制
```

## 执行规则

默认使用 `agent-team` 执行模式。每个阶段按需调用对应角色，角色会通过 hook 注入 `docs/standards/index.md`、`clarification.md`、`implementation-plan.md` 和角色自己的 `context.<role>.jsonl`。

如果当前运行环境没有子代理能力，可以降级为 `single-session`，并在 `task.json.executionModeFallbackReason` 记录原因。

每个阶段完成后必须写入对应证据文件，再通过 `task.py advance` 进入下一阶段。最终使用 `verify.py all` 生成 `verify-result.json`，通过后才能进入 `done`。
"""

SKILL_HARNESS_IMPLEMENT_COMPAT = """\
---
name: harness-implement
description: |
  兼容入口。旧触发语 "harness-implement"、"按 design.md 开发"、"implement design.md" 会转入 requirement-development。
---

# Harness Implement Compatibility

<!-- harness-managed-skill -->

`harness-implement` 是旧名称。当前正式入口是 `requirement-development`，中文名称为需求开发 skill。

收到实现类请求时，按照 `requirement-development` 执行，并先转入 `requirement-confirmation` 完成需求确认。
"""

SKILL_GRILL_ME_COMPAT = """\
---
name: grill-me
description: 兼容入口。旧触发语 "grill me" 会转入 requirement-confirmation，也就是需求确认 skill。
---

# Grill Me Compatibility

<!-- harness-managed-skill -->

`grill-me` 是旧名称。当前正式入口是 `requirement-confirmation`，中文名称为需求确认 skill。

继续保持每次只问一个问题，每个问题给出推荐回答，并以 `clarification.jsonl` 作为需求确认门禁依据。
"""

AGENT_ARCHITECT = """\
---
name: architect
description: 负责 plan 和 review 阶段，编写实现计划、维护 scope，并检查实现是否符合需求确认结果。
tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
---
# Architect Agent

读取 `clarification.md`、`implementation-plan.md`、`docs/standards/index.md` 和 `context.architect.jsonl` 中明确引用的文件。

在 `plan` 阶段，编写 `implementation-plan.md` 和 `scope.json`。计划文件只能保存实现计划，必须包含固定章节：开发意图摘要、影响范围、技术方案、可测试契约、Slice 顺序、验证方式、已知限制。

在 `review` 阶段，检查当前变更是否符合需求确认、实现计划和团队规范，并通过 `task.py review record` 写入 `review-result.json`。需要修正代码时保持测试通过。

禁止手工编辑受控文件：`task.json`、`clarification.jsonl`、`clarification.md`、`test-result.red.json`、`test-result.green.json`、`review-result.json`、`verify-result.json`。
"""

AGENT_DEVELOPER = """\
---
name: developer
description: 负责 green 阶段，根据 RED 测试实现最小代码变更。
tools: Read, Write, Edit, Bash, Glob, Grep
---
# Developer Agent

读取 `clarification.md`、`implementation-plan.md`、`docs/standards/index.md` 和 `context.developer.jsonl` 中明确引用的文件。

在 `green` 阶段，先确认 `test-result.red.json` 已经记录目标测试的预期失败，再实现代码使同一组目标测试通过。通过后使用 `verify.py green` 写入 `test-result.green.json`。

实现必须遵守 `scope.json` 的变更范围。发现需求、计划或测试之间存在冲突时，停止实现并返回主会话处理。

禁止执行 git commit，禁止手工编辑 harness 受控文件。
"""

AGENT_TESTER = """\
---
name: tester
description: 负责 red 和 validate 阶段，编写失败测试、补充边界测试并生成验证证据。
tools: Read, Write, Edit, Bash, Glob, Grep
---
# Tester Agent

读取 `clarification.md`、`implementation-plan.md`、`docs/standards/index.md` 和 `context.tester.jsonl` 中明确引用的文件。

在 `red` 阶段，根据可测试契约编写目标测试，并使用 `verify.py red` 写入 `test-result.red.json`。该阶段要求目标测试出现预期失败。

在 `validate` 阶段，补充边界测试并运行必要验证，最终由主会话运行 `verify.py all` 写入 `verify-result.json`。

禁止执行 git commit，禁止手工编辑 harness 受控文件。
"""

CMD_CONTINUE = """\
查看当前需求开发状态。

读取 `.harness/runtime/sessions/` 中的当前任务指针，展示 `docs/tasks/<task>/task.json` 的 `status`、`phase` 和下一阶段需要的证据文件。
"""

CMD_FINISH = """\
归档当前需求开发任务。

任务必须先进入 `phase=done`，并且 `verify-result.json.success=true`。归档后任务移动到 `docs/tasks/archive/YYYY-MM/<task>/`。
"""

HOOK_INJECT_CONTEXT = '''\
#!/usr/bin/env python3
"""PreToolUse hook: inject phase-safe role context."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

LOCAL_CONTEXT_KEY = "local"
KNOWN_ROLES = ("architect", "developer", "tester")
PHASE_ROLE = {
    "plan": "architect",
    "red": "tester",
    "green": "developer",
    "review": "architect",
    "validate": "tester",
}
CONTROLLED_SUFFIXES = (
    "task.json",
    "clarification.jsonl",
    "clarification.md",
    "test-result.red.json",
    "test-result.green.json",
    "review-result.json",
    "verify-result.json",
)


def find_project_root(start: Path) -> Path | None:
    cur = start.resolve()
    while cur != cur.parent:
        if (cur / ".harness").is_dir():
            return cur
        cur = cur.parent
    return None


def resolve_session_key(data: dict) -> str | None:
    for key in ("session_id", "sessionId"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return os.environ.get("HARNESS_CONTEXT_ID")


def task_dir_from_ref(root: Path, task_ref: str) -> Path | None:
    task_dir = root / task_ref
    return task_dir if task_dir.is_dir() else None


def unique_in_progress_task_dir(root: Path) -> Path | None:
    tasks_dir = root / "docs" / "tasks"
    if not tasks_dir.is_dir():
        return None
    matches = []
    for task_dir in tasks_dir.iterdir():
        if not task_dir.is_dir() or task_dir.name == "archive":
            continue
        task_json = task_dir / "task.json"
        if not task_json.is_file():
            continue
        data = json.loads(task_json.read_text(encoding="utf-8"))
        if data.get("status") == "in_progress":
            matches.append(task_dir)
    return matches[0] if len(matches) == 1 else None


def get_active_task_dir(root: Path, data: dict) -> Path | None:
    sessions_dir = root / ".harness" / "runtime" / "sessions"
    key = resolve_session_key(data)
    candidates = []
    if key:
        candidates.append(sessions_dir / f"{key}.json")
    candidates.append(sessions_dir / f"{LOCAL_CONTEXT_KEY}.json")
    for path in candidates:
        if not path.is_file():
            continue
        session = json.loads(path.read_text(encoding="utf-8"))
        task_ref = session.get("current_task")
        if task_ref:
            task_dir = task_dir_from_ref(root, task_ref)
            if task_dir:
                return task_dir
    return unique_in_progress_task_dir(root)


def read_file_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return ""


def read_jsonl_context(root: Path, jsonl_path: Path) -> list[tuple[str, str]]:
    if not jsonl_path.is_file():
        return []
    results = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "_example" in item:
            continue
        file_path = item.get("file")
        if not isinstance(file_path, str) or not file_path:
            continue
        content = read_file_safe(root / file_path)
        if content:
            results.append((file_path, content))
    return results


def task_phase(task_dir: Path) -> str:
    data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    return data.get("phase", "unknown")


def build_role_context(root: Path, task_dir: Path, role: str) -> str:
    parts = []
    standards = read_file_safe(root / "docs" / "standards" / "index.md")
    if standards:
        parts.append(f"=== docs/standards/index.md ===\\n{standards}")
    clarification = read_file_safe(task_dir / "clarification.md")
    if clarification:
        parts.append(f"=== clarification.md ===\\n{clarification}")
    plan = read_file_safe(task_dir / "implementation-plan.md")
    if plan:
        parts.append(f"=== implementation-plan.md ===\\n{plan}")
    for file_path, content in read_jsonl_context(root, task_dir / f"context.{role}.jsonl"):
        parts.append(f"=== {file_path} ===\\n{content}")
    return "\\n\\n".join(parts)


def infer_role(tool_input: dict) -> str:
    direct = tool_input.get("subagent_type") or tool_input.get("subagentType") or tool_input.get("role") or ""
    if direct in KNOWN_ROLES:
        return direct
    for key in ("task_name", "name", "target"):
        value = tool_input.get(key)
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        for role in KNOWN_ROLES:
            if role in lowered:
                return role
    return ""


def prompt_field(tool_input: dict) -> str:
    if "prompt" in tool_input:
        return "prompt"
    if "message" in tool_input:
        return "message"
    return "prompt"


def controlled_edit_target(tool_input: dict) -> str | None:
    candidates = []
    for key in ("file_path", "path", "target_file"):
        value = tool_input.get(key)
        if isinstance(value, str):
            candidates.append(value)
    for value in candidates:
        normalized = value.replace("\\\\", "/")
        if "/docs/tasks/" in normalized or normalized.startswith("docs/tasks/"):
            if any(normalized.endswith(suffix) for suffix in CONTROLLED_SUFFIXES):
                return value
    return None


def emit_block(reason: str) -> int:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "additionalContext": reason,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    tool_input = data.get("tool_input", {})
    target = controlled_edit_target(tool_input)
    if target:
        return emit_block(f"受控文件 {target} 只能通过 harness 内部工具生成，禁止手工编辑。")
    role = infer_role(tool_input)
    if role not in KNOWN_ROLES:
        return 0
    root = find_project_root(Path(data.get("cwd") or "."))
    if root is None:
        return 0
    task_dir = get_active_task_dir(root, data)
    if task_dir is None:
        return 0
    phase = task_phase(task_dir)
    expected = PHASE_ROLE.get(phase)
    if expected != role:
        return emit_block(f"当前阶段 {phase} 不允许调用 {role}。应执行的角色职责是 {expected or '无开发角色'}。")
    context = build_role_context(root, task_dir, role)
    if not context:
        return 0
    field = prompt_field(tool_input)
    original = tool_input.get(field, "")
    updated = {**tool_input, field: f"## Injected Context\\n\\n{context}\\n\\n---\\n\\n## Task\\n\\n{original}"}
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": updated,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

WORKFLOW_MD = """\
# Harness 阶段说明

[workflow-phase:no_task]
当前没有激活的需求开发任务。收到需求开发请求时，先进入 `requirement-confirmation`，确认开发意图、验收标准和范围边界。
[/workflow-phase:no_task]

[workflow-phase:clarify]
当前处于需求确认阶段。有效门禁是 `clarification.jsonl` 中最近一条 `event=confirm` 记录，且 `openQuestions=[]`、`confirmed=true`、`confirmedBy=collaborator`。
[/workflow-phase:clarify]

[workflow-phase:plan]
当前处于实现计划阶段。只允许调用 `architect`，生成 `implementation-plan.md`、`scope.json`，并补齐三份 `context.<role>.jsonl` 的真实文件引用。
[/workflow-phase:plan]

[workflow-phase:red]
当前处于 RED 阶段。只允许调用 `tester`，目标是写出预期失败测试，并通过 `verify.py red` 写入 `test-result.red.json`。
[/workflow-phase:red]

[workflow-phase:green]
当前处于 GREEN 阶段。只允许调用 `developer`，目标是让 RED 阶段同一组目标测试通过，并通过 `verify.py green` 写入 `test-result.green.json`。
[/workflow-phase:green]

[workflow-phase:review]
当前处于 REVIEW 阶段。只允许调用 `architect`，检查需求符合性和代码质量，并通过 `task.py review record` 写入 `review-result.json`。
[/workflow-phase:review]

[workflow-phase:validate]
当前处于 VALIDATE 阶段。只允许调用 `tester`，补充验证后由主会话运行 `verify.py all` 写入 `verify-result.json`。
[/workflow-phase:validate]

[workflow-phase:done]
任务已经完成验证，可以归档。
[/workflow-phase:done]

[workflow-phase:archived]
任务已经归档。
[/workflow-phase:archived]
"""

HARNESS_SECTION = """\
# Agent Harness

本项目使用 harness 支持流程化需求开发。协作者使用自然语言表达任务，模型通过内部脚本维护状态和证据文件。

## 自然语言入口

| 表达 | 处理方式 |
| --- | --- |
| 按 `design.md` 开发 | 进入 `requirement-development` |
| 继续需求开发 | 读取当前任务并推进下一阶段 |
| 查看当前需求开发状态 | 读取 `task.json` 的 `status` 和 `phase` |
| 归档当前任务 | 在 `phase=done` 后移动到 `docs/tasks/archive/` |

## 目录约定

任务包保存在 `docs/tasks/<task>/`。团队工程规范保存在 `docs/standards/`。`docs/index.md` 记录这些目录用途。

## 阶段顺序

`task.json.status` 表示任务大状态，`task.json.phase` 表示细阶段。阶段顺序固定为：

```text
clarify -> plan -> red -> green -> review -> validate -> done -> archived
```

阶段推进只能通过 `python3 .harness/scripts/task.py advance <phase>` 完成。

## 需求确认

需求开发前必须先完成 `requirement-confirmation`。即使需求文档完整，也要复述开发意图、验收标准和边界条件，并等待协作者确认。

`clarification.jsonl` 是需求确认门禁依据，`clarification.md` 是阅读快照。

## 角色职责

| 阶段 | 角色 | 主要产物 |
| --- | --- | --- |
| `plan` | `architect` | `implementation-plan.md`、`scope.json` |
| `red` | `tester` | `test-result.red.json` |
| `green` | `developer` | `test-result.green.json` |
| `review` | `architect` | `review-result.json` |
| `validate` | `tester` | `verify-result.json` |

hooks 会根据 `phase` 限制角色调用，并注入 `docs/standards/index.md`、`clarification.md`、`implementation-plan.md` 和角色专属 `context.<role>.jsonl`。

## 受控文件

以下文件只能由 harness 内部工具生成或更新：`task.json`、`clarification.jsonl`、`clarification.md`、`test-result.red.json`、`test-result.green.json`、`review-result.json`、`verify-result.json`。

主会话负责最终验证和 git 提交，子代理负责阶段内专业任务。
"""


LEGACY_HARNESS_SECTION = """\
# Agent Harness

This project uses a 3-role agent harness for stateful AI collaboration.
Hooks at `.claude/hooks/harness-*.py` inject context every session/turn.

## Workflow Phases

| Phase | Status | Sequence (order matters) |
| --- | --- | --- |
| Plan | `planning` | confirm project-root design doc → **Mandatory grill-me before `task.py create`** → (optional) research → **curate 3 manifests** → architect writes info.md + scope.json → `task.py start` |
| Execute | `in_progress` | confirm execution mode → **TDD cycle**: tester(RED) → developer(GREEN) → architect(REVIEW/REFACTOR) → tester(VALIDATE) → `verify.py all` → main session commits |
| Done | `archived` | `/harness:finish` writes `summary.md` and moves task to archive/ |

**Why curate before architect**: architect reads `context.architect.jsonl` to see
team specs during design. If dispatched before curation, it designs blind.

**Why TDD by default**: the harness assumes test-first. tester runs BEFORE developer.
This forces info.md to have testable contracts and prevents developer from
writing untested code.

## Active Task

Pointer lives in `.harness/runtime/sessions/<session-key>.json`.
The per-turn `<workflow-state>` breadcrumb tells you the current phase. **Trust it.**

To check active task: `python3 .harness/scripts/task.py current`
To create a new task: `python3 .harness/scripts/task.py create "<title>"`
To activate planning → in_progress: `python3 .harness/scripts/task.py start <dir>`

## Requirement Confirmation

Run `grill-me` before `task.py create` for every harness implementation request.
Ask one question at a time. If codebase inspection can answer a question,
inspect the codebase instead of asking. Proceed only after the design source and
grill-me answers are confirmed.

## Agent Roles (3 — dispatched via Task/Agent tool)

| Role | TDD Phase | Reads | Writes |
| --- | --- | --- | --- |
| `architect` | (Plan + REVIEW + RE-ENGAGE) | research/, project-root design, code, manifest | `info.md`, refactored code |
| `developer` | GREEN | failing tests, project-root design, info.md, manifest | minimum code to pass tests |
| `tester` | RED + VALIDATE | project-root design, info.md, manifest | failing tests + edge case tests |

**No sub-agent commits.** Main session commits after the slice's TDD cycle is GREEN.
Main session must run `python3 .harness/scripts/verify.py all` before every
slice commit.
**Only tester modifies tests.** developer + architect must not touch test files.

## Decision Tree

```
Starting a NEW feature slice?            → tester (RED) — failing tests first
Tests are RED, need code?                → developer (GREEN)
Tests are GREEN, ready to refactor?      → architect (REVIEW/REFACTOR)
Code refactored, want hardening?         → tester (VALIDATE) — edge cases
Need a design decision / re-engagement?  → architect

Trivial change (typo/rename/config)?     → main session may edit directly,
                                           but MUST state "skipping TDD because <reason>"
```

## Dispatching via Claude Agent Teams (v1.6+)

Three-agent Teams mode is optional per task. After `task.py start`, the main
session returns the slice plan to the user and asks whether to enable this mode.

When enabled, sub-agents are dispatched as Team teammates, not plain Task calls.
This unlocks:
- **Persistence**: teammate retains context across multiple turns
- **Peer DM**: teammates can SendMessage each other
- **Shared TaskList**: all teammates see the team's tasks

### Bootstrap (after execution-mode confirmation)

```
TeamCreate(team_name: "<task-slug>", description: "<task title>")
```

### Spawn / dispatch a teammate

```
Agent(
  team_name: "<task-slug>",
  name: "tester",
  subagent_type: "tester",
  mode: "bypassPermissions",
  prompt: "RED phase. Slice 1: ..."
)
```

The PreToolUse hook fires on this Agent call and injects context based on `subagent_type`.

### Subsequent dispatch to same teammate

```
SendMessage(to: "tester", message: "VALIDATE phase. Slice 1. Add edge cases.")
```

Caveat: SendMessage does NOT re-trigger the inject-context hook. Agents re-read
the project-root design doc and info.md each turn (per their role .md instructions).

Without Teams mode confirmation, keep execution in the main session. Dispatch a
single specialist role only when the current phase needs that role's context.

## Coexistence with Other Skills

Harness manages **orchestration** (which role, what order, what artifacts),
NOT technique. It coexists with other skills:

- harness defines: role boundaries, dispatch order, file protocol, state machine
- other skills inform: how to write a test, how to debug, how to refactor

If a teammate / role needs help with HOW to do its work (e.g. tester needs TDD
technique, developer needs language-specific patterns), it can invoke other
skills as appropriate.

**Conflict rule**: when another skill conflicts with harness flow (e.g. suggests
skipping TDD when user asked for harness-implement), defer to harness. The user
chose the harness on purpose.

## Project-Specific Conventions

Add team-specific guidelines to `.harness/spec/index.md` and reference from
manifests. Keep specs short and link from manifests rather than dumping
everything into every prompt.
"""


CLAUDE_MD_TEMPLATE = HARNESS_SECTION


def install_rtk(skip: bool, dry_run: bool) -> str:
    """Best-effort RTK auto-install. Returns a status word for caller to log.

    Status values:
      - "skipped":           --no-rtk flag set
      - "already_installed": rtk already on PATH
      - "would_install":     --check-deps mode, rtk missing, would attempt install
      - "would_skip":        --check-deps mode, rtk missing, no curl available
      - "installed":         curl install + `rtk init -g` succeeded
      - "install_failed":    curl ran but rtk still not on PATH
      - "needs_curl":        no curl available; user must install manually
    """
    if skip:
        return "skipped"
    if shutil.which("rtk"):
        return "already_installed"

    if not shutil.which("curl"):
        return "would_skip" if dry_run else "needs_curl"

    if dry_run:
        return "would_install"

    # Run the official install script.
    cmd = f"curl -fsSL {RTK_INSTALL_URL} | sh"
    try:
        subprocess.run(["sh", "-c", cmd], check=False, timeout=180)
    except (subprocess.SubprocessError, OSError):
        return "install_failed"

    if not shutil.which("rtk"):
        return "install_failed"

    # Hook into Claude Code (global PreToolUse hook on Bash tool).
    try:
        subprocess.run(["rtk", "init", "-g"], check=False, timeout=30)
    except (subprocess.SubprocessError, OSError):
        pass  # binary present is the main goal; init -g is icing

    return "installed"


def _caveman_present() -> bool:
    """Best-effort check for caveman presence.

    Caveman installs via the Claude Code plugin/skill system, which puts
    files under several possible paths depending on version. Check the most
    common candidates; if any matches, treat as installed.
    """
    home = Path.home()
    candidates = [
        home / ".claude" / "skills" / "caveman",
    ]
    for path in candidates:
        if path.is_dir():
            return True
    # Walk ~/.claude/plugins for any caveman directory (deeper plugin cache)
    plugins_dir = home / ".claude" / "plugins"
    if plugins_dir.is_dir():
        for sub in plugins_dir.rglob("caveman"):
            if sub.is_dir():
                return True
    return False


def install_caveman(skip: bool, dry_run: bool) -> str:
    """Best-effort Caveman auto-install via official curl|bash script.

    Status values: skipped / already_installed / would_install / would_skip /
    installed / install_failed / needs_curl / needs_bash.
    """
    if skip:
        return "skipped"
    if _caveman_present():
        return "already_installed"

    if not shutil.which("curl"):
        return "would_skip" if dry_run else "needs_curl"
    if not shutil.which("bash"):
        return "would_skip" if dry_run else "needs_bash"

    if dry_run:
        return "would_install"

    cmd = f"curl -fsSL {CAVEMAN_INSTALL_URL} | bash caveman"
    try:
        subprocess.run(["bash", "-c", cmd], check=False, timeout=180)
    except (subprocess.SubprocessError, OSError):
        return "install_failed"

    return "installed" if _caveman_present() else "install_failed"


def report_caveman_status(status: str) -> None:
    """Print a human-readable line summarizing Caveman install status."""
    messages = {
        "skipped":           "Caveman auto-install skipped (--no-caveman).",
        "already_installed": "Caveman already installed — no action needed.",
        "would_install":     "Caveman would be installed (--check-deps; not run).",
        "would_skip":        "Caveman missing AND curl/bash unavailable — would skip.",
        "installed":         "Caveman installed via official install script.",
        "install_failed":    "Caveman install attempted but verification failed; install manually:\n"
                             f"    curl -fsSL {CAVEMAN_INSTALL_URL} | bash caveman",
        "needs_curl":        "Caveman not installed and curl not found.\n"
                             "    Install curl first, or visit https://git.xiaojukeji.com/morganli/caveman",
        "needs_bash":        "Caveman not installed and bash not found.\n"
                             "    Install bash, or follow https://git.xiaojukeji.com/morganli/caveman manually",
    }
    print(f"  caveman: {messages.get(status, status)}")


def report_rtk_status(status: str) -> None:
    """Print a human-readable line summarizing RTK install status."""
    messages = {
        "skipped":           "RTK auto-install skipped (--no-rtk).",
        "already_installed": "RTK already installed — no action needed.",
        "would_install":     "RTK would be installed (--check-deps; not run).",
        "would_skip":        "RTK missing AND curl not available — would skip install.",
        "installed":         "RTK installed via curl + `rtk init -g`.",
        "install_failed":    "RTK install attempted but failed; install manually:\n"
                             f"    curl -fsSL {RTK_INSTALL_URL} | sh && rtk init -g",
        "needs_curl":        "RTK not installed and curl not found.\n"
                             "    Install curl first, or install RTK manually per https://github.com/rtk-ai/rtk",
    }
    print(f"  rtk: {messages.get(status, status)}")


def main():
    parser = argparse.ArgumentParser(description="Initialize lightweight agent harness")
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.cwd(),
        help="Target project directory (default: current directory)",
    )
    parser.add_argument(
        "--no-rtk",
        action="store_true",
        help="Skip RTK auto-install (CI / restricted networks)",
    )
    parser.add_argument(
        "--no-caveman",
        action="store_true",
        help="Skip Caveman auto-install (CI / restricted networks)",
    )
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="Dry-run: report what would be installed without doing it",
    )
    args = parser.parse_args()
    target = args.target.resolve()

    if args.check_deps:
        # Dry-run: just report status, don't write files
        rtk_status = install_rtk(skip=args.no_rtk, dry_run=True)
        caveman_status = install_caveman(skip=args.no_caveman, dry_run=True)
        print(f"Check-deps for harness target: {target}")
        report_rtk_status(rtk_status)
        report_caveman_status(caveman_status)
        return

    create_harness_skeleton(target)
    create_claude_hooks(target)
    create_codex_hooks(target)
    create_claude_agents(target)
    create_claude_commands(target)
    create_claude_skills(target)
    remove_managed_deepseek_skills()
    create_codex_skills()
    create_claude_md(target)
    create_agents_md(target)
    merge_settings(target)
    merge_codex_hooks(target)

    rtk_status = install_rtk(skip=args.no_rtk, dry_run=False)
    caveman_status = install_caveman(skip=args.no_caveman, dry_run=False)

    print(f"✓ Harness initialized in {target}")
    print(f"  .harness/  — scripts, workflow, verification config")
    print(f"  docs/tasks/ — requirement development task packages")
    print(f"  docs/standards/ — team engineering standards")
    print(f"  .claude/   — hooks, agents, commands, skills (merged)")
    print(f"  .codex/    — hooks (merged)")
    print(f"  ~/.codex/skills/ — Codex skills (created if missing)")
    print(f"  CLAUDE.md  — harness conventions (created or appended)")
    print(f"  AGENTS.md  — harness conventions (created or appended)")
    report_rtk_status(rtk_status)
    report_caveman_status(caveman_status)
    print("")
    print("下一步建议配置提交前检查:")
    print("  请配置 harness verify。先读取当前项目的构建和测试入口，给出 .harness/verify.json 推荐配置，等确认后再写入。")
    print("  已安装 skill: harness-configure-verify")


if __name__ == "__main__":
    main()
