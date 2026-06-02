#!/usr/bin/env python3
"""Task management CLI for the agent harness.

The CLI is an internal tool for skills and hooks. Team members interact through
natural language; agents call this script to keep task state machine transitions
and evidence files deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LOCAL_CONTEXT_KEY = "local"
TASKS_ROOT = Path("docs/tasks")
PHASE_ORDER = ("clarify", "doc-plan", "red", "green", "review", "validate", "done")
VALID_INTENTS = ("requirement-development", "requirement-confirmation")
VALID_EXECUTION_MODES = ("agent-team",)
PLAN_SECTIONS = (
    "开发意图摘要",
    "影响范围",
    "技术方案",
    "可测试契约",
    "业务契约覆盖",
    "Slice 顺序",
    "验证方式",
    "已知限制",
)
BUSINESS_CONTRACT_REQUIRED_FIELDS = ("id", "scenario", "expectedBehavior")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_prefix() -> str:
    return datetime.now().strftime("%m-%d")


def _find_project_root() -> Path:
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".harness").is_dir():
            return current
        current = current.parent
    script_path = Path(__file__).resolve()
    if script_path.parent.name == "scripts" and script_path.parent.parent.name == ".harness":
        return script_path.parent.parent.parent
    print("Error: .harness/ directory not found", file=sys.stderr)
    sys.exit(1)


def _harness_root(root: Path) -> Path:
    return root / ".harness"


def _tasks_root(root: Path) -> Path:
    return root / TASKS_ROOT


def _context_key() -> str:
    return os.environ.get("HARNESS_CONTEXT_ID") or LOCAL_CONTEXT_KEY


def _session_path(root: Path, key: str) -> Path:
    return _harness_root(root) / "runtime" / "sessions" / f"{key}.json"


def _read_json(path: Path, label: str) -> dict:
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


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_session(root: Path, key: str) -> dict:
    path = _session_path(root, key)
    if path.is_file():
        return _read_json(path, "session")
    return {}


def _write_session(root: Path, key: str, data: dict) -> None:
    _write_json(_session_path(root, key), data)


def _slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9一-鿿]+", "-", slug)
    slug = slug.strip("-")
    return slug[:50] if slug else "requirement"


def _task_ref(task_dir: Path, root: Path) -> str:
    return task_dir.relative_to(root).as_posix()


def _resolve_task_dir(root: Path, task_arg: str | None = None) -> Path:
    if task_arg:
        ref = task_arg
    else:
        session = _read_session(root, _context_key())
        ref = session.get("current_task")
        if not ref:
            print("Error: no active task. Create or select a task first.", file=sys.stderr)
            sys.exit(2)

    path = Path(ref)
    if path.is_absolute():
        task_dir = path
    elif ref.startswith("docs/tasks/"):
        task_dir = root / path
    else:
        task_dir = _tasks_root(root) / ref

    if not task_dir.is_dir():
        print(f"Error: task directory not found: {ref}", file=sys.stderr)
        sys.exit(2)
    return task_dir


def _read_task(task_dir: Path) -> dict:
    return _read_json(task_dir / "task.json", "task.json")


def _write_task(task_dir: Path, data: dict) -> None:
    _write_json(task_dir / "task.json", data)


def _history_event(task_dir: Path, event: dict) -> None:
    data = _read_task(task_dir)
    history = data.setdefault("phaseHistory", [])
    event.setdefault("at", _utc_now())
    history.append(event)
    _write_task(task_dir, data)


def _record_advance_failure(task_dir: Path, phase: str, reason: str) -> None:
    data = _read_task(task_dir)
    attempts = data.setdefault("phaseAttempts", {})
    phase_attempt = attempts.setdefault(phase, {})
    phase_attempt["autoFixCount"] = phase_attempt.get("autoFixCount", 0)
    phase_attempt["lastError"] = reason
    phase_attempt["lastFailedAt"] = _utc_now()
    data.setdefault("phaseHistory", []).append(
        {"event": "advance_failed", "phase": phase, "reason": reason, "at": _utc_now()}
    )
    _write_task(task_dir, data)


def _advance_to(task_dir: Path, target: str, evidence: list[str]) -> None:
    data = _read_task(task_dir)
    old = data.get("phase")
    data["phase"] = target
    data["status"] = "done" if target == "done" else "in_progress"
    data.setdefault("phaseHistory", []).append(
        {
            "event": "advanced",
            "from": old,
            "to": target,
            "at": _utc_now(),
            "evidence": evidence,
        }
    )
    _write_task(task_dir, data)


def _fail_advance(task_dir: Path, phase: str, reason: str) -> int:
    _record_advance_failure(task_dir, phase, reason)
    print(f"Error: {reason}", file=sys.stderr)
    return 1


def _git_lines(root: Path, args: list[str]) -> list[str]:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _changed_files(root: Path) -> list[str]:
    tracked = _git_lines(root, ["diff", "--name-only", "HEAD", "--"])
    untracked = _git_lines(root, ["ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked + untracked))


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def cmd_create(args: argparse.Namespace) -> int:
    root = _find_project_root()
    tasks_root = _tasks_root(root)
    tasks_root.mkdir(parents=True, exist_ok=True)

    slug = args.slug or _slugify(args.title)
    dir_name = f"{_today_prefix()}-{slug}"
    task_dir = tasks_root / dir_name
    if task_dir.exists():
        print(f"Error: task directory already exists: {dir_name}", file=sys.stderr)
        return 1

    task_dir.mkdir(parents=True)
    task_data = {
        "id": slug,
        "title": args.title,
        "description": "",
        "status": "in_progress",
        "phase": "clarify",
        "originIntent": args.origin_intent,
        "executionMode": args.execution_mode,
        "executionModeFallbackReason": None,
        "priority": "P2",
        "creator": os.environ.get("USER", "unknown"),
        "assignee": os.environ.get("USER", "unknown"),
        "createdAt": datetime.now().strftime("%Y-%m-%d"),
        "completedAt": None,
        "branch": None,
        "sourceDoc": args.source_doc,
        "sourceDocHash": args.source_hash,
        "phaseHistory": [],
        "phaseAttempts": {},
        "meta": {},
    }
    _write_task(task_dir, task_data)
    (task_dir / "clarification.jsonl").write_text("", encoding="utf-8")

    seed = (
        '{"_example":"请添加真实文件引用，例如 '
        '{\\"file\\":\\"docs/standards/index.md\\",\\"reason\\":\\"团队工程规范入口\\"}"}\n'
    )
    for role in ("architect", "developer", "tester"):
        (task_dir / f"context.{role}.jsonl").write_text(seed, encoding="utf-8")

    session = _read_session(root, _context_key())
    session["current_task"] = _task_ref(task_dir, root)
    session["updated_at"] = _utc_now()
    _write_session(root, _context_key(), session)

    print(f"✓ Created task: {dir_name}")
    print("  Status: in_progress")
    print("  Phase: clarify")
    print(f"  Path: docs/tasks/{dir_name}/")
    return 0


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{idx}: invalid JSON: {exc}") from exc
        if isinstance(record, dict):
            records.append(record)
    return records


def _latest_confirmation(task_dir: Path) -> dict | None:
    records = _read_jsonl(task_dir / "clarification.jsonl")
    confirms = [record for record in records if record.get("event") == "confirm"]
    return confirms[-1] if confirms else None


def _render_clarification(task_dir: Path, confirmation: dict) -> None:
    criteria = "\n".join(f"{idx}. {item}" for idx, item in enumerate(confirmation["acceptanceCriteria"], start=1))
    boundaries = "\n".join(f"{idx}. {item}" for idx, item in enumerate(confirmation["boundaries"], start=1))
    business_contracts = confirmation.get("businessContracts") or []
    contract_section = ""
    if business_contracts:
        rows = [
            "| 编号 | 业务场景 | 输入条件 | 预期行为 | 可观测信息 | 是否需要测试 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for item in business_contracts:
            rows.append(
                "| {id} | {scenario} | {input} | {expected} | {observable} | {test_required} |".format(
                    id=item.get("id", ""),
                    scenario=item.get("scenario", ""),
                    input=item.get("input", ""),
                    expected=item.get("expectedBehavior", ""),
                    observable=item.get("observable", ""),
                    test_required="是" if item.get("testRequired", True) else "否",
                )
            )
        contract_section = "\n## 业务契约\n\n" + "\n".join(rows) + "\n"
    content = f"""---
