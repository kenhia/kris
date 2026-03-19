"""Shared test fixtures for kris tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from kris.catalog.db import get_connection


@pytest.fixture
def db_path(tmp_path):
    """Path to a temporary SQLite database."""
    return tmp_path / "test-catalog.db"


@pytest.fixture
def db(db_path) -> Generator:
    """Initialized SQLite connection with schema."""
    conn = get_connection(db_path)
    yield conn
    conn.close()


@pytest.fixture
def sample_source(db) -> str:
    """Insert a sample source and return its ID."""
    source_id = "test-source"
    db.execute(
        "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
        (source_id, "Test Source", "local", "/tmp/test-data"),
    )
    db.commit()
    return source_id


@pytest.fixture
def sample_file_tree(tmp_path):
    """Create a sample directory tree with various file types."""
    root = tmp_path / "test-data"
    root.mkdir()

    (root / "readme.md").write_text("# Hello\n\nThis is a test.", encoding="utf-8")
    (root / "main.py").write_text('print("hello world")\n', encoding="utf-8")
    (root / "config.toml").write_text('[settings]\nkey = "value"\n', encoding="utf-8")
    (root / "notes.txt").write_text("Some plain text notes.\n", encoding="utf-8")

    subdir = root / "src"
    subdir.mkdir()
    (subdir / "lib.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    return root
