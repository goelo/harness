#!/usr/bin/env python3
"""Project documentation CLI for harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


CONFIG_PATH = ".harness/project-docs.json"
PROFILE_PATH = ".harness/project-profile.json"
BLOCK_START = "<!-- harness-project-docs:start -->"
BLOCK_END = "<!-- harness-project-docs:end -->"

DEFAULT_DOCUMENTS = [
    {
        "id": "projectGuide",
        "title": "项目说明",
        "output": "docs/standards/project-guide.md",
        "description": "记录项目架构、模块职责、启动方式、开发约定和常见变更入口。",
    },
    {
        "id": "apiUrlIndex",
        "title": "接口地址索引",
        "output": "docs/standards/api/url-index.md",
        "description": "记录项目暴露的 HTTP、RPC 或事件接口入口和代码位置。",
    },
    {
        "id": "apiDetail",
        "title": "接口详情",
        "output": "docs/standards/api/detail.md",
        "description": "记录接口请求、响应、鉴权、错误码和重要业务约束。",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_project_root() -> Path:
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".harness").is_dir():
            return current
        current = current.parent
    script = Path(__file__).resolve()
    if script.parent.name == "scripts" and script.parent.parent.name == ".harness":
        return script.parent.parent.parent
    print("Error: .harness/ directory not found", file=sys.stderr)
    sys.exit(1)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON: {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, dict):
        print(f"Error: JSON root must be object: {path}", file=sys.stderr)
        sys.exit(2)
    return data


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _default_config() -> dict:
    return {
        "version": 1,
        "preset": "default",
        "documents": DEFAULT_DOCUMENTS,
        "review": {
            "initialStatus": "draft",
            "statuses": ["draft", "approved", "needs_update", "stale", "missing"],
        },
        "analysis": {
            "cacheDir": ".harness/analysis/latest",
            "keepHistory": False,
        },
        "contextInjection": {
            "standardsIndex": "docs/standards/index.md",
            "documents": [item["output"] for item in DEFAULT_DOCUMENTS],
        },
    }


def _document_from_config(config: dict) -> list[dict]:
    documents = config.get("documents")
    if not isinstance(documents, list) or not documents:
        return DEFAULT_DOCUMENTS
    valid = []
    for item in documents:
        if not isinstance(item, dict):
            continue
        output = item.get("output")
        doc_id = item.get("id")
        if isinstance(output, str) and output and isinstance(doc_id, str) and doc_id:
            valid.append(item)
    return valid or DEFAULT_DOCUMENTS


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def _profile_document(root: Path, doc: dict, existing: dict | None = None) -> dict:
    existing = existing or {}
    rel_path = doc["output"]
    path = root / rel_path
    content_hash = _sha256_file(path) if path.is_file() else ""
    old_hash = existing.get("contentHash") if isinstance(existing.get("contentHash"), str) else ""
    old_status = existing.get("reviewStatus") if isinstance(existing.get("reviewStatus"), str) else ""
    if not path.is_file():
        review_status = "missing"
    elif old_status == "approved" and old_hash == content_hash:
        review_status = "approved"
    elif old_status == "approved" and old_hash and old_hash != content_hash:
        review_status = "stale"
    else:
        review_status = old_status if old_status in {"draft", "needs_update"} else "draft"
    return {
        "id": doc["id"],
        "title": doc.get("title", doc["id"]),
        "path": rel_path,
        "reviewStatus": review_status,
        "contentHash": content_hash if review_status == "approved" else old_hash,
        "generatedAt": existing.get("generatedAt"),
        "approvedAt": existing.get("approvedAt") if review_status == "approved" else None,
        "approvedBy": existing.get("approvedBy") if review_status == "approved" else None,
    }


def _load_config(root: Path) -> dict:
    config = _read_json(root / CONFIG_PATH)
    return config if config else _default_config()


def _load_profile(root: Path) -> dict:
    return _read_json(root / PROFILE_PATH)


def _build_profile(root: Path, config: dict) -> dict:
    previous = _load_profile(root)
    previous_docs = {
        item.get("id"): item
        for item in previous.get("documents", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    return {
        "version": 1,
        "updatedAt": _utc_now(),
        "documents": [
            _profile_document(root, doc, previous_docs.get(doc["id"]))
            for doc in _document_from_config(config)
        ],
        "review": {
            "openQuestionsCount": previous.get("review", {}).get("openQuestionsCount", 0),
            "highPriorityOpenQuestionsCount": previous.get("review", {}).get("highPriorityOpenQuestionsCount", 0),
        },
    }


def _replace_managed_block(content: str, block: str) -> str:
    if BLOCK_START in content and BLOCK_END in content:
        before = content.split(BLOCK_START, 1)[0].rstrip()
        after = content.split(BLOCK_END, 1)[1].lstrip()
        pieces = [before, block.strip(), after]
        return "\n\n".join(piece for piece in pieces if piece) + "\n"
    sep = "\n\n" if content.strip() else ""
    return content.rstrip() + sep + block.strip() + "\n"


def _docs_index_block() -> str:
    return f"""\
{BLOCK_START}
## 项目知识文档

