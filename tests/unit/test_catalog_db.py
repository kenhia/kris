"""Unit tests for catalog database initialization, WAL mode, and schema creation."""

from __future__ import annotations

import sqlite3

import pytest

from kris.catalog.db import SCHEMA_VERSION, connect, get_connection, initialize_schema


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


class TestConnect:
    def test_creates_database_file(self, db_path):
        conn = connect(db_path)
        conn.close()
        assert db_path.exists()

    def test_creates_parent_directories(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "c" / "test.db"
        conn = connect(deep_path)
        conn.close()
        assert deep_path.exists()

    def test_wal_mode_enabled(self, db_path):
        conn = connect(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_foreign_keys_enabled(self, db_path):
        conn = connect(db_path)
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()
        assert fk == 1

    def test_busy_timeout_set(self, db_path):
        conn = connect(db_path)
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        conn.close()
        assert timeout == 5000

    def test_row_factory_is_row(self, db_path):
        conn = connect(db_path)
        assert conn.row_factory is sqlite3.Row
        conn.close()


class TestInitializeSchema:
    def test_creates_all_tables(self, db_path):
        conn = connect(db_path)
        initialize_schema(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        expected = {
            "source",
            "scan_schedule",
            "file",
            "content",
            "task",
            "chunk",
            "embedding",
            "model_registry",
            "schema_version",
        }
        assert tables == expected
        conn.close()

    def test_creates_indexes(self, db_path):
        conn = connect(db_path)
        initialize_schema(conn)
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
        }
        expected = {
            "idx_file_source",
            "idx_file_content_hash",
            "idx_file_processing",
            "idx_file_visibility",
            "idx_content_status",
            "idx_task_status",
            "idx_task_content",
            "idx_chunk_content",
            "idx_embedding_chunk",
            "idx_embedding_model",
        }
        assert indexes == expected
        conn.close()

    def test_schema_version_recorded(self, db_path):
        conn = connect(db_path)
        initialize_schema(conn)
        version = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()[0]
        assert version == SCHEMA_VERSION
        conn.close()

    def test_idempotent(self, db_path):
        conn = connect(db_path)
        initialize_schema(conn)
        initialize_schema(conn)
        version_count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        assert version_count == 1
        conn.close()


class TestGetConnection:
    def test_returns_initialized_connection(self, db_path):
        conn = get_connection(db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert "source" in tables
        assert "file" in tables
        conn.close()

    def test_wal_mode(self, db_path):
        conn = get_connection(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()
