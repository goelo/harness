#!/usr/bin/env python3
"""UserPromptSubmit hook — emits <workflow-state> breadcrumb each turn.

Reads active task from session pointer, resolves status, and parses
[workflow-state:STATUS] blocks from workflow.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

LOCAL_CONTEXT_KEY = "local"

_TAG_RE = re.compile(
    r"\[workflow-state:([A-Za-z0-9_-]+)\]\s*\n(.*?)\n\s*\[/workflow-state:\1\]",
    re.DOTALL,
)


def find_harness_root(start: Path) -> Path | None:
    cur = start.resolve()
    while cur != cur.parent:
        if (cur / ".harness").is_dir():
            return cur
        cur = cur.parent
    return None


def load_breadcrumbs(root: Path) -> dict[str, str]:
    workflow = root / ".harness" / "workflow.md"
    if not workflow.is_file():
        return {}
    content = workflow.read_text(encoding="utf-8")
    return {m.group(1): m.group(2).strip() for m in _TAG_RE.finditer(content)}


def resolve_session_key(data: dict) -> str | None:
    for key in ("session_id", "sessionId"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    env_key = os.environ.get("HARNESS_CONTEXT_ID")
    if env_key:
        return env_key
    return None


def get_active_task(root: Path, data: dict) -> tuple[str | None, str | None]:
    """Return (task_path, status) or (None, None)."""
    sessions_dir = root / ".harness" / "runtime" / "sessions"
    if not sessions_dir.is_dir():
        return None, None

    # Try explicit session key
    key = resolve_session_key(data)
    if key:
        session_file = sessions_dir / f"{key}.json"
        if session_file.is_file():
            session = json.loads(session_file.read_text(encoding="utf-8"))
            task_ref = session.get("current_task")
            if task_ref:
                return _resolve_task_status(root, task_ref)

    local_session = sessions_dir / f"{LOCAL_CONTEXT_KEY}.json"
    if local_session.is_file():
        session = json.loads(local_session.read_text(encoding="utf-8"))
        task_ref = session.get("current_task")
        if task_ref:
            return _resolve_task_status(root, task_ref)

    # Fallback: if exactly one session file exists
    files = list(sessions_dir.glob("*.json"))
    if len(files) == 1:
        session = json.loads(files[0].read_text(encoding="utf-8"))
        task_ref = session.get("current_task")
        if task_ref:
            return _resolve_task_status(root, task_ref)

    unique_task = _unique_in_progress_task(root)
    if unique_task:
        return _resolve_task_status(root, unique_task)

    return None, None


def _resolve_task_status(root: Path, task_ref: str) -> tuple[str | None, str | None]:
    task_dir = root / task_ref
    if not task_dir.is_dir():
        return None, None
    task_json = task_dir / "task.json"
    if not task_json.is_file():
        return task_ref, "unknown"
    data = json.loads(task_json.read_text(encoding="utf-8"))
    return task_ref, data.get("status", "unknown")


def _unique_in_progress_task(root: Path) -> str | None:
    tasks_dir = root / ".harness" / "tasks"
    if not tasks_dir.is_dir():
        return None
    candidates = []
    for task_dir in tasks_dir.iterdir():
        if not task_dir.is_dir() or task_dir.name == "archive":
            continue
        task_json = task_dir / "task.json"
        if not task_json.is_file():
            continue
        try:
            data = json.loads(task_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") == "in_progress":
            candidates.append(f".harness/tasks/{task_dir.name}")
    return candidates[0] if len(candidates) == 1 else None


def build_breadcrumb(task_ref: str | None, status: str, body: str) -> str:
    if task_ref:
        header = f"Task: {task_ref} ({status})"
    else:
        header = f"Status: {status}"
    return f"<workflow-state>\n{header}\n{body}\n</workflow-state>"


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}

    cwd = data.get("cwd") or "."
    root = find_harness_root(Path(cwd))
    if root is None:
        return 0

    templates = load_breadcrumbs(root)
    task_ref, status = get_active_task(root, data)

    if not task_ref:
        status = "no_task"

    body = templates.get(status, "Refer to workflow.md for current step.")
    breadcrumb = build_breadcrumb(task_ref, status, body)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": breadcrumb,
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
