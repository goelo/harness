#!/usr/bin/env python3
"""PreToolUse hook: inject phase-safe role context."""

from __future__ import annotations

import json
import os
import sys
import fnmatch
from pathlib import Path

LOCAL_CONTEXT_KEY = "local"
KNOWN_ROLES = ("architect", "developer", "tester")
PHASE_ROLE = {
    "doc-plan": "architect",
    "red": "tester",
    "green": "developer",
    "review": "architect",
    "validate": "tester",
}
ROLE_TOOLS = ("Task", "Agent", "TaskCreate", "TeamCreate", "spawn_agent", "followup_task")
EDIT_TOOLS = ("Write", "Edit", "MultiEdit")
TEST_PATH_PARTS = ("/test/", "/tests/", "_test.", ".test.", ".spec.")
CODE_EXTENSIONS = (
    ".go",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".kt",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
)
CONTROLLED_SUFFIXES = (
    "task.json",
    "clarification.jsonl",
    "clarification.md",
    "test-result.red.json",
    "test-result.green.json",
    "review-result.json",
    "verify-result.json",
)
DOC_PLAN_TASK_FILES = (
    "implementation-plan.md",
    "scope.json",
    "context.architect.jsonl",
    "context.developer.jsonl",
    "context.tester.jsonl",
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


def normalize_target_path(root: Path, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()


def edit_target(tool_input: dict) -> str | None:
    for key in ("file_path", "path", "target_file"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def controlled_edit_target(tool_input: dict) -> str | None:
    target = edit_target(tool_input)
    if target:
        normalized = target.replace("\\", "/")
        if "/docs/tasks/" in normalized or normalized.startswith("docs/tasks/"):
            if any(normalized.endswith(suffix) for suffix in CONTROLLED_SUFFIXES):
                return target
    return None


def is_test_path(path: str) -> bool:
    normalized_path = path.replace("\\", "/")
    normalized = f"/{normalized_path}"
    return any(part in normalized for part in TEST_PATH_PARTS)


def is_code_path(path: str) -> bool:
    return Path(path).suffix in CODE_EXTENSIONS


def matches_pattern(path: str, pattern: str) -> bool:
    normalized = pattern.strip()
    if normalized.endswith("/"):
        normalized = f"{normalized}**"
    plain = normalized.rstrip("/")
    if not any(ch in normalized for ch in "*?[]"):
        return path == plain or path.startswith(f"{plain}/")
    return fnmatch.fnmatchcase(path, normalized)


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(matches_pattern(path, pattern) for pattern in patterns)


def scope_allowed(task_dir: Path) -> list[str]:
    path = task_dir / "scope.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    allowed = data.get("allowed")
    if not isinstance(allowed, list):
        return []
    return [item for item in allowed if isinstance(item, str) and item.strip()]


def is_doc_plan_artifact(path: str, task_dir: Path, root: Path) -> bool:
    try:
        rel_task = task_dir.relative_to(root).as_posix()
    except ValueError:
        return False
    if not path.startswith(f"{rel_task}/"):
        return False
    name = path.removeprefix(f"{rel_task}/")
    return name in DOC_PLAN_TASK_FILES


def phase_edit_violation(root: Path, task_dir: Path | None, phase: str | None, target: str) -> str | None:
    rel = normalize_target_path(root, target)
    if task_dir is None:
        if is_code_path(rel):
            return f"没有 active task，禁止修改业务代码 {rel}。请先进入 requirement-confirmation 完成需求确认。"
        return None
    if phase == "clarify":
        if is_code_path(rel):
            return f"当前阶段 clarify 禁止修改业务代码 {rel}。请先完成需求确认并推进到 doc-plan。"
        return None
    if phase == "doc-plan":
        if is_doc_plan_artifact(rel, task_dir, root):
            return None
        if is_code_path(rel) or is_test_path(rel):
            return f"当前阶段 doc-plan 禁止修改业务代码 {rel}。只能编写 implementation-plan.md、scope.json 和 context.*.jsonl。"
        return None
    if phase in ("red", "validate"):
        if is_code_path(rel) and not is_test_path(rel):
            return f"当前阶段 {phase} 禁止修改业务实现文件 {rel}。该阶段只允许测试相关变更。"
        return None
    if phase == "green":
        if is_test_path(rel):
            return f"当前阶段 green 禁止修改测试文件 {rel}。请回到 red 或 validate 阶段处理测试。"
        allowed = scope_allowed(task_dir)
        if allowed and not matches_any(rel, allowed):
            return f"文件 {rel} 不在 scope.json.allowed 范围内，禁止修改。"
    if phase == "review":
        allowed = scope_allowed(task_dir)
        if allowed and not matches_any(rel, allowed):
            return f"文件 {rel} 不在 scope.json.allowed 范围内，禁止修改。"
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
    tool_name = data.get("tool_name", "")
    target = controlled_edit_target(tool_input)
    if target:
        return emit_block(f"受控文件 {target} 只能通过 harness 内部工具生成，禁止手工编辑。")

    root = find_project_root(Path(data.get("cwd") or "."))
    if root is None:
        return 0
    task_dir = get_active_task_dir(root, data)
    phase = task_phase(task_dir) if task_dir else None

    if tool_name in EDIT_TOOLS:
        target = edit_target(tool_input)
        if target:
            violation = phase_edit_violation(root, task_dir, phase, target)
            if violation:
                return emit_block(violation)
        return 0

    if tool_name in ROLE_TOOLS and task_dir is None:
        return emit_block(
            "没有 active task，禁止启动开发子任务。请先使用 requirement-confirmation 完成需求确认，"
            "确认后再使用 python3 .harness/scripts/task.py create \"<任务名>\" 创建任务。"
        )

    role = infer_role(tool_input)
    if role not in KNOWN_ROLES:
        if tool_name in ROLE_TOOLS and phase in PHASE_ROLE:
            expected = PHASE_ROLE[phase]
            return emit_block(f"当前阶段 {phase} 必须调用 {expected}，禁止使用未声明角色的子任务绕过 harness。")
        return 0

    if task_dir is None:
        return 0

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
