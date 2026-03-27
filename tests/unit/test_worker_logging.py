"""Unit tests for worker log batching (US5 — Quiet Logs)."""

from __future__ import annotations

import json
import logging
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from kris.catalog.db import get_connection
from kris.processing.worker import LOG_BATCH_INTERVAL, run_worker


@pytest.fixture
def worker_db(tmp_path):
    """Minimal DB with queued tasks."""
    db_path = tmp_path / "worker-log-test.db"
    conn = get_connection(db_path)

    conn.execute(
        "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
        ("src", "Test", "local", "/tmp/test"),
    )

    yield conn
    conn.close()


def _add_file_and_tasks(conn: sqlite3.Connection, idx: int) -> str:
    """Insert a file + content + extract/chunk/embed tasks. Returns content_hash."""
    ch = f"hash-{idx:04d}"
    conn.execute(
        "INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind, "
        "processing_status, visibility) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (f"f-{idx}", "src", ch, f"file{idx}.txt", 100, 1000, "text", "pending", "active"),
    )
    conn.execute(
        "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
        (ch, "pending"),
    )
    for i, ttype in enumerate(["extract", "chunk", "embed"]):
        tid = f"t-{idx}-{i}"
        dep = json.dumps([f"t-{idx}-{i - 1}"]) if i > 0 else None
        conn.execute(
            "INSERT INTO task (id, content_hash, task_type, status, depends_on) "
            "VALUES (?, ?, ?, ?, ?)",
            (tid, ch, ttype, "queued", dep),
        )
    conn.commit()
    return ch


class TestLogBatchInterval:
    """T051 — Per-file messages are DEBUG, batch summary is INFO every LOG_BATCH_INTERVAL items."""

    def test_batch_interval_is_defined(self):
        assert LOG_BATCH_INTERVAL == 3000

    def test_per_file_messages_are_debug(self, worker_db, tmp_path, caplog):
        """Per-file extract/chunk/embed log lines should be at DEBUG level."""
        _add_file_and_tasks(worker_db, 0)
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        qdrant_path = tmp_path / "qdrant"

        mock_manager = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock(model_id="embedding")

        with (
            caplog.at_level(logging.DEBUG, logger="kris.processing.worker"),
            patch("kris.processing.worker.extract_for_content") as mock_extract,
            patch("kris.processing.worker.chunk_text", return_value=[]),
            patch("kris.processing.worker.save_chunks", return_value=0),
            patch("kris.processing.worker.embed_chunks", return_value=0),
            patch("kris.processing.worker.create_qdrant_client"),
        ):
            mock_extract.return_value = MagicMock(text="hello", size=5)
            run_worker(worker_db, data_dir, qdrant_path, mock_manager, mock_registry)

        # Per-file messages should be DEBUG, not INFO
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]

        # Per-file "Extracted", "Created", "Embedded" should be DEBUG
        for r in debug_records:
            if any(kw in r.message for kw in ("Extracted", "Created", "Embedded")):
                assert r.levelno == logging.DEBUG

        # Per-file messages should NOT be at INFO
        per_file_info = [
            r
            for r in info_records
            if any(kw in r.message for kw in ("Extracted", "Created", "Embedded"))
            and "hash-" in r.message
        ]
        assert len(per_file_info) == 0, f"Per-file messages should not be INFO: {per_file_info}"


class TestFinalSummary:
    """T052 — Final summary log at worker completion."""

    def test_final_summary_emitted(self, worker_db, tmp_path, caplog):
        _add_file_and_tasks(worker_db, 0)
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        qdrant_path = tmp_path / "qdrant"

        mock_manager = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = MagicMock(model_id="embedding")

        with (
            caplog.at_level(logging.DEBUG, logger="kris.processing.worker"),
            patch("kris.processing.worker.extract_for_content") as mock_extract,
            patch("kris.processing.worker.chunk_text", return_value=[]),
            patch("kris.processing.worker.save_chunks", return_value=0),
            patch("kris.processing.worker.embed_chunks", return_value=0),
            patch("kris.processing.worker.create_qdrant_client"),
        ):
            mock_extract.return_value = MagicMock(text="hello", size=5)
            run_worker(worker_db, data_dir, qdrant_path, mock_manager, mock_registry)

        # There should be a final summary at INFO level
        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        summary_msgs = [
            m for m in info_messages if "completed" in m.lower() or "total" in m.lower()
        ]
        assert len(summary_msgs) >= 1, f"Expected final summary INFO: {info_messages}"
