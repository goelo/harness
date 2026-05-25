#!/usr/bin/env python3
"""Build role-specific harness context for non-hook runtimes.

Claude Code receives this context through PreToolUse hooks. Runtimes without
Claude hook events can call this script explicitly before dispatching a role.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STANDARD_ROLES = ("architect", "developer", "tester")
TASK_CONTEXT_FILENAMES = ("proposal.md", "design.md", "tasks.md")
ROOT_DESIGN_FILENAMES = ("design.md", "spec.md", "requirements.md")


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
    elif task.startswith(".harness/"):
        candidate = root / task
    else:
        candidate = root / ".harness" / "tasks" / task

    if not candidate.is_dir():
        print(f"Error: task directory not found: {task}", file=sys.stderr)
        sys.exit(1)
    return candidate


def read_file_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return ""


def read_task_context_docs(task_dir: Path) -> list[tuple[str, str]]:
    results = []
    for name in TASK_CONTEXT_FILENAMES:
        content = read_file_safe(task_dir / name)
        if content:
            results.append((name, content))
    return results


def find_project_design(root: Path) -> Path | None:
    for name in ROOT_DESIGN_FILENAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def read_design_context(root: Path, task_dir: Path) -> list[tuple[str, str]]:
    task_docs = read_task_context_docs(task_dir)
    if task_docs:
        return task_docs

    design_path = find_project_design(root)
    if design_path is None:
        return []
    design = read_file_safe(design_path)
    return [(design_path.name, design)] if design else []


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
    for path in sorted(directory.glob("*.md")):
        content = read_file_safe(path)
        if content:
            results.append((path.name, content))
    return results


def build_role_context(root: Path, task_dir: Path, role: str) -> str:
    parts = []

    manifest = task_dir / f"context.{role}.jsonl"
    for file_path, content in read_jsonl_context(root, manifest):
        parts.append(f"=== {file_path} ===\n{content}")

    for filename, content in read_design_context(root, task_dir):
        parts.append(f"=== {filename} ===\n{content}")

    info = read_file_safe(task_dir / "info.md")
    if info:
        parts.append(f"=== info.md ===\n{info}")

    if role == "architect":
        for filename, content in read_directory_md_files(task_dir / "research"):
            parts.append(f"=== research/{filename} ===\n{content}")

    return "\n\n".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build harness role context")
    parser.add_argument("role", choices=STANDARD_ROLES)
    parser.add_argument("--task", required=True, help="Task dir name or .harness/tasks/<dir>")
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
