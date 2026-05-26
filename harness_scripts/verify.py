#!/usr/bin/env python3
"""Run harness quality checks before committing a slice."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path


COMMAND_CHECKS = ("lint", "type", "test", "coverage")
ALL_CHECKS = ("all", *COMMAND_CHECKS, "scope")
LOCAL_CONTEXT_KEY = "local"


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    while current != current.parent:
        if (current / ".harness").is_dir():
            return current
        current = current.parent
    script_path = Path(__file__).resolve()
    if script_path.parent.name == "scripts" and script_path.parent.parent.name == ".harness":
        return script_path.parent.parent.parent
    print("Error: .harness/ directory not found", file=sys.stderr)
    sys.exit(2)


def load_json(path: Path, label: str) -> dict:
    if not path.is_file():
        print(f"Error: missing {label}: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: invalid {label}: {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, dict):
        print(f"Error: {label} must be a JSON object: {path}", file=sys.stderr)
        sys.exit(2)
    return data


def load_config(root: Path) -> dict:
    return load_json(root / ".harness" / "verify.json", "verify config")


def command_for(config: dict, name: str) -> str | None:
    commands = config.get("commands")
    if not isinstance(commands, dict):
        return None
    command = commands.get(name)
    if isinstance(command, str) and command.strip():
        return command
    return None


def validate_command_config(config: dict, names: tuple[str, ...]) -> bool:
    ok = True
    for name in names:
        if command_for(config, name) is None:
            print(f"Error: missing required command config: commands.{name}", file=sys.stderr)
            ok = False
    return ok


def run_configured_command(root: Path, config: dict, name: str) -> int:
    command = command_for(config, name)
    if command is None:
        print(f"Error: missing required command config: commands.{name}", file=sys.stderr)
        return 2

    print(f"==> {name}: {command}")
    result = subprocess.run(command, cwd=root, shell=True)
    if result.returncode == 0:
        print(f"✓ {name} passed")
    else:
        print(f"✗ {name} failed with exit code {result.returncode}", file=sys.stderr)
    return result.returncode


def context_key() -> str:
    return os.environ.get("HARNESS_CONTEXT_ID") or LOCAL_CONTEXT_KEY


def resolve_task_dir(root: Path, task_arg: str | None) -> Path:
    if task_arg:
        task_ref = task_arg
    else:
        session_path = root / ".harness" / "runtime" / "sessions" / f"{context_key()}.json"
        if not session_path.is_file():
            print(
                f"Error: no active task session found: {session_path}. Pass --task <task-dir>.",
                file=sys.stderr,
            )
            sys.exit(2)
        session = load_json(session_path, "session")
        task_ref = session.get("current_task")
        if not isinstance(task_ref, str) or not task_ref:
            print("Error: current session has no active task. Pass --task <task-dir>.", file=sys.stderr)
            sys.exit(2)

    task_path = Path(task_ref)
    if task_path.is_absolute():
        task_dir = task_path
    elif task_ref.startswith(".harness/"):
        task_dir = root / task_path
    else:
        task_dir = root / ".harness" / "tasks" / task_ref

    if not task_dir.is_dir():
        print(f"Error: task directory not found: {task_ref}", file=sys.stderr)
        sys.exit(2)
    return task_dir


def run_git(root: Path, args: list[str]) -> list[str]:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr.strip() or f"Error: git {' '.join(args)} failed", file=sys.stderr)
        sys.exit(2)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(root: Path) -> list[str]:
    tracked = run_git(root, ["diff", "--name-only", "HEAD", "--"])
    untracked = run_git(root, ["ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked + untracked))


def normalize_patterns(value: object, label: str, *, required: bool = False) -> list[str]:
    if value is None:
        if required:
            print(f"Error: missing required list: {label}", file=sys.stderr)
            sys.exit(2)
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        print(f"Error: {label} must be a list of non-empty strings", file=sys.stderr)
        sys.exit(2)
    if required and not value:
        print(f"Error: {label} must contain at least one pattern", file=sys.stderr)
        sys.exit(2)
    return value


def matches_pattern(path: str, pattern: str) -> bool:
    pattern = pattern.strip()
    if pattern.endswith("/"):
        pattern = f"{pattern}**"
    plain = pattern.rstrip("/")
    if not any(ch in pattern for ch in "*?[]"):
        return path == plain or path.startswith(f"{plain}/")
    return fnmatch.fnmatchcase(path, pattern)


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(matches_pattern(path, pattern) for pattern in patterns)


def run_scope(root: Path, config: dict, task_arg: str | None) -> int:
    task_dir = resolve_task_dir(root, task_arg)
    scope = load_json(task_dir / "scope.json", "task scope")
    global_scope = config.get("scope", {})
    if not isinstance(global_scope, dict):
        print("Error: scope in verify config must be an object", file=sys.stderr)
        return 2

    allowed = normalize_patterns(scope.get("allowed"), "scope.allowed", required=True)
    task_denied = normalize_patterns(scope.get("denied"), "scope.denied")
    global_denied = normalize_patterns(global_scope.get("denied"), "verify.scope.denied")
    denied = [*global_denied, *task_denied]
    files = changed_files(root)

    if not files:
        print("✓ scope passed: no changed files")
        return 0

    failed = False
    for path in files:
        if matches_any(path, denied):
            print(f"Error: denied changed file: {path}", file=sys.stderr)
            failed = True
        elif not matches_any(path, allowed):
            print(f"Error: changed file not allowed by task scope: {path}", file=sys.stderr)
            failed = True

    if failed:
        return 1
    print(f"✓ scope passed: {len(files)} changed file(s)")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run harness quality checks")
    parser.add_argument("check", choices=ALL_CHECKS)
    parser.add_argument("--task", help="Task dir name or .harness/tasks/<dir> for scope checks")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = find_project_root(Path.cwd())
    config = load_config(root)

    if args.check == "all":
        if not validate_command_config(config, COMMAND_CHECKS):
            return 2
        for check in COMMAND_CHECKS:
            code = run_configured_command(root, config, check)
            if code != 0:
                return code
        return run_scope(root, config, args.task)

    if args.check in COMMAND_CHECKS:
        return run_configured_command(root, config, args.check)

    return run_scope(root, config, args.task)


if __name__ == "__main__":
    sys.exit(main())
