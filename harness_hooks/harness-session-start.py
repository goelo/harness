#!/usr/bin/env python3
"""SessionStart hook: inject current harness task summary."""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

LOCAL_CONTEXT_KEY = "local"


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


def export_context_id_to_env_file(context_key: str | None) -> None:
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


def task_info_from_ref(root: Path, task_ref: str) -> dict | None:
    task_dir = root / task_ref
    if not task_dir.is_dir():
        return None
    task_json = task_dir / "task.json"
    if not task_json.is_file():
        return {"title": task_dir.name, "path": task_ref, "status": "unknown", "phase": "unknown"}
    data = json.loads(task_json.read_text(encoding="utf-8"))
    return {
        "title": data.get("title", task_dir.name),
        "path": task_ref,
        "status": data.get("status", "unknown"),
        "phase": data.get("phase", "unknown"),
        "executionMode": data.get("executionMode", "unknown"),
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
            task = task_info_from_ref(root, task_ref)
            if task:
                return task
    return unique_in_progress_task(root)


def unique_in_progress_task(root: Path) -> dict | None:
    tasks_dir = root / "docs" / "tasks"
    if not tasks_dir.is_dir():
        return None
    refs = []
    for task_dir in tasks_dir.iterdir():
        if not task_dir.is_dir() or task_dir.name == "archive":
            continue
        task_json = task_dir / "task.json"
        if not task_json.is_file():
            continue
        data = json.loads(task_json.read_text(encoding="utf-8"))
        if data.get("status") == "in_progress":
            refs.append(f"docs/tasks/{task_dir.name}")
    return task_info_from_ref(root, refs[0]) if len(refs) == 1 else None


def build_context(task: dict | None) -> str:
    parts = []
    if task:
        parts.append(
            f"Active task: {task['title']} ({task['status']})\n"
            f"Phase: {task['phase']}\n"
            f"Execution mode: {task['executionMode']}\n"
            f"Path: {task['path']}"
        )
    else:
        parts.append("No active task.")

    parts.append(
        "\nNatural language entries:\n"
        "- 按 design.md 开发\n"
        "- 继续需求开发\n"
        "- 查看当前需求开发状态\n"
        "- 归档当前任务"
    )
    parts.append(
        "\nHarness roles:\n"
        "- requirement-confirmation: confirm intent, acceptance criteria, and boundaries\n"
        "- requirement-development: orchestrate phase progression\n"
        "- architect: plan and review\n"
        "- tester: RED and validate\n"
        "- developer: GREEN implementation"
    )
    return "\n".join(parts)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}
    root = find_project_root(Path(data.get("cwd") or "."))
    if root is None:
        return 0
    export_context_id_to_env_file(resolve_session_key(data))
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": build_context(get_active_task(root, data)),
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
