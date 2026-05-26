#!/usr/bin/env python3
"""Task management CLI for lightweight agent harness.

Usage:
    python3 task.py create "<title>" [--slug <name>]
    python3 task.py start <task-dir-name>
    python3 task.py current
    python3 task.py finish
    python3 task.py archive <task-dir-name>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

LOCAL_CONTEXT_KEY = "local"


def _find_harness_root() -> Path:
    """Walk up from cwd to find .harness/ directory."""
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".harness").is_dir():
            return current / ".harness"
        current = current.parent
    # Fallback: if running from inside .harness/scripts/
    script_path = Path(__file__).resolve()
    if "scripts" in script_path.parts:
        candidate = script_path.parent.parent
        if candidate.name == ".harness":
            return candidate
    print("Error: .harness/ directory not found", file=sys.stderr)
    sys.exit(1)


def _context_key() -> str | None:
    """Get session context key from environment."""
    return os.environ.get("HARNESS_CONTEXT_ID") or LOCAL_CONTEXT_KEY


def _session_path(harness: Path, key: str) -> Path:
    return harness / "runtime" / "sessions" / f"{key}.json"


def _read_session(harness: Path, key: str) -> dict:
    path = _session_path(harness, key)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _write_session(harness: Path, key: str, data: dict) -> None:
    path = _session_path(harness, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _slugify(title: str) -> str:
    """Convert title to a filesystem-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9一-鿿]+", "-", slug)
    slug = slug.strip("-")
    return slug[:50] if slug else "task"


def _today_prefix() -> str:
    return datetime.now().strftime("%m-%d")


