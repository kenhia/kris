"""Integration test for full index flow: scan → catalog → plan → extract → chunk → embed."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from kris.catalog.content import get_duplicate_groups
from kris.catalog.db import get_connection
from kris.catalog.files import cleanup_missing_files
from kris.planner.planner import plan_pending_content
from kris.processing.chunk import chunk_markdown, chunk_text, save_chunks
from kris.processing.extract import extract_for_content
from kris.scanner import find_scanner_binary


@pytest.fixture
def scanner_binary():
    try:
        return find_scanner_binary()
    except Exception:
        pytest.skip("kris-scanner binary not built")


@pytest.fixture
def index_env(tmp_path):
    """Full index environment: database + sample files."""
    db_path = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create files of various types
    (data_dir / "readme.md").write_text(
        "# Project\n\nOverview of the project.\n\n## Usage\n\nRun the thing.\n",
        encoding="utf-8",
    )
    (data_dir / "hello.py").write_text(
        'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n',
        encoding="utf-8",
    )
    (data_dir / "notes.txt").write_text(
        "Some important notes.\n\nAnother paragraph here.\n",
        encoding="utf-8",
    )

    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
        ("src-1", "Test", "local", str(data_dir)),
    )
    conn.commit()
    conn.close()

    return {"db_path": db_path, "data_dir": data_dir}


class TestIndexFlow:
    """End-to-end: scan → plan → extract → chunk pipeline."""

    def test_scan_then_plan_creates_tasks(self, scanner_binary, index_env):
        """After scanning, planning should create extract→chunk→embed tasks."""
        subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(index_env["db_path"]),
                "--source-id",
                "src-1",
                "--base-path",
                str(index_env["data_dir"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        conn = get_connection(index_env["db_path"])
        planned = plan_pending_content(conn)
        assert planned == 3  # 3 files → 3 content records

        tasks = conn.execute("SELECT * FROM task ORDER BY priority").fetchall()
        # 3 content records x 3 task types = 9 tasks
        assert len(tasks) == 9

        types = [t["task_type"] for t in tasks]
        assert types.count("extract") == 3
        assert types.count("chunk") == 3
        assert types.count("embed") == 3
        conn.close()

    def test_extract_after_scan(self, scanner_binary, index_env):
        """After scanning, extraction should read file content correctly."""
        subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(index_env["db_path"]),
                "--source-id",
                "src-1",
                "--base-path",
                str(index_env["data_dir"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        conn = get_connection(index_env["db_path"])
        content_rows = conn.execute("SELECT content_hash FROM content").fetchall()
        assert len(content_rows) == 3

        for row in content_rows:
            result = extract_for_content(conn, row["content_hash"], index_env["data_dir"])
            assert result.size > 0
            assert result.encoding == "utf-8"
        conn.close()

    def test_chunk_after_extract(self, scanner_binary, index_env):
        """After scanning and extracting, chunking should produce chunks in the DB."""
        subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(index_env["db_path"]),
                "--source-id",
                "src-1",
                "--base-path",
                str(index_env["data_dir"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        conn = get_connection(index_env["db_path"])
        content_rows = conn.execute(
            "SELECT c.content_hash, f.file_kind FROM content c "
            "JOIN file f ON f.content_hash = c.content_hash",
        ).fetchall()

        total_chunks = 0
        for row in content_rows:
            result = extract_for_content(conn, row["content_hash"], index_env["data_dir"])
            if row["file_kind"] == "markdown":
                chunks = chunk_markdown(result.text, row["content_hash"])
            else:
                chunks = chunk_text(result.text, row["content_hash"])
            saved = save_chunks(conn, chunks)
            total_chunks += saved

        assert total_chunks > 0
        db_chunks = conn.execute("SELECT COUNT(*) FROM chunk").fetchone()[0]
        assert db_chunks == total_chunks
        conn.close()

    def test_full_flow_with_mocked_embed(self, scanner_binary, index_env):
        """Full flow scan→plan→worker with mocked embedding model."""
        from kris.processing.worker import run_worker

        # Scan
        subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(index_env["db_path"]),
                "--source-id",
                "src-1",
                "--base-path",
                str(index_env["data_dir"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        conn = get_connection(index_env["db_path"])

        # Plan
        planned = plan_pending_content(conn)
        assert planned == 3

        # Mock model infrastructure for embed tasks
        mock_model = MagicMock()
        mock_model.encode.return_value = [[0.1] * 384]  # fake embeddings
        mock_manager = MagicMock()
        mock_manager.load.return_value = mock_model

        mock_registry = MagicMock()
        mock_info = MagicMock()
        mock_info.dimensions = 384
        mock_registry.get.return_value = mock_info

        qdrant_path = index_env["data_dir"].parent / "qdrant"

        # Patch embed_chunks to avoid real Qdrant/model deps
        with patch("kris.processing.worker.embed_chunks", return_value=1):
            completed, failed = run_worker(
                conn,
                index_env["data_dir"],
                qdrant_path,
                mock_manager,
                mock_registry,
            )

        assert failed == 0
        # 9 tasks total: 3 extract + 3 chunk + 3 embed
        assert completed == 9

        # Verify all tasks completed
        remaining = conn.execute(
            "SELECT COUNT(*) FROM task WHERE status != 'completed'",
        ).fetchone()[0]
        assert remaining == 0
        conn.close()


class TestDedupFlow:
    """Integration: duplicate files across sources share content records and artifacts."""

    def test_duplicate_files_share_content(self, scanner_binary, index_env):
        """Scanning identical files in two source dirs produces shared content records."""
        data_dir = index_env["data_dir"]
        data_dir_2 = data_dir.parent / "data2"
        # Copy entire tree to second source
        shutil.copytree(data_dir, data_dir_2)

        db_path = index_env["db_path"]
        conn = get_connection(db_path)
        conn.execute(
            "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
            ("src-2", "Test 2", "local", str(data_dir_2)),
        )
        conn.commit()
        conn.close()

        # Scan both sources
        for src_id, base in [("src-1", data_dir), ("src-2", data_dir_2)]:
            subprocess.run(
                [
                    str(scanner_binary),
                    "--db",
                    str(db_path),
                    "--source-id",
                    src_id,
                    "--base-path",
                    str(base),
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

        conn = get_connection(db_path)

        # Files are doubled (3 per source)
        file_count = conn.execute("SELECT COUNT(*) FROM file").fetchone()[0]
        assert file_count == 6

        # Content records should NOT be doubled — INSERT OR IGNORE deduplicates
        content_count = conn.execute("SELECT COUNT(*) FROM content").fetchone()[0]
        assert content_count == 3  # only 3 unique content hashes

        # Planning should only create tasks once per content_hash
        planned = plan_pending_content(conn)
        assert planned == 3  # not 6

        task_count = conn.execute("SELECT COUNT(*) FROM task").fetchone()[0]
        assert task_count == 9  # 3 content x 3 task types

        # Duplicate groups should show 3 groups of 2
        groups = get_duplicate_groups(conn)
        assert len(groups) == 3
        for g in groups:
            assert g["count"] == 2

        conn.close()


class TestArchiveFlow:
    """Integration: delete file -> re-index -> verify missing -> cleanup."""

    def test_deleted_file_becomes_missing(self, scanner_binary, index_env):
        """After deleting a file and re-scanning, it's marked as missing."""
        data_dir = index_env["data_dir"]
        db_path = index_env["db_path"]

        # First scan
        subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(db_path),
                "--source-id",
                "src-1",
                "--base-path",
                str(data_dir),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        conn = get_connection(db_path)
        initial_count = conn.execute(
            "SELECT COUNT(*) FROM file WHERE visibility = 'active'"
        ).fetchone()[0]
        assert initial_count == 3
        conn.close()

        # Delete a file
        os.remove(data_dir / "notes.txt")

        # Wait for timestamp to advance (scanner uses second-level resolution)
        time.sleep(1.1)

        # Re-scan
        subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(db_path),
                "--source-id",
                "src-1",
                "--base-path",
                str(data_dir),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        conn = get_connection(db_path)
        active_count = conn.execute(
            "SELECT COUNT(*) FROM file WHERE visibility = 'active'"
        ).fetchone()[0]
        missing_count = conn.execute(
            "SELECT COUNT(*) FROM file WHERE visibility = 'missing'"
        ).fetchone()[0]
        assert active_count == 2
        assert missing_count == 1

        # Verify the missing file is notes.txt
        missing = conn.execute("SELECT path FROM file WHERE visibility = 'missing'").fetchone()
        assert "notes.txt" in missing["path"]
        conn.close()

    def test_cleanup_removes_missing_files(self, scanner_binary, index_env):
        """After marking files missing, cleanup removes them."""
        data_dir = index_env["data_dir"]
        db_path = index_env["db_path"]

        # Scan, delete, re-scan
        for _i in range(2):
            subprocess.run(
                [
                    str(scanner_binary),
                    "--db",
                    str(db_path),
                    "--source-id",
                    "src-1",
                    "--base-path",
                    str(data_dir),
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            if _i == 0:
                os.remove(data_dir / "notes.txt")
                time.sleep(1.1)  # scanner uses second-level timestamps

        conn = get_connection(db_path)
        result = cleanup_missing_files(conn)
        assert result["files_removed"] == 1

        total = conn.execute("SELECT COUNT(*) FROM file").fetchone()[0]
        assert total == 2  # only active files remain
        conn.close()