| 文档 | 用途 |
| --- | --- |
| `docs/standards/project-guide.md` | 项目架构、模块职责和开发入口 |
| `docs/standards/api/` | 接口索引和接口详情 |
{BLOCK_END}
"""


def _standards_index_block(config: dict) -> str:
    rows = [
        f"| `{doc['output']}` | {doc.get('description', doc.get('title', doc['id']))} |"
        for doc in _document_from_config(config)
    ]
    return "\n".join(
        [
            BLOCK_START,
            "## 项目知识文档",
            "",
            "| 文档 | 用途 |",
            "| --- | --- |",
            *rows,
            BLOCK_END,
            "",
        ]
    )


def _update_index(path: Path, block: str, default_title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text(encoding="utf-8") if path.is_file() else f"# {default_title}\n"
    path.write_text(_replace_managed_block(content, block), encoding="utf-8")


def _ensure_dirs(root: Path, config: dict) -> None:
    (root / ".harness" / "analysis" / "latest").mkdir(parents=True, exist_ok=True)
    for doc in _document_from_config(config):
        (root / doc["output"]).parent.mkdir(parents=True, exist_ok=True)


def cmd_init_config(args: argparse.Namespace) -> int:
    root = _find_project_root()
    config_path = root / CONFIG_PATH
    config = _load_config(root)
    _ensure_dirs(root, config)
    if not config_path.is_file():
        _write_json(config_path, config)
    else:
        _write_json(config_path, config)
    _write_json(root / PROFILE_PATH, _build_profile(root, config))
    _update_index(root / "docs" / "index.md", _docs_index_block(), "文档索引")
    _update_index(root / "docs" / "standards" / "index.md", _standards_index_block(config), "团队工程规范索引")
    print(f"Project documentation config initialized: {CONFIG_PATH}")
    return 0


def _summarize(profile: dict) -> dict:
    summary = {"total": 0, "missing": 0, "draft": 0, "approved": 0, "needs_update": 0, "stale": 0}
    for doc in profile.get("documents", []):
        if not isinstance(doc, dict):
            continue
        summary["total"] += 1
        status = doc.get("reviewStatus", "draft")
        if status not in summary:
            summary[status] = 0
        summary[status] += 1
    return summary


def cmd_status(args: argparse.Namespace) -> int:
    root = _find_project_root()
    initialized = (root / CONFIG_PATH).is_file() and (root / PROFILE_PATH).is_file()
    config = _load_config(root)
    profile = _build_profile(root, config)
    if initialized:
        _write_json(root / PROFILE_PATH, profile)
    output = {
        "initialized": initialized,
        "summary": _summarize(profile),
        "documents": profile["documents"],
    }
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    print("Project documentation status:")
    for doc in profile["documents"]:
        print(f"  {doc['reviewStatus']}: {doc['path']}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    root = _find_project_root()
    config = _load_config(root)
    profile = _build_profile(root, config)
    approved_by = args.approved_by or "local"
    targets = {doc["id"] for doc in profile["documents"]} if args.all else set(args.document or [])
    if not targets:
        print("Error: use --all or --document <id>", file=sys.stderr)
        return 2
    now = _utc_now()
    changed = 0
    for doc in profile["documents"]:
        if doc["id"] not in targets:
            continue
        path = root / doc["path"]
        if not path.is_file():
            doc["reviewStatus"] = "missing"
            continue
        doc["reviewStatus"] = "approved"
        doc["contentHash"] = _sha256_file(path)
        doc["approvedAt"] = now
        doc["approvedBy"] = approved_by
        if not doc.get("generatedAt"):
            doc["generatedAt"] = now
        changed += 1
    profile["updatedAt"] = now
    _write_json(root / PROFILE_PATH, profile)
    print(f"Approved project documents: {changed}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage harness project documentation")
    subparsers = parser.add_subparsers(dest="command")

    docs = subparsers.add_parser("docs", help="Manage project documentation")
    docs_subparsers = docs.add_subparsers(dest="docs_command")

    init_config = docs_subparsers.add_parser("init-config", help="Create project documentation config")
    init_config.set_defaults(func=cmd_init_config)

    status = docs_subparsers.add_parser("status", help="Show project documentation status")
    status.add_argument("--json", action="store_true", help="Print JSON output")
    status.set_defaults(func=cmd_status)

    approve = docs_subparsers.add_parser("approve", help="Approve generated project documentation")
    approve.add_argument("--all", action="store_true", help="Approve every existing configured document")
    approve.add_argument("--document", action="append", help="Approve one configured document id")
    approve.add_argument("--approved-by", default="local", help="Reviewer name recorded in profile")
    approve.set_defaults(func=cmd_approve)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
