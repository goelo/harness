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
        parts.append(f"=== docs/standards/index.md ===\n{standards}")

    clarification = read_file_safe(task_dir / "clarification.md")
    if clarification:
        parts.append(f"=== clarification.md ===\n{clarification}")

    plan = read_file_safe(task_dir / "implementation-plan.md")
    if plan:
        parts.append(f"=== implementation-plan.md ===\n{plan}")

    for file_path, content in read_jsonl_context(root, task_dir / f"context.{role}.jsonl"):
        parts.append(f"=== {file_path} ===\n{content}")

    return "\n\n".join(parts)


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
        normalized = value.replace("\\", "/")
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
    updated = {**tool_input, field: f"## Injected Context\n\n{context}\n\n---\n\n## Task\n\n{original}"}
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
