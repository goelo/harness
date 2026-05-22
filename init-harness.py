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


def _is_harness_hook_entry(entry: dict) -> bool:
    """Check if a hook entry was created by this harness."""
    for hook in entry.get("hooks", []):
        cmd = hook.get("command", "")
        if "harness-" in cmd and ".claude/hooks/" in cmd:
            return True
    return False


def merge_settings(target: Path) -> None:
    """Merge harness hooks into existing .claude/settings.json."""
    settings_path = target / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.is_file():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})

    for event_name, harness_entries in HARNESS_HOOKS.items():
        existing = hooks.get(event_name, [])
        # Remove old harness entries (idempotent)
        existing = [e for e in existing if not _is_harness_hook_entry(e)]
        existing.extend(harness_entries)
        hooks[event_name] = existing

    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def create_harness_skeleton(target: Path) -> None:
    """Create .harness/ directory structure."""
    harness = target / ".harness"

    (harness / "tasks").mkdir(parents=True, exist_ok=True)
    (harness / "tasks" / "archive").mkdir(parents=True, exist_ok=True)
    (harness / "runtime" / "sessions").mkdir(parents=True, exist_ok=True)
    (harness / "spec").mkdir(parents=True, exist_ok=True)
    (harness / "scripts").mkdir(parents=True, exist_ok=True)

    _write_if_missing(harness / "workflow.md", WORKFLOW_MD)
    _write_if_missing(harness / "spec" / "index.md", SPEC_INDEX_MD)

    # Deploy real scripts from sibling harness_scripts/ when available
    src_scripts = Path(__file__).parent / "harness_scripts"
    script_files = {
        "task.py": TASK_PY_STUB,
        "team_cleanup.py": TEAM_CLEANUP_STUB,
    }
    for filename, stub in script_files.items():
        real = src_scripts / filename
        content = real.read_text(encoding="utf-8") if real.is_file() else stub
        target_file = harness / "scripts" / filename
        if not target_file.is_file():
            target_file.write_text(content, encoding="utf-8")

    # Project-root .gitignore — append harness/python/node defaults if absent
    create_gitignore(target)


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


def create_claude_skills(target: Path) -> None:
    """Write skill files (v1.5+)."""
    harness_skill_dir = target / ".claude" / "skills" / "harness-implement"
    harness_skill_dir.mkdir(parents=True, exist_ok=True)
    _write_if_missing(harness_skill_dir / "SKILL.md", SKILL_HARNESS_IMPLEMENT)

    grill_me_skill_dir = target / ".claude" / "skills" / "grill-me"
    grill_me_skill_dir.mkdir(parents=True, exist_ok=True)
    _write_if_missing(grill_me_skill_dir / "SKILL.md", SKILL_GRILL_ME)


HARNESS_SECTION_MARKER = "# Agent Harness"


def create_claude_md(target: Path) -> None:
    """Create or append the harness section to CLAUDE.md.

    - No CLAUDE.md → create with full harness template
    - Existing CLAUDE.md without harness section → append harness section
    - Existing CLAUDE.md with harness section → idempotent (no change)
    """
    claude_md = target / "CLAUDE.md"

    if not claude_md.is_file():
        claude_md.write_text(CLAUDE_MD_TEMPLATE, encoding="utf-8")
        return

    existing = claude_md.read_text(encoding="utf-8")
    if HARNESS_SECTION_MARKER in existing:
        return  # already has the section, leave it alone

    # Append harness section after user content
    separator = "" if existing.endswith("\n") else "\n"
    claude_md.write_text(
        existing + separator + "\n" + HARNESS_SECTION + "\n",
        encoding="utf-8",
    )


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
[/workflow-state:no_task]

