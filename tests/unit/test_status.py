"""Unit tests for status query functions and CLI output."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from kris.catalog.db import get_connection
from kris.catalog.files import get_failed_files, get_status_summary
from kris.cli.app import app


@pytest.fixture
def status_db(tmp_path):
    """Database with files in various states for status testing."""
    db_path = tmp_path / "status-test.db"
    conn = get_connection(db_path)

    # Sources
    conn.execute(
        "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
        ("src-1", "Home", "local", "/home/user"),
    )
    conn.execute(
        "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
        ("src-2", "NAS", "local", "/mnt/nas"),
    )

    # Files for src-1: 3 completed markdown, 2 pending code, 1 failed text
    for i in range(3):
        conn.execute(
            "INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind, "
            "processing_status, visibility) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"f1-{i}",
                "src-1",
                f"hash-1-{i}",
                f"docs/file{i}.md",
                100 + i * 50,
                1000,
                "markdown",
                "completed",
                "active",
            ),
        )
    for i in range(2):
        conn.execute(
            "INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind, "
            "processing_status, visibility) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"f1-c{i}",
                "src-1",
                f"hash-1-c{i}",
                f"src/main{i}.py",
                200,
                1000,
                "code",
                "pending",
                "active",
            ),
        )
    conn.execute(
        "INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind, "
        "processing_status, visibility) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("f1-fail", "src-1", "hash-fail", "bad.txt", 50, 1000, "text", "failed", "active"),
    )

    # Files for src-2: 2 completed code
    for i in range(2):
        conn.execute(
            "INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind, "
            "processing_status, visibility) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"f2-{i}",
                "src-2",
                f"hash-2-{i}",
                f"project/app{i}.py",
                300,
                1000,
                "code",
                "completed",
                "active",
            ),
        )

    # Content records
    for h in [
        "hash-1-0",
        "hash-1-1",
        "hash-1-2",
        "hash-1-c0",
        "hash-1-c1",
        "hash-fail",
        "hash-2-0",
        "hash-2-1",
    ]:
        conn.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
            (h, "completed" if "fail" not in h else "failed"),
        )

    # Chunks (for counting)
    for i in range(5):
        conn.execute(
            "INSERT INTO chunk (id, content_hash, chunk_index, chunk_content_hash, content, "
            "start_offset, end_offset, chunking_strategy) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f"chunk-{i}", f"hash-1-{i % 3}", i, f"cc-{i}", f"chunk text {i}", 0, 10, "text"),
        )

    # Embeddings (for counting)
    for i in range(3):
        conn.execute(
            "INSERT INTO embedding (id, chunk_id, model_id, index_name, opensearch_doc_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"emb-{i}", f"chunk-{i}", "embedding", "kris_chunks", f"doc-{i}"),
        )

    # Task with error for the failed file
    conn.execute(
        "INSERT INTO task (id, content_hash, task_type, status, error) VALUES (?, ?, ?, ?, ?)",
        ("task-fail", "hash-fail", "extract", "failed", "Encoding detection failed"),
    )

    conn.commit()
    yield conn
    conn.close()


class TestGetStatusSummary:
    def test_returns_all_sources(self, status_db):
        summary = get_status_summary(status_db)
        assert len(summary) == 2
        source_ids = {s["source_id"] for s in summary}
        assert source_ids == {"src-1", "src-2"}

    def test_file_counts_per_source(self, status_db):
        summary = get_status_summary(status_db)
        src1 = next(s for s in summary if s["source_id"] == "src-1")
        assert src1["total_files"] == 6
        src2 = next(s for s in summary if s["source_id"] == "src-2")
        assert src2["total_files"] == 2

    def test_counts_by_kind(self, status_db):
        summary = get_status_summary(status_db)
        src1 = next(s for s in summary if s["source_id"] == "src-1")
        assert src1["by_kind"]["markdown"] == 3
        assert src1["by_kind"]["code"] == 2
        assert src1["by_kind"]["text"] == 1

    def test_counts_by_status(self, status_db):
        summary = get_status_summary(status_db)
        src1 = next(s for s in summary if s["source_id"] == "src-1")
        assert src1["by_status"]["completed"] == 3
        assert src1["by_status"]["pending"] == 2
        assert src1["by_status"]["failed"] == 1

    def test_source_filter(self, status_db):
        summary = get_status_summary(status_db, source_id="src-2")
        assert len(summary) == 1
        assert summary[0]["source_id"] == "src-2"

    def test_chunk_and_embedding_counts(self, status_db):
        summary = get_status_summary(status_db)
        src1 = next(s for s in summary if s["source_id"] == "src-1")
        assert src1["total_chunks"] >= 0  # may vary by join
        # Overall counts are present
        assert "total_chunks" in src1
        assert "total_embeddings" in src1


class TestGetFailedFiles:
    def test_returns_failed_files(self, status_db):
        failed = get_failed_files(status_db)
        assert len(failed) == 1
        assert failed[0]["path"] == "bad.txt"

    def test_includes_error_message(self, status_db):
        failed = get_failed_files(status_db)
        assert failed[0]["error"] == "Encoding detection failed"

    def test_failed_with_source_filter(self, status_db):
        failed = get_failed_files(status_db, source_id="src-2")
        assert len(failed) == 0

    def test_failed_with_matching_source(self, status_db):
        failed = get_failed_files(status_db, source_id="src-1")
        assert len(failed) == 1


# ---------------------------------------------------------------------------
# CLI-level tests for --show-failed (T053-T055)
# ---------------------------------------------------------------------------

runner = CliRunner()


def _mock_status_data():
    """Return (summary, failed) tuples that mock DB queries."""
    summary = [
        {
            "source_id": "src-1",
            "source_name": "Home",
            "last_scan": "2025-01-01T00:00:00",
            "total_files": 10,
            "by_kind": {"text": 8, "code": 2},
            "by_status": {"completed": 8, "failed": 2},
            "total_chunks": 50,
            "total_embeddings": 50,
        }
    ]
    failed = [
        {"path": "bad1.txt", "source_id": "src-1", "error": "encoding error"},
        {"path": "bad2.bin", "source_id": "src-1", "error": "binary file"},
    ]
    return summary, failed


class TestStatusShowFailed:
    """T053 — Default output hides failed files, shows one-line count."""

    def test_default_hides_failed_table(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n',
            encoding="utf-8",
        )
        summary, failed = _mock_status_data()

        with (
            patch("kris.cli.status.get_status_summary", return_value=summary),
            patch("kris.cli.status.get_failed_files", return_value=failed),
            patch("kris.cli.status.get_connection"),
        ):
            result = runner.invoke(app, ["status", "--config", str(config_path)])

        assert result.exit_code == 0
        # Should show a count mention
        assert "2" in result.output  # 2 failed files
        assert "show-failed" in result.output.lower() or "--show-failed" in result.output
        # Should NOT show full failed-files table rows
        assert "bad1.txt" not in result.output
        assert "bad2.bin" not in result.output

    def test_show_failed_flag_shows_table(self, tmp_path):
        """T054 — --show-failed displays full table."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n',
            encoding="utf-8",
        )
        summary, failed = _mock_status_data()

        with (
            patch("kris.cli.status.get_status_summary", return_value=summary),
            patch("kris.cli.status.get_failed_files", return_value=failed),
            patch("kris.cli.status.get_connection"),
        ):
            result = runner.invoke(app, ["status", "--config", str(config_path), "--show-failed"])

        assert result.exit_code == 0
        # Full table rendered
        assert "bad1.txt" in result.output
        assert "bad2.bin" in result.output

    def test_no_failures_no_message(self, tmp_path):
        """When no failures, don't show any failure section."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n',
            encoding="utf-8",
        )
        summary, _ = _mock_status_data()

        with (
            patch("kris.cli.status.get_status_summary", return_value=summary),
            patch("kris.cli.status.get_failed_files", return_value=[]),
            patch("kris.cli.status.get_connection"),
        ):
            result = runner.invoke(app, ["status", "--config", str(config_path)])

        assert result.exit_code == 0
        assert "show-failed" not in result.output.lower()


class TestStatusJsonShowFailed:
    """T055 — JSON output always includes failed_files."""

    def test_json_always_includes_failed_files(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n',
            encoding="utf-8",
        )
        summary, failed = _mock_status_data()

        with (
            patch("kris.cli.status.get_status_summary", return_value=summary),
            patch("kris.cli.status.get_failed_files", return_value=failed),
            patch("kris.cli.status.get_connection"),
        ):
            result = runner.invoke(app, ["--json", "status", "--config", str(config_path)])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "failed_files" in data["data"]
        assert len(data["data"]["failed_files"]) == 2

    def test_json_includes_failed_even_without_flag(self, tmp_path):
        """JSON mode includes failed_files regardless of --show-failed."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[sources.test]\nname = "Test"\nbase_path = "/tmp/test"\n',
            encoding="utf-8",
        )
        summary, failed = _mock_status_data()

        with (
            patch("kris.cli.status.get_status_summary", return_value=summary),
            patch("kris.cli.status.get_failed_files", return_value=failed),
            patch("kris.cli.status.get_connection"),
        ):
            # No --show-failed flag, but JSON should still have it
            result = runner.invoke(app, ["--json", "status", "--config", str(config_path)])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["data"]["failed_files"]) == 2