def cmd_create(args: argparse.Namespace) -> int:
    """Create a new task."""
    harness = _find_harness_root()
    title = args.title

    slug = args.slug if args.slug else _slugify(title)
    dir_name = f"{_today_prefix()}-{slug}"
    task_dir = harness / "tasks" / dir_name

    if task_dir.exists():
        print(f"Error: task directory already exists: {dir_name}", file=sys.stderr)
        return 1

    task_dir.mkdir(parents=True)
    (task_dir / "research").mkdir()

    task_data = {
        "id": slug,
        "title": title,
        "description": "",
        "status": "planning",
        "priority": "P2",
        "creator": os.environ.get("USER", "unknown"),
        "assignee": os.environ.get("USER", "unknown"),
        "createdAt": datetime.now().strftime("%Y-%m-%d"),
        "completedAt": None,
        "branch": None,
        "meta": {},
    }
    (task_dir / "task.json").write_text(
        json.dumps(task_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Seed context manifests for each role (3 in v1.6: architect/developer/tester)
    seed = '{"_example": "Add entries like: {\\"file\\": \\".harness/spec/index.md\\", \\"reason\\": \\"team guidelines\\"}"}\n'
    for role in ("architect", "developer", "tester"):
        (task_dir / f"context.{role}.jsonl").write_text(seed, encoding="utf-8")

    # Auto-activate in current session
    context_key = _context_key()
    if context_key:
        session_data = _read_session(harness, context_key)
        session_data["current_task"] = f".harness/tasks/{dir_name}"
        session_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_session(harness, context_key, session_data)

    print(f"✓ Created task: {dir_name}")
    print(f"  Status: planning")
    print(f"  Path: .harness/tasks/{dir_name}/")
    return 0


def _has_curated_jsonl_entry(jsonl_path: Path) -> bool:
    """A manifest is 'curated' if it has at least one row with a `file` field.

    Seed rows like {"_example": "..."} have no `file` field and are skipped.
    """
    if not jsonl_path.is_file():
        return False
    try:
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("file"):
                return True
    except (OSError, UnicodeDecodeError):
        pass
    return False


def _check_phase_1_3_gate(task_dir: Path) -> list[str]:
    """Return a list of manifest filenames that are NOT yet curated.

    Empty list means all are curated (gate passes).
    """
    pending = []
    for role in ("architect", "developer", "tester"):
        manifest = task_dir / f"context.{role}.jsonl"
        if not _has_curated_jsonl_entry(manifest):
            pending.append(manifest.name)
    return pending


def cmd_start(args: argparse.Namespace) -> int:
    """Activate a task — flip status to in_progress.

    Phase 1.3 gate: refuses to start if any of the 4 role manifests still
    has only the `_example` seed row. Use --force to bypass.
    """
    harness = _find_harness_root()
    task_name = args.dir

    task_dir = harness / "tasks" / task_name
    if not task_dir.is_dir():
        print(f"Error: task not found: {task_name}", file=sys.stderr)
        return 1

    task_json = task_dir / "task.json"
    data = json.loads(task_json.read_text(encoding="utf-8"))

    if data.get("status") != "planning":
        print(f"Error: task status is '{data.get('status')}', expected 'planning'", file=sys.stderr)
        return 1

    # Phase 1.3 gate
    if not getattr(args, "force", False):
        pending = _check_phase_1_3_gate(task_dir)
        if pending:
            print(
                f"Error: Phase 1.3 manifest curation incomplete.\n"
                f"  These manifests still have only the _example seed row:\n"
                + "\n".join(f"    - {name}" for name in pending)
                + "\n\n"
                f"  Each manifest must have at least one row with a `file` field, e.g.:\n"
                f'    {{"file": ".harness/spec/index.md", "reason": "team conventions"}}\n\n'
                f"  Edit the files above and re-run, OR pass --force to bypass.",
                file=sys.stderr,
            )
            return 1

    data["status"] = "in_progress"
    task_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Update session pointer
    context_key = _context_key()
    if context_key:
        session_data = _read_session(harness, context_key)
        session_data["current_task"] = f".harness/tasks/{task_name}"
        session_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_session(harness, context_key, session_data)

    print(f"✓ Task activated: {task_name}")
    print(f"  Status: in_progress")
    return 0


def cmd_current(args: argparse.Namespace) -> int:
    """Show the current active task."""
    harness = _find_harness_root()
    context_key = _context_key()

    if not context_key:
        print("No session identity (set HARNESS_CONTEXT_ID)")
        return 1

    session_data = _read_session(harness, context_key)
    task_ref = session_data.get("current_task")

    if not task_ref:
        print("No active task")
        return 0

    # Resolve task directory
    project_root = harness.parent
    task_dir = project_root / task_ref
    if not task_dir.is_dir():
        print(f"Stale pointer: {task_ref}")
        return 1

    task_json = task_dir / "task.json"
    if task_json.is_file():
        data = json.loads(task_json.read_text(encoding="utf-8"))
        print(f"Task: {data.get('title', task_dir.name)}")
        print(f"Status: {data.get('status', 'unknown')}")
        print(f"Path: {task_ref}")
    else:
        print(f"Task: {task_dir.name} (no task.json)")

    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    """Clear the active task pointer."""
    harness = _find_harness_root()
    context_key = _context_key()

    if not context_key:
        print("No session identity (set HARNESS_CONTEXT_ID)")
        return 1

    session_path = _session_path(harness, context_key)
    if session_path.is_file():
        session_path.unlink()

    print("✓ Session cleared")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    """Archive a task to archive/YYYY-MM/."""
    harness = _find_harness_root()
    task_name = args.dir

    task_dir = harness / "tasks" / task_name
    if not task_dir.is_dir():
        print(f"Error: task not found: {task_name}", file=sys.stderr)
        return 1

    # Update status
    task_json = task_dir / "task.json"
    if task_json.is_file():
        data = json.loads(task_json.read_text(encoding="utf-8"))
        data["status"] = "archived"
        data["completedAt"] = datetime.now().strftime("%Y-%m-%d")
        task_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Move to archive
    archive_month = datetime.now().strftime("%Y-%m")
    archive_dir = harness / "tasks" / "archive" / archive_month
    archive_dir.mkdir(parents=True, exist_ok=True)

    dest = archive_dir / task_name
    shutil.move(str(task_dir), str(dest))

    # Clear session pointer if it pointed to this task
    context_key = _context_key()
    if context_key:
        session_data = _read_session(harness, context_key)
        if session_data.get("current_task", "").endswith(task_name):
            session_path = _session_path(harness, context_key)
            if session_path.is_file():
                session_path.unlink()

    print(f"✓ Archived: {task_name} → archive/{archive_month}/")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Harness task management")
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="Create a new task")
    p_create.add_argument("title", help="Task title")
    p_create.add_argument("--slug", help="Custom slug (default: auto from title)")

    p_start = sub.add_parser("start", help="Activate a task")
    p_start.add_argument("dir", help="Task directory name")
    p_start.add_argument(
        "--force",
        action="store_true",
        help="Bypass Phase 1.3 manifest curation gate (use with care)",
    )

    sub.add_parser("current", help="Show active task")
    sub.add_parser("finish", help="Clear active task")

    p_archive = sub.add_parser("archive", help="Archive a task")
    p_archive.add_argument("dir", help="Task directory name")

    args = parser.parse_args()

    commands = {
        "create": cmd_create,
        "start": cmd_start,
        "current": cmd_current,
        "finish": cmd_finish,
        "archive": cmd_archive,
    }

    handler = commands.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
