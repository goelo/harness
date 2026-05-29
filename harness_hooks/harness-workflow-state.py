#!/usr/bin/env python3
"""UserPromptSubmit hook: emit phase-aware workflow breadcrumb."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

LOCAL_CONTEXT_KEY = "local"
TAG_RE = re.compile(
    r"\[workflow-phase:([A-Za-z0-9_-]+)\]\s*\n(.*?)\n\s*\[/workflow-phase:\1\]",
    re.DOTALL,
)


def find_project_root(start: Path) -> Path | None:
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
    return {m.group(1): m.group(2).strip() for m in TAG_RE.finditer(content)}


def resolve_session_key(data: dict) -> str | None:
    for key in ("session_id", "sessionId"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    env_key = os.environ.get("HARNESS_CONTEXT_ID")
    return env_key or None


def task_info_from_ref(root: Path, task_ref: str) -> dict | None:
    task_dir = root / task_ref
    if not task_dir.is_dir():
        return None
    task_json = task_dir / "task.json"
    if not task_json.is_file():
        return {"path": task_ref, "status": "unknown", "phase": "unknown"}
    data = json.loads(task_json.read_text(encoding="utf-8"))
    return {
        "path": task_ref,
        "title": data.get("title", task_dir.name),
        "status": data.get("status", "unknown"),
        "phase": data.get("phase", data.get("status", "unknown")),
    }


def get_active_task(root: Path, data: dict) -> dict | None:
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
            task_info = task_info_from_ref(root, task_ref)
            if task_info:
                return task_info

    files = list(sessions_dir.glob("*.json")) if sessions_dir.is_dir() else []
    if len(files) == 1:
        session = json.loads(files[0].read_text(encoding="utf-8"))
        task_ref = session.get("current_task")
        if task_ref:
            return task_info_from_ref(root, task_ref)
    return unique_in_progress_task(root)


def unique_in_progress_task(root: Path) -> dict | None:
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
            matches.append(f"docs/tasks/{task_dir.name}")
    return task_info_from_ref(root, matches[0]) if len(matches) == 1 else None


def build_breadcrumb(task: dict | None, body: str) -> str:
    if task:
        header = f"Task: {task['path']} ({task['status']})\nPhase: {task['phase']}"
    else:
        header = "Status: no_task\nPhase: no_task"
    return f"<workflow-state>\n{header}\n{body}\n</workflow-state>"


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}
    root = find_project_root(Path(data.get("cwd") or "."))
    if root is None:
        return 0

    breadcrumbs = load_breadcrumbs(root)
    task = get_active_task(root, data)
    phase = task["phase"] if task else "no_task"
    body = breadcrumbs.get(phase, "Refer to workflow.md for current phase.")
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": build_breadcrumb(task, body),
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