confirmation_source: {confirmation["confirmationSource"]}
confirmed: true
confirmed_by: collaborator
open_questions: []
source_doc: {confirmation["sourceDoc"]}
source_doc_hash: {confirmation["sourceDocHash"]}
business_contracts: {len(business_contracts)}
---

# 需求确认

## 开发意图

{confirmation["developmentIntent"]}

## 验收标准

{criteria}

## 边界条件

{boundaries}
{contract_section}
"""
    (task_dir / "clarification.md").write_text(content, encoding="utf-8")


def _parse_business_contracts(raw_items: list[str] | None) -> tuple[list[dict], str | None]:
    contracts = []
    for idx, raw in enumerate(raw_items or [], start=1):
        try:
            item = json.loads(raw)
        except json.JSONDecodeError as exc:
            return [], f"business-contract:{idx}: invalid JSON: {exc}"
        if not isinstance(item, dict):
            return [], f"business-contract:{idx}: must be a JSON object"
        missing = [field for field in BUSINESS_CONTRACT_REQUIRED_FIELDS if not item.get(field)]
        if missing:
            return [], f"business-contract:{idx}: missing required fields: {', '.join(missing)}"
        contracts.append(item)
    return contracts, None


def cmd_clarify_confirm(args: argparse.Namespace) -> int:
    root = _find_project_root()
    task_dir = _resolve_task_dir(root, args.task)
    business_contracts, parse_error = _parse_business_contracts(args.business_contract)
    if parse_error:
        print(f"Error: {parse_error}", file=sys.stderr)
        return 1
    record = {
        "event": "confirm",
        "at": _utc_now(),
        "confirmationSource": args.confirmation_source,
        "sourceDoc": args.source_doc,
        "sourceDocHash": args.source_hash or _sha256_text(args.development_intent),
        "developmentIntent": args.development_intent.strip(),
        "acceptanceCriteria": [item.strip() for item in args.acceptance_criterion if item.strip()],
        "boundaries": [item.strip() for item in args.boundary if item.strip()],
        "openQuestions": [],
        "confirmed": True,
        "confirmedBy": "collaborator",
        "businessContracts": business_contracts,
    }
    error = _validate_confirmation(record)
    if error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    _append_jsonl(task_dir / "clarification.jsonl", record)
    _render_clarification(task_dir, record)
    print("✓ Requirement clarification confirmed")
    return 0


def cmd_clarify_render(args: argparse.Namespace) -> int:
    root = _find_project_root()
    task_dir = _resolve_task_dir(root, args.task)
    confirmation = _latest_confirmation(task_dir)
    if not confirmation:
        print("Error: no confirmed clarification found", file=sys.stderr)
        return 1
    _render_clarification(task_dir, confirmation)
    print("✓ Rendered clarification.md")
    return 0


def _validate_confirmation(record: dict) -> str | None:
    if not record.get("confirmed"):
        return "clarification is not confirmed"
    if record.get("confirmedBy") != "collaborator":
        return "confirmedBy must be collaborator"
    if not record.get("developmentIntent"):
        return "developmentIntent is required"
    if not record.get("acceptanceCriteria"):
        return "at least one acceptance criterion is required"
    if not record.get("boundaries"):
        return "at least one boundary is required"
    if record.get("openQuestions"):
        return "openQuestions must be empty"
    if not record.get("sourceDoc"):
        return "sourceDoc is required"
    if not record.get("sourceDocHash"):
        return "sourceDocHash is required"
    return None


def _validate_plan_file(path: Path) -> str | None:
    if not path.is_file():
        return "missing implementation-plan.md"
    content = path.read_text(encoding="utf-8")
    for section in PLAN_SECTIONS:
        marker = f"## {section}"
        if marker not in content:
            return f"implementation-plan.md missing section: {section}"
        after = content.split(marker, 1)[1]
        body = after.split("\n## ", 1)[0].strip()
        if not body:
            return f"implementation-plan.md section is empty: {section}"
    return None


def _normalize_patterns(value: object, label: str, required: bool = False) -> list[str]:
    if value is None:
        if required:
            raise ValueError(f"missing required list: {label}")
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    if required and not value:
        raise ValueError(f"{label} must contain at least one pattern")
    return value


def _validate_scope(task_dir: Path) -> str | None:
    path = task_dir / "scope.json"
    if not path.is_file():
        return "missing scope.json"
    try:
        scope = _read_json(path, "scope.json")
        _normalize_patterns(scope.get("allowed"), "scope.allowed", required=True)
        _normalize_patterns(scope.get("denied"), "scope.denied")
    except SystemExit:
        raise
    except ValueError as exc:
        return str(exc)
    return None


def _validate_manifest(root: Path, task_dir: Path, role: str) -> str | None:
    path = task_dir / f"context.{role}.jsonl"
    if not path.is_file():
        return f"missing context.{role}.jsonl"
    try:
        records = _read_jsonl(path)
    except ValueError as exc:
        return str(exc)
    valid = []
    for idx, record in enumerate(records, start=1):
        if "_example" in record:
            continue
        file_path = record.get("file")
        reason = record.get("reason")
        if not file_path or not isinstance(file_path, str):
            return f"context.{role}.jsonl:{idx}: file is required"
        if any(ch in file_path for ch in "*?[]") or file_path.endswith("/"):
            return f"context.{role}.jsonl:{idx}: file must reference a concrete file"
        if not reason or not isinstance(reason, str):
            return f"context.{role}.jsonl:{idx}: reason is required"
        resolved = root / file_path
        if not resolved.is_file():
            return f"context.{role}.jsonl:{idx}: referenced file not found: {file_path}"
        valid.append(record)
    if not valid:
        return f"context.{role}.jsonl has no valid file entries"
    return None


def _validate_test_result(path: Path, expected_key: str) -> tuple[dict | None, str | None]:
    if not path.is_file():
        return None, f"missing {path.name}"
    data = _read_json(path, path.name)
    if data.get(expected_key) is not True:
        return None, f"{path.name}.{expected_key} must be true"
    target_tests = data.get("targetTests")
    if not isinstance(target_tests, list) or not target_tests:
        return None, f"{path.name}.targetTests must be non-empty"
    return data, None


def _advance_doc_plan(root: Path, task_dir: Path) -> int:
    confirmation = _latest_confirmation(task_dir)
    if not confirmation:
        return _fail_advance(task_dir, "doc-plan", "confirmed clarification is required")
    error = _validate_confirmation(confirmation)
    if error:
        return _fail_advance(task_dir, "doc-plan", error)
    data = _read_task(task_dir)
    data["sourceDoc"] = confirmation["sourceDoc"]
    data["sourceDocHash"] = confirmation["sourceDocHash"]
    _write_task(task_dir, data)
    _advance_to(task_dir, "doc-plan", [_task_ref(task_dir / "clarification.jsonl", root)])
    print("✓ Advanced to doc-plan")
    return 0


def _advance_red(root: Path, task_dir: Path) -> int:
    for error in (
        _validate_plan_file(task_dir / "implementation-plan.md"),
        _validate_scope(task_dir),
        _validate_manifest(root, task_dir, "architect"),
        _validate_manifest(root, task_dir, "developer"),
        _validate_manifest(root, task_dir, "tester"),
    ):
        if error:
            return _fail_advance(task_dir, "red", error)
    _advance_to(
        task_dir,
        "red",
        [
            _task_ref(task_dir / "implementation-plan.md", root),
            _task_ref(task_dir / "scope.json", root),
            _task_ref(task_dir / "context.architect.jsonl", root),
            _task_ref(task_dir / "context.developer.jsonl", root),
            _task_ref(task_dir / "context.tester.jsonl", root),
        ],
    )
    print("✓ Advanced to red")
    return 0


def _advance_green(root: Path, task_dir: Path) -> int:
    _, error = _validate_test_result(task_dir / "test-result.red.json", "expectedFailureObserved")
    if error:
        return _fail_advance(task_dir, "green", error)
    _advance_to(task_dir, "green", [_task_ref(task_dir / "test-result.red.json", root)])
    print("✓ Advanced to green")
    return 0


def _advance_review(root: Path, task_dir: Path) -> int:
    red, error = _validate_test_result(task_dir / "test-result.red.json", "expectedFailureObserved")
    if error:
        return _fail_advance(task_dir, "review", error)
    green, error = _validate_test_result(task_dir / "test-result.green.json", "expectedPassObserved")
    if error:
        return _fail_advance(task_dir, "review", error)
    if red and green and red.get("targetTests") != green.get("targetTests"):
        return _fail_advance(task_dir, "review", "RED and GREEN targetTests differ")
    _advance_to(task_dir, "review", [_task_ref(task_dir / "test-result.green.json", root)])
    print("✓ Advanced to review")
    return 0


def _review_passed(data: dict) -> bool:
    business = data.get("businessContractCoverage", {})
    return (
        data.get("specCompliance", {}).get("status") == "passed"
        and data.get("codeQuality", {}).get("status") == "passed"
        and business.get("status") == "passed"
        and not business.get("missing")
        and not data.get("blockingIssues")
    )


def _advance_validate(root: Path, task_dir: Path) -> int:
    path = task_dir / "review-result.json"
    if not path.is_file():
        return _fail_advance(task_dir, "validate", "missing review-result.json")
    review = _read_json(path, "review-result.json")
    if not _review_passed(review):
        return _fail_advance(task_dir, "validate", "review-result.json has blocking issues or business contract review failed")
    if sorted(review.get("changedFiles", [])) != _changed_files(root):
        return _fail_advance(task_dir, "validate", "working tree changed after review")
    _advance_to(task_dir, "validate", [_task_ref(path, root)])
    print("✓ Advanced to validate")
    return 0


def _advance_done(root: Path, task_dir: Path) -> int:
    path = task_dir / "verify-result.json"
    if not path.is_file():
        return _fail_advance(task_dir, "done", "missing verify-result.json")
    verify = _read_json(path, "verify-result.json")
    if verify.get("success") is not True:
        return _fail_advance(task_dir, "done", "verify-result.json success must be true")
    if sorted(verify.get("changedFiles", [])) != _changed_files(root):
        return _fail_advance(task_dir, "done", "working tree changed after final verify")
    _advance_to(task_dir, "done", [_task_ref(path, root)])
    print("✓ Advanced to done")
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    root = _find_project_root()
    task_dir = _resolve_task_dir(root, args.task)
    target = args.phase
    handlers = {
        "doc-plan": _advance_doc_plan,
        "red": _advance_red,
        "green": _advance_green,
        "review": _advance_review,
        "validate": _advance_validate,
        "done": _advance_done,
    }
    handler = handlers[target]
    return handler(root, task_dir)


def cmd_review_record(args: argparse.Namespace) -> int:
    root = _find_project_root()
    task_dir = _resolve_task_dir(root, args.task)
    blocking = args.blocking_issue or []
    record = {
        "generatedBy": "task.py review record",
        "baseRef": "HEAD",
        "headRef": "working-tree",
        "changedFiles": _changed_files(root),
        "specCompliance": {"status": args.spec_compliance, "issues": []},
        "codeQuality": {"status": args.code_quality, "issues": []},
        "businessContractCoverage": {
            "status": args.business_contract_status,
            "missing": args.missing_contract or [],
        },
        "blockingIssues": blocking,
        "summary": args.summary or "",
        "finishedAt": _utc_now(),
    }
    _write_json(task_dir / "review-result.json", record)
    print("✓ Recorded review-result.json")
    return 0


def cmd_intent_set(args: argparse.Namespace) -> int:
    root = _find_project_root()
    task_dir = _resolve_task_dir(root, args.task)
    data = _read_task(task_dir)
    old = data.get("originIntent")
    data["originIntent"] = args.intent
    data.setdefault("phaseHistory", []).append(
        {
            "event": "origin_intent_updated",
            "from": old,
            "to": args.intent,
            "at": _utc_now(),
            "reason": args.reason,
        }
    )
    _write_task(task_dir, data)
    print(f"✓ originIntent set to {args.intent}")
    return 0


def cmd_current(args: argparse.Namespace) -> int:
    root = _find_project_root()
    session = _read_session(root, _context_key())
    task_ref = session.get("current_task")
    if not task_ref:
        print("No active task")
        return 0
    task_dir = _resolve_task_dir(root, task_ref)
    data = _read_task(task_dir)
    print(f"Task: {data.get('title', task_dir.name)}")
    print(f"Status: {data.get('status', 'unknown')}")
    print(f"Phase: {data.get('phase', 'unknown')}")
    print(f"ExecutionMode: {data.get('executionMode', 'unknown')}")
    print(f"Path: {task_ref}")
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    root = _find_project_root()
    session_path = _session_path(root, _context_key())
    if session_path.is_file():
        session_path.unlink()
    print("✓ Session cleared")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    root = _find_project_root()
    task_dir = _resolve_task_dir(root, args.dir)
    data = _read_task(task_dir)
    if data.get("phase") != "done":
        print("Error: task must have phase=done before archive", file=sys.stderr)
        return 1
    verify = _read_json(task_dir / "verify-result.json", "verify-result.json")
    if verify.get("success") is not True:
        print("Error: verify-result.json success must be true", file=sys.stderr)
        return 1

    data["status"] = "archived"
    data["phase"] = "archived"
    data["completedAt"] = datetime.now().strftime("%Y-%m-%d")
    data.setdefault("phaseHistory", []).append({"event": "archived", "at": _utc_now()})
    _write_task(task_dir, data)

    archive_month = datetime.now().strftime("%Y-%m")
    archive_dir = _tasks_root(root) / "archive" / archive_month
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / task_dir.name
    shutil.move(str(task_dir), str(dest))

    session_path = _session_path(root, _context_key())
    if session_path.is_file():
        session = _read_json(session_path, "session")
        if session.get("current_task") == _task_ref(task_dir, root):
            session_path.unlink()

    print(f"✓ Archived: {task_dir.name} -> docs/tasks/archive/{archive_month}/")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Harness task management")
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="Create a new clarify-phase task")
    p_create.add_argument("title")
    p_create.add_argument("--slug")
    p_create.add_argument("--origin-intent", choices=VALID_INTENTS, default="requirement-development")
    p_create.add_argument("--execution-mode", choices=VALID_EXECUTION_MODES, default="agent-team")
    p_create.add_argument("--source-doc", default="inline-request")
    p_create.add_argument("--source-hash")

    p_clarify = sub.add_parser("clarify", help="Manage requirement clarification")
    clarify_sub = p_clarify.add_subparsers(dest="clarify_command")
    p_confirm = clarify_sub.add_parser("confirm", help="Record confirmed requirement clarification")
    p_confirm.add_argument("--task")
    p_confirm.add_argument("--development-intent", required=True)
    p_confirm.add_argument("--acceptance-criterion", action="append", required=True)
    p_confirm.add_argument("--boundary", action="append", required=True)
    p_confirm.add_argument("--business-contract", action="append")
    p_confirm.add_argument("--source-doc", default="inline-request")
    p_confirm.add_argument("--source-hash")
    p_confirm.add_argument("--confirmation-source", choices=("live", "imported"), default="live")
    p_render = clarify_sub.add_parser("render", help="Render clarification.md from jsonl")
    p_render.add_argument("--task")

    p_advance = sub.add_parser("advance", help="Advance to the next phase")
    p_advance.add_argument("phase", choices=PHASE_ORDER[1:])
    p_advance.add_argument("--task")

    p_review = sub.add_parser("review", help="Record review evidence")
    review_sub = p_review.add_subparsers(dest="review_command")
    p_record = review_sub.add_parser("record")
    p_record.add_argument("--task")
    p_record.add_argument("--spec-compliance", choices=("passed", "failed", "not_started"), required=True)
    p_record.add_argument("--code-quality", choices=("passed", "failed", "not_started"), required=True)
    p_record.add_argument("--business-contract-status", choices=("passed", "failed", "not_started"), default="passed")
    p_record.add_argument("--missing-contract", action="append")
    p_record.add_argument("--blocking-issue", action="append")
    p_record.add_argument("--summary")

    p_intent = sub.add_parser("intent", help="Manage origin intent")
    intent_sub = p_intent.add_subparsers(dest="intent_command")
    p_intent_set = intent_sub.add_parser("set")
    p_intent_set.add_argument("intent", choices=VALID_INTENTS)
    p_intent_set.add_argument("--task")
    p_intent_set.add_argument("--reason", default="collaborator requested intent change")

    sub.add_parser("current", help="Show active task")
    sub.add_parser("finish", help="Clear active task pointer")

    p_archive = sub.add_parser("archive", help="Archive a done task")
    p_archive.add_argument("dir")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "create":
        return cmd_create(args)
    if args.command == "clarify" and args.clarify_command == "confirm":
        return cmd_clarify_confirm(args)
    if args.command == "clarify" and args.clarify_command == "render":
        return cmd_clarify_render(args)
    if args.command == "advance":
        return cmd_advance(args)
    if args.command == "review" and args.review_command == "record":
        return cmd_review_record(args)
    if args.command == "intent" and args.intent_command == "set":
        return cmd_intent_set(args)
    if args.command == "current":
        return cmd_current(args)
    if args.command == "finish":
        return cmd_finish(args)
    if args.command == "archive":
        return cmd_archive(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