[workflow-state:planning]
Task is in planning. Required steps in this exact order:

  1. Design source — project root (NO copy):
     a. Confirm a design document exists at project root: `design.md`,
        `spec.md`, or `requirements.md` (in that priority order). Hooks read
        it directly — do NOT copy it into the task dir.
     b. If missing or too vague, work with the user (or invoke grill-me) to
        produce one. Confirm before proceeding.

  2. Optional: gather external info via `research/*.md` (architect can do this).

  3. **Curate 3 manifests** (Phase 1.3 — required before any agent dispatch):
     - `context.architect.jsonl`  — at least .harness/spec/index.md
     - `context.developer.jsonl`  — spec + relevant research
     - `context.tester.jsonl`     — spec + testing conventions
     Each file MUST have at least one row with a `file` field
     (not just the `_example` seed row).

  4. Dispatch `architect` agent → writes `info.md` (now has spec via manifest).

  5. (Optional) Refine manifests if architect's design uncovers needs not yet in manifests.

  6. Run: `python3 .harness/scripts/task.py start <task-dir>`.
     This command WILL FAIL if manifests are still seed-only.

WHY this order: architect itself reads context.architect.jsonl to see team
specs while designing. If you dispatch architect before curating, it designs
without team conventions. Manifest curation must precede ALL sub-agent dispatch.
[/workflow-state:planning]

[workflow-state:in_progress]
Task is active. **TDD is the default workflow** (red-green-refactor) with 3 teammates.
**Sub-agents are dispatched via Claude Agent Teams** (not plain Task tool).

## Bootstrap once per task (right after task.py start)

  TeamCreate(team_name: "<task-slug>", description: "<task title>")

This creates a shared TaskList visible to all teammates. Main session = team lead.

## Permission mode for all sub-agent calls

If main session was started with `--dangerously-skip-permissions` (autonomous mode),
ALL Agent / SendMessage calls MUST pass `mode: "bypassPermissions"` so sub-agents
don't stall on approval prompts.

## Spawn 3 execution teammates ONCE

Right after TeamCreate, spawn 3 persistent teammates (once for the whole task):

  Agent(team_name, name: "architect", subagent_type: "architect", mode: "bypassPermissions", prompt: "Stand by ...")
  Agent(team_name, name: "developer", subagent_type: "developer", mode: "bypassPermissions", prompt: "Stand by ...")
  Agent(team_name, name: "tester",    subagent_type: "tester",    mode: "bypassPermissions", prompt: "Stand by ...")

The PreToolUse hook fires on each Agent call → injects PRD + info.md + role
manifest into each teammate. Context persists across all subsequent SendMessage.

## Per-slice TDD dispatch via SendMessage

For each implementation slice, send messages in TDD order, waiting for idle
between each:

  1. SendMessage(to: "tester",    message: "RED phase. Slice N: <X>. Write failing tests.")
  2. SendMessage(to: "developer", message: "GREEN phase. Slice N. Make tester's tests pass.")
  3. SendMessage(to: "architect", message: "REVIEW phase. Slice N. Refactor + verify design conformance.")
  4. SendMessage(to: "tester",    message: "VALIDATE phase. Slice N. Add edge case tests.")

After all 4 idle: main session commits.

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

HOOK_INJECT_CONTEXT = """\
#!/usr/bin/env python3
\"\"\"PreToolUse hook — injects context into sub-agents. Placeholder.\"\"\"
import json, sys
sys.exit(0)
"""

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

## info.md structure (in order)

1. **Module breakdown** — files/packages, dependency direction, naming
2. **Interface contracts** (testable — see below)
3. **Slice order** — which slice first, what each unlocks
4. **Risks / trade-offs**

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
  Use when the user asks to implement a feature from a design / spec / requirements
  markdown document and the project has a harness setup (.harness/ + .claude/hooks).
  Triggers: "按照 design.md 开发", "implement design.md", "按照详细设计文档开发",
  "用 harness 实现 xxx.md", "follow the harness flow", "走 harness 流程", or any
  phrasing pointing the AI at a markdown spec file as the source of truth for
  implementation work.
---

# Harness Implement

Walks the AI through the full v1.6 harness TDD + Teams flow with 3 agents:
read user's design doc → architect produces info.md → per-slice TDD cycle (tester
RED → developer GREEN → architect REVIEW → tester VALIDATE) → archive.

## When to Use

User points at a design/spec/requirements markdown file (`design.md`, `spec.md`,
`requirements.md`, or similar) and asks for implementation. The project has
`.harness/` directory and Claude Code hooks installed.

