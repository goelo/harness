#!/usr/bin/env python3
"""SessionStart hook — injects active task, status, commands, and role list.

Lightweight version: no spec indexes, no workflow text dump, no marketing banner.

Also exports HARNESS_CONTEXT_ID to CLAUDE_ENV_FILE so that subsequent Bash tool
invocations (e.g. `python3 .harness/scripts/task.py current`) can resolve the
session pointer.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path


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


def export_context_id_to_env_file(context_key: str | None) -> None:
    """Append `export HARNESS_CONTEXT_ID=...` to CLAUDE_ENV_FILE.

    Without this, Bash tool invocations from the same Claude Code session
    (e.g. `task.py current`) don't see the session id and fail.
    """
    if not context_key:
        return
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    try:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write(f"export HARNESS_CONTEXT_ID={shlex.quote(context_key)}\n")
    except OSError:
        pass


def get_active_task_info(root: Path, data: dict) -> dict | None:
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
    if not task_dir.is_dir():
        return None

    task_json = task_dir / "task.json"
    if not task_json.is_file():
        return {"title": task_dir.name, "status": "unknown", "path": task_ref}

    task_data = json.loads(task_json.read_text(encoding="utf-8"))
    return {
        "title": task_data.get("title", task_dir.name),
        "status": task_data.get("status", "unknown"),
        "path": task_ref,
    }


def build_context(root: Path, task_info: dict | None) -> str:
    parts = []

    if task_info:
        parts.append(
            f"Active task: {task_info['title']} ({task_info['status']})\n"
            f"Path: {task_info['path']}"
        )
    else:
        parts.append("No active task.")

    parts.append(
        "\nAvailable commands:\n"
        "- /harness:continue — check current state and next steps\n"
        "- /harness:finish — verify clean state, archive task, write summary"
    )

    parts.append(
        "\nAgent roles:\n"
        "- research  — search and persist findings to research/*.md\n"
        "- architect — design decisions, writes info.md (Plan phase)\n"
        "- developer — implement features (no commit)\n"
        "- reviewer  — code review and self-fix on diff (no commit)\n"
        "- qa        — write tests, edge cases, quality (no commit)"
    )

    return "\n".join(parts)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}

    cwd = data.get("cwd") or "."
    root = find_harness_root(Path(cwd))
    if root is None:
        return 0

    # Export session id so Bash tool can run task.py with session identity
    export_context_id_to_env_file(resolve_session_key(data))

    task_info = get_active_task_info(root, data)
    context = build_context(root, task_info)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
