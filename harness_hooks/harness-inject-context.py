#!/usr/bin/env python3
"""PreToolUse hook — injects task context into sub-agent prompts.

Triggered when Claude dispatches a Task/Agent with subagent_type matching
a known role.

Three roles (v1.7):
  architect — designs (info.md), reviews diff vs design, refactors when needed.
              Reads task docs + research/*.md + context.architect.jsonl
  developer — implements GREEN code from failing tests.
              Reads task docs + info.md + context.developer.jsonl
  tester    — writes failing tests (RED) and edge cases (VALIDATE).
              Reads task docs + info.md + context.tester.jsonl

Design source: the active task package's proposal.md / design.md / tasks.md
is read first. The project root's design.md / spec.md / requirements.md is
kept as a compatibility fallback for older task packages.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# All three roles follow the standard pattern:
#   task package docs + info.md + context.<role>.jsonl manifest
# (Architect additionally gets research/*.md auto-included.)
STANDARD_ROLES = ("architect", "developer", "tester")
KNOWN_ROLES = STANDARD_ROLES

# Active task package docs, in reading order.
TASK_CONTEXT_FILENAMES = ("proposal.md", "design.md", "tasks.md")

# Project-root design document fallback, in priority order.
ROOT_DESIGN_FILENAMES = ("design.md", "spec.md", "requirements.md")


def find_project_design(root: Path) -> Path | None:
    """Find the project-root design document, by fallback priority."""
    for name in ROOT_DESIGN_FILENAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def read_task_context_docs(task_dir: Path) -> list[tuple[str, str]]:
    """Read task package context docs in canonical order."""
    results = []
    for name in TASK_CONTEXT_FILENAMES:
        content = read_file_safe(task_dir / name)
        if content:
            results.append((name, content))
    return results


def read_design_context(root: Path, task_dir: Path) -> list[tuple[str, str]]:
    """Prefer active task package docs; fall back to project-root design doc."""
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
    """Read file contents referenced by JSONL manifest. Skip seed rows."""
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
    """Read all .md files in a directory (non-recursive)."""
    if not directory.is_dir():
        return []
    results = []
    for f in sorted(directory.glob("*.md")):
        content = read_file_safe(f)
        if content:
            results.append((f.name, content))
    return results


def build_standard_role_context(root: Path, task_dir: Path, role: str) -> str:
    """Standard pattern: jsonl manifest + task docs + info.md."""
    parts = []

    # 1. JSONL manifest files
    manifest = task_dir / f"context.{role}.jsonl"
    for file_path, content in read_jsonl_context(root, manifest):
        parts.append(f"=== {file_path} ===\n{content}")

    # 2. Active task docs, with root design fallback for older task packages
    for filename, content in read_design_context(root, task_dir):
        parts.append(f"=== {filename} ===\n{content}")

    # 3. info.md (when exists — architect writes it, others read it)
    info = read_file_safe(task_dir / "info.md")
    if info:
        parts.append(f"=== info.md ===\n{info}")

    # 4. For architect: also include all research/*.md files
    if role == "architect":
        for filename, content in read_directory_md_files(task_dir / "research"):
            parts.append(f"=== research/{filename} ===\n{content}")

    return "\n\n".join(parts)


def infer_role(tool_input: dict) -> str:
    """Infer harness role from Claude or Codex tool input."""
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
    """Return the prompt-like field used by the current agent tool."""
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

    # All three standard roles require an active task
    task_dir = get_active_task_dir(root, data)
    if task_dir is None:
        return 0
    context = build_standard_role_context(root, task_dir, role)

    if not context:
        return 0

    field = prompt_field(tool_input)
    original_prompt = tool_input.get(field, "")
    new_prompt = f"## Injected Context\n\n{context}\n\n---\n\n## Task\n\n{original_prompt}"

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