**Do NOT use** when:
- User wants exploration / brainstorming (no spec yet)
- User wants a trivial change (typo fix, rename) — main session edits directly
- No `.harness/` in project root (this isn't a harness project)

## Core Principle

The user's design doc IS the PRD. Do not rewrite it. Architect's job is
**technical decomposition into testable contracts**, not requirements authoring.

## Flow Overview

| Step | Action | Checkpoint? |
|------|--------|-------------|
| 1 | Confirm design doc at project root (design.md / spec.md / requirements.md). Hooks read it directly — no copy. | — |
| 2 | `task.py create "<title>"` | — |
| 3 | Confirm design doc with user (or invoke grill-me to fill gaps) | **YES — wait for confirm** |
| 4 | Curate 3 manifests (architect/developer/tester) | — |
| 5 | Dispatch `architect` → produces `info.md` | — |
| 6 | Verify info.md has testable contracts + slice plan | — |
| 7 | Sync slice plan with user | **YES — wait for confirm** |
| 8 | `task.py start <task-dir>` | — |
| 9 | `TeamCreate(team_name: "<task-slug>", ...)` | — |
| 9b | Spawn 3 persistent execution teammates (architect/developer/tester) | — |
| 10 | Per slice: SendMessage tester(RED) → developer → architect(REVIEW) → tester(VALIDATE) | per-slice **YES** |
| 11 | Main session commits the slice | — |
| 12 | Repeat 10-11 for remaining slices (SAME teammates, no re-spawn) | — |
| 13 | TeamDelete + team_cleanup.py + `task.py archive <task-dir>` | — |

## Step Templates

### 1-3. Bootstrap

```bash
# Verify design doc exists at project root (one of these).
ls design.md spec.md requirements.md 2>/dev/null

# Create task. Hooks will inject the project-root design doc directly —
# no copy into the task dir.
python3 .harness/scripts/task.py create "<short title from design doc>"
```

### 5. Curate manifests (Phase 1.3)

Each manifest must have ≥1 row with `file` field (not just `_example`).
Minimal viable curation:

```jsonl
# context.architect.jsonl
{"file": ".harness/spec/index.md", "reason": "team conventions for design"}

# context.developer.jsonl
{"file": ".harness/spec/index.md", "reason": "team coding conventions"}

# context.tester.jsonl
{"file": ".harness/spec/index.md", "reason": "test conventions"}
```

**Tool tip**: the 3 manifests are seed files created by `task.py create`. They
already exist with an `_example` row. To add real entries, use `Edit` (with
`replace_all` if needed) or first `Read` then `Write` — naked `Write` against
an existing file is rejected.

### 6. Dispatch architect (one-shot, before team)

```
Agent(
  name: "architect",
  subagent_type: "architect",
  mode: "bypassPermissions",
  prompt: "Read the project-root design doc and produce info.md with:
           (1) module breakdown, (2) testable interface contracts,
           (3) slice order, (4) risks."
)
```

### 9-10b. Activate + bootstrap team

```bash
python3 .harness/scripts/task.py start <task-dir>
```

```
TeamCreate(team_name: "<task-slug>", description: "<task title>")

Agent(team_name: "<slug>", name: "architect", subagent_type: "architect",
      mode: "bypassPermissions", prompt: "Stand by for REVIEW phases per slice.")

Agent(team_name: "<slug>", name: "developer", subagent_type: "developer",
      mode: "bypassPermissions", prompt: "Stand by for GREEN phases per slice.")

Agent(team_name: "<slug>", name: "tester", subagent_type: "tester",
      mode: "bypassPermissions", prompt: "Stand by for RED and VALIDATE phases per slice.")
```

**Important — TaskCreate after TeamCreate**: if you use TaskCreate to track slices,
do it AFTER TeamCreate so tasks live in the team's shared TaskList (not orphaned
in main session context).

### 11. Per-slice TDD cycle (SendMessage)

For slice N:

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

**Before commit**: invoke `superpowers:verification-before-completion` if available,
or at minimum run the project's test suite manually and confirm GREEN. Don't claim
slice done without verification evidence.

