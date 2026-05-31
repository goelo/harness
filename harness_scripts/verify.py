#!/usr/bin/env python3
"""Run harness quality checks and write phase evidence files."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


COMMAND_CHECKS = ("lint", "type", "test", "coverage")
ALL_CHECKS = ("all", *COMMAND_CHECKS, "scope", "red", "green")
LOCAL_CONTEXT_KEY = "local"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def required_checks(config: dict) -> list[str]:
    value = config.get("required", ["test", "scope"])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        print("Error: required must be a list of check names", file=sys.stderr)
        sys.exit(2)
    allowed = set(COMMAND_CHECKS + ("scope",))
    unknown = [item for item in value if item not in allowed]
    if unknown:
        print(f"Error: unknown required checks: {', '.join(unknown)}", file=sys.stderr)
        sys.exit(2)
    return value


def run_configured_command(root: Path, config: dict, name: str) -> dict:
    command = command_for(config, name)
    if command is None:
        print(f"Error: missing required command config: commands.{name}", file=sys.stderr)
        return {"name": name, "command": None, "exitCode": 2, "success": False}

    print(f"==> {name}: {command}")
    result = subprocess.run(command, cwd=root, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✓ {name} passed")
    else:
        print(f"✗ {name} failed with exit code {result.returncode}", file=sys.stderr)
    return {
        "name": name,
        "command": command,
        "exitCode": result.returncode,
        "success": result.returncode == 0,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def context_key() -> str:
    return os.environ.get("HARNESS_CONTEXT_ID") or LOCAL_CONTEXT_KEY


def resolve_task_dir(root: Path, task_arg: str | None) -> Path:
    if task_arg:
        task_ref = task_arg
    else:
        session_path = root / ".harness" / "runtime" / "sessions" / f"{context_key()}.json"
        if not session_path.is_file():
            print(f"Error: no active task session found: {session_path}. Pass --task <task-dir>.", file=sys.stderr)
            sys.exit(2)
        session = load_json(session_path, "session")
        task_ref = session.get("current_task")
        if not isinstance(task_ref, str) or not task_ref:
            print("Error: current session has no active task. Pass --task <task-dir>.", file=sys.stderr)
            sys.exit(2)

    path = Path(task_ref)
    if path.is_absolute():
        task_dir = path
    elif task_ref.startswith("docs/tasks/"):
        task_dir = root / path
    else:
        task_dir = root / "docs" / "tasks" / task_ref

    if not task_dir.is_dir():
        print(f"Error: task directory not found: {task_ref}", file=sys.stderr)
        sys.exit(2)
    return task_dir


def run_git(root: Path, args: list[str]) -> list[str]:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(root: Path) -> list[str]:
    tracked = run_git(root, ["diff", "--name-only", "HEAD", "--"])
    untracked = run_git(root, ["ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked + untracked))


def normalize_patterns(value: object, label: str, *, required: bool = False) -> list[str]:
    if value is None:
        if required:
            raise ValueError(f"missing required list: {label}")
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    if required and not value:
        raise ValueError(f"{label} must contain at least one pattern")
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


def run_scope(root: Path, config: dict, task_arg: str | None) -> dict:
    task_dir = resolve_task_dir(root, task_arg)
    scope = load_json(task_dir / "scope.json", "task scope")
    global_scope = config.get("scope", {})
    if not isinstance(global_scope, dict):
        return {"success": False, "errors": ["scope in verify config must be an object"]}

    try:
        allowed = normalize_patterns(scope.get("allowed"), "scope.allowed", required=True)
        task_denied = normalize_patterns(scope.get("denied"), "scope.denied")
        global_denied = normalize_patterns(global_scope.get("denied"), "verify.scope.denied")
    except ValueError as exc:
        return {"success": False, "errors": [str(exc)]}

    denied = [*global_denied, *task_denied]
    files = changed_files(root)
    errors = []
    for path in files:
        if matches_any(path, denied):
            errors.append(f"denied changed file: {path}")
        elif not matches_any(path, allowed):
            errors.append(f"changed file not allowed by task scope: {path}")

    if errors:
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
    else:
        print(f"✓ scope passed: {len(files)} changed file(s)")
    return {"success": not errors, "changedFiles": files, "errors": errors}


def write_verify_result(task_dir: Path, result: dict) -> None:
    write_json(task_dir / "verify-result.json", result)


def run_all(root: Path, config: dict, task_arg: str | None) -> int:
    task_dir = resolve_task_dir(root, task_arg)
    required = required_checks(config)
    command_results = []
    success = True

    for check in required:
        if check == "scope":
            continue
        result = run_configured_command(root, config, check)
        command_results.append(result)
        if not result["success"]:
            success = False

    scope_result = {"success": True, "changedFiles": changed_files(root), "errors": []}
    if "scope" in required:
        scope_result = run_scope(root, config, task_arg)
        if not scope_result["success"]:
            success = False

    output = {
        "success": success,
        "commands": command_results,
        "scope": scope_result,
        "changedFiles": changed_files(root),
        "finishedAt": utc_now(),
        "generatedBy": "verify.py all",
    }
    write_verify_result(task_dir, output)
    return 0 if success else 1


def run_red_green(root: Path, args: argparse.Namespace, *, mode: str) -> int:
    task_dir = resolve_task_dir(root, args.task)
    if not args.target_test:
        print("Error: at least one --target-test is required", file=sys.stderr)
        return 2
    result = subprocess.run(args.command, cwd=root, shell=True, capture_output=True, text=True)
    expected_failure = mode == "red" and result.returncode != 0
    expected_pass = mode == "green" and result.returncode == 0
    success = expected_failure if mode == "red" else expected_pass
    payload = {
        "success": success,
        "command": args.command,
        "exitCode": result.returncode,
        "targetTests": args.target_test,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "finishedAt": utc_now(),
        "generatedBy": f"verify.py {mode}",
    }
    if mode == "red":
        payload["expectedFailureObserved"] = expected_failure
        filename = "test-result.red.json"
    else:
        payload["expectedPassObserved"] = expected_pass
        filename = "test-result.green.json"
    write_json(task_dir / filename, payload)
    if success:
        print(f"✓ {mode} evidence written: {filename}")
        return 0
    print(f"Error: {mode} command did not meet expected result", file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run harness quality checks")
    parser.add_argument("check", choices=ALL_CHECKS)
    parser.add_argument("--task", help="Task dir name or docs/tasks/<dir> for checks")
    parser.add_argument("--command", help="Command for red/green evidence")
    parser.add_argument("--target-test", action="append", help="Target test identifier for red/green evidence")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = find_project_root(Path.cwd())
    config = load_config(root)

    if args.check == "all":
        return run_all(root, config, args.task)
    if args.check in COMMAND_CHECKS:
        result = run_configured_command(root, config, args.check)
        return result["exitCode"]
    if args.check == "scope":
        result = run_scope(root, config, args.task)
        return 0 if result["success"] else 1
    if args.check in ("red", "green"):
        if not args.command:
            print(f"Error: verify.py {args.check} requires --command", file=sys.stderr)
            return 2
        return run_red_green(root, args, mode=args.check)
    return 2


if __name__ == "__main__":
    sys.exit(main())
