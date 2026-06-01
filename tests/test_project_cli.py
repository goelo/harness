"""Tests for .harness/scripts/project.py project documentation state."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
PROJECT_SCRIPT = REPO_ROOT / "harness_scripts" / "project.py"


def _copy_project_script(project_dir: Path) -> None:
    scripts = project_dir / ".harness" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_SCRIPT, scripts / "project.py")


def _run_project(project_dir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, ".harness/scripts/project.py", *args],
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env=os.environ.copy(),
    )


class ProjectCliTestCase(unittest.TestCase):
    def setUp(self):
        self.project_dir = Path(tempfile.mkdtemp())
        (self.project_dir / ".harness").mkdir(parents=True)
        _copy_project_script(self.project_dir)

    def tearDown(self):
        shutil.rmtree(self.project_dir)

    def write_project_docs(self) -> None:
        docs = {
            "docs/standards/project-guide.md": "# 项目说明\n\n核心业务说明。\n",
            "docs/standards/api/url-index.md": "# 接口索引\n\nGET /api/orders\n",
            "docs/standards/api/detail.md": "# 接口详情\n\nGET /api/orders 返回订单列表。\n",
        }
        for rel_path, content in docs.items():
            path = self.project_dir / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


class TestProjectDocsInit(ProjectCliTestCase):
    def test_init_config_creates_project_docs_state_and_indexes(self):
        result = _run_project(self.project_dir, "docs", "init-config")
        self.assertEqual(result.returncode, 0, result.stderr)

        config_path = self.project_dir / ".harness" / "project-docs.json"
        profile_path = self.project_dir / ".harness" / "project-profile.json"
        self.assertTrue(config_path.is_file())
        self.assertTrue(profile_path.is_file())
        self.assertTrue((self.project_dir / "docs" / "standards" / "api").is_dir())

        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["preset"], "default")
        self.assertEqual(config["analysis"]["cacheDir"], ".harness/analysis/latest")
        self.assertFalse(config["analysis"]["keepHistory"])
        outputs = [item["output"] for item in config["documents"]]
        self.assertEqual(
            outputs,
            [
                "docs/standards/project-guide.md",
                "docs/standards/api/url-index.md",
                "docs/standards/api/detail.md",
            ],
        )

        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        self.assertEqual(profile["documents"][0]["reviewStatus"], "missing")
        self.assertEqual(profile["documents"][0]["path"], "docs/standards/project-guide.md")

    def test_init_config_preserves_existing_index_content_and_updates_managed_blocks(self):
        docs = self.project_dir / "docs"
        standards = docs / "standards"
        standards.mkdir(parents=True)
        (docs / "index.md").write_text("# Existing Docs\n\n业务文档说明。\n", encoding="utf-8")
        (standards / "index.md").write_text("# Existing Standards\n\n团队规范说明。\n", encoding="utf-8")

        result = _run_project(self.project_dir, "docs", "init-config")
        self.assertEqual(result.returncode, 0, result.stderr)

        docs_index = (docs / "index.md").read_text(encoding="utf-8")
        standards_index = (standards / "index.md").read_text(encoding="utf-8")
        self.assertIn("业务文档说明", docs_index)
        self.assertIn("团队规范说明", standards_index)
        self.assertEqual(docs_index.count("<!-- harness-project-docs:start -->"), 1)
        self.assertEqual(standards_index.count("<!-- harness-project-docs:start -->"), 1)
        self.assertIn("docs/standards/project-guide.md", docs_index)
        self.assertIn("docs/standards/api/detail.md", standards_index)

        second = _run_project(self.project_dir, "docs", "init-config")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((docs / "index.md").read_text(encoding="utf-8").count("<!-- harness-project-docs:start -->"), 1)


class TestProjectDocsStatusAndApprove(ProjectCliTestCase):
    def test_status_json_before_init_is_read_only(self):
        result = _run_project(self.project_dir, "docs", "status", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)

        self.assertFalse(data["initialized"])
        self.assertEqual(data["summary"]["missing"], 3)
        self.assertFalse((self.project_dir / ".harness" / "project-docs.json").exists())
        self.assertFalse((self.project_dir / ".harness" / "project-profile.json").exists())

    def test_status_json_reports_missing_documents(self):
        self.assertEqual(_run_project(self.project_dir, "docs", "init-config").returncode, 0)

        result = _run_project(self.project_dir, "docs", "status", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)

        self.assertTrue(data["initialized"])
        self.assertEqual(data["summary"]["missing"], 3)
        self.assertEqual(data["summary"]["approved"], 0)
        self.assertEqual(data["documents"][0]["reviewStatus"], "missing")

    def test_approve_all_marks_existing_documents_with_hash_and_reviewer(self):
        self.assertEqual(_run_project(self.project_dir, "docs", "init-config").returncode, 0)
        self.write_project_docs()

        result = _run_project(self.project_dir, "docs", "approve", "--all", "--approved-by", "owner")
        self.assertEqual(result.returncode, 0, result.stderr)

        profile = json.loads((self.project_dir / ".harness" / "project-profile.json").read_text(encoding="utf-8"))
        for doc in profile["documents"]:
            self.assertEqual(doc["reviewStatus"], "approved")
            self.assertTrue(doc["contentHash"].startswith("sha256:"))
            self.assertEqual(doc["approvedBy"], "owner")
            self.assertIsNotNone(doc["approvedAt"])

        status = _run_project(self.project_dir, "docs", "status", "--json")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["summary"]["approved"], 3)


if __name__ == "__main__":
    unittest.main()