After all 4 idle, summarize to user, then main session runs `git add` + `git commit`.

### 14. Cleanup

`TeamDelete` only removes the team config + worktree — **the actual sub-agent
Claude processes survive**. Use the harness cleanup script to kill them properly:

```
TeamDelete()
```

```bash
python3 .harness/scripts/team_cleanup.py <task-slug>
```

```bash
python3 .harness/scripts/task.py archive <task-dir>
```

## Required Behaviors

- **Wait at user checkpoints** (PRD confirm, slice plan confirm, per-slice review)
- **Pass `mode: "bypassPermissions"`** on EVERY Agent call
- **Spawn 3 execution teammates ONCE** at execute-phase start (step 10b). Reuse
  via SendMessage for every slice.
- **Sub-agents must NOT commit** — main session owns git
- **Architect re-engagement**: if tester or developer flags design deviation, send
  architect a REVIEW message; it may update info.md and SendMessage affected
  teammates "info.md updated, please re-read".
- **TeamDelete + team_cleanup.py at archive** — single command kills all teammates

## Common Pitfalls

| Mistake | Fix |
|---------|-----|
| Rewriting user's design doc | Don't. Hooks read it directly from project root — the doc IS the PRD. |
| Skipping manifest curation | task.py start gate will reject — curate first |
| Architect produces vague info.md | Reject and re-dispatch with explicit "testable contracts" requirement |
| Sub-agent runs git commit | Stop it. Only main session commits. |
| Forgetting `mode: "bypassPermissions"` | Sub-agent stalls on approval — pass mode every time |
| Skipping tester(RED) | TDD violated. Only skip on trivial changes with explicit announcement. |
| Trusting `TeamDelete` to kill processes | It doesn't. Run team_cleanup.py after. |
"""


SKILL_GRILL_ME = """\
---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when user wants to stress-test a plan, get grilled on their design, or mentions "grill me".
---

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time.

If a question can be answered by exploring the codebase, explore the codebase instead.
"""


HARNESS_SECTION = """\
# Agent Harness

This project uses a 3-role agent harness for stateful AI collaboration.
Hooks at `.claude/hooks/harness-*.py` inject context every session/turn.

## Workflow Phases

| Phase | Status | Sequence (order matters) |
| --- | --- | --- |
| Plan | `planning` | confirm project-root design doc → (optional) research → **curate 3 manifests** → architect writes info.md → `task.py start` |
| Execute | `in_progress` | **TDD cycle**: tester(RED) → developer(GREEN) → architect(REVIEW/REFACTOR) → tester(VALIDATE) → main session commits |
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

## Agent Roles (3 — dispatched via Task/Agent tool)

| Role | TDD Phase | Reads | Writes |
| --- | --- | --- | --- |
| `architect` | (Plan + REVIEW + RE-ENGAGE) | research/, project-root design, code, manifest | `info.md`, refactored code |
| `developer` | GREEN | failing tests, project-root design, info.md, manifest | minimum code to pass tests |
| `tester` | RED + VALIDATE | project-root design, info.md, manifest | failing tests + edge case tests |

**No sub-agent commits.** Main session commits after the slice's TDD cycle is GREEN.
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

Sub-agents are dispatched as Team teammates, not plain Task calls. This unlocks:
- **Persistence**: teammate retains context across multiple turns
- **Peer DM**: teammates can SendMessage each other
- **Shared TaskList**: all teammates see the team's tasks

### Bootstrap (right after task.py start)

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
    create_claude_agents(target)
    create_claude_commands(target)
    create_claude_skills(target)
    create_claude_md(target)
    merge_settings(target)

    rtk_status = install_rtk(skip=args.no_rtk, dry_run=False)
    caveman_status = install_caveman(skip=args.no_caveman, dry_run=False)

    print(f"✓ Harness initialized in {target}")
    print(f"  .harness/  — task state, workflow, spec")
    print(f"  .claude/   — hooks, agents, commands (merged)")
    print(f"  CLAUDE.md  — harness conventions (created or appended)")
    report_rtk_status(rtk_status)
    report_caveman_status(caveman_status)


if __name__ == "__main__":
    main()
