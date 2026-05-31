#!/usr/bin/env python3
"""Build role-specific harness context for runtimes without hook support."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STANDARD_ROLES = ("architect", "developer", "tester")


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    while current != current.parent:
        if (current / ".harness").is_dir():
            return current
        current = current.parent
    print("Error: .harness/ directory not found", file=sys.stderr)
    sys.exit(1)


def resolve_task_dir(root: Path, task: str) -> Path:
    task_path = Path(task)
    if task_path.is_absolute():
        candidate = task_path
    elif task.startswith("docs/tasks/"):
        candidate = root / task_path
    else:
        candidate = root / "docs" / "tasks" / task
    if not candidate.is_dir():
        print(f"Error: task directory not found: {task}", file=sys.stderr)
        sys.exit(1)
    return candidate


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build harness role context")
    parser.add_argument("role", choices=STANDARD_ROLES)
    parser.add_argument("--task", required=True, help="Task dir name or docs/tasks/<dir>")
    parser.add_argument("--prompt", default="", help="Optional task prompt appended after context")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = find_project_root(Path.cwd())
    task_dir = resolve_task_dir(root, args.task)
    context = build_role_context(root, task_dir, args.role)
    if not context:
        print("Error: no context found for role", file=sys.stderr)
        return 1
    print("## Injected Context")
    print()
    print(context)
    if args.prompt:
        print()
        print("---")
        print()
        print("## Task")
        print()
        print(args.prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
