"""SQLite database connection management and schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_MVP_DDL = """\
CREATE TABLE IF NOT EXISTS source (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'local',
    base_path   TEXT NOT NULL,
    config      TEXT,
    last_scan   TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scan_schedule (
    id               TEXT PRIMARY KEY,
    source_id        TEXT NOT NULL REFERENCES source(id),
    path_pattern     TEXT NOT NULL DEFAULT '**',
    interval_minutes INTEGER NOT NULL DEFAULT 60,
    priority         INTEGER NOT NULL DEFAULT 100,
    last_run         TEXT,
    next_run         TEXT
);

CREATE TABLE IF NOT EXISTS file (
    id                TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL REFERENCES source(id),
    content_hash      TEXT NOT NULL,
    path              TEXT NOT NULL,
    size              INTEGER NOT NULL,
    mtime             INTEGER NOT NULL,
    file_kind         TEXT NOT NULL,
    mime_type         TEXT,
    processing_status TEXT NOT NULL DEFAULT 'pending',
    visibility        TEXT NOT NULL DEFAULT 'active',
    first_seen        TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen         TEXT NOT NULL DEFAULT (datetime('now')),
    disappeared_at    TEXT,
    permissions       INTEGER,
    UNIQUE(source_id, path)
);

CREATE TABLE IF NOT EXISTS content (
    content_hash      TEXT PRIMARY KEY,
    parent_content_hash TEXT,
    processing_status TEXT NOT NULL DEFAULT 'pending',
    last_processed    TEXT
);

CREATE TABLE IF NOT EXISTS task (
    id            TEXT PRIMARY KEY,
    content_hash  TEXT NOT NULL REFERENCES content(content_hash),
    task_type     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'queued',
    model_hint    TEXT,
    priority      INTEGER NOT NULL DEFAULT 100,
    depends_on    TEXT,
    attempts      INTEGER NOT NULL DEFAULT 0,
    max_attempts  INTEGER NOT NULL DEFAULT 3,
    error         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    started_at    TEXT,
    completed_at  TEXT
);

CREATE TABLE IF NOT EXISTS chunk (
    id                 TEXT PRIMARY KEY,
    content_hash       TEXT NOT NULL REFERENCES content(content_hash),
    chunk_index        INTEGER NOT NULL,
    chunk_content_hash TEXT NOT NULL,
    content            TEXT NOT NULL,
    start_offset       INTEGER NOT NULL,
    end_offset         INTEGER NOT NULL,
    chunking_strategy  TEXT NOT NULL,
    metadata           TEXT,
    UNIQUE(content_hash, chunk_index)
);

CREATE TABLE IF NOT EXISTS embedding (
    id              TEXT PRIMARY KEY,
    chunk_id        TEXT NOT NULL REFERENCES chunk(id),
    model_id        TEXT NOT NULL,
    index_name      TEXT NOT NULL,
    opensearch_doc_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_registry (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    model_type         TEXT NOT NULL,
    model_path_or_repo TEXT NOT NULL,
    dimensions         INTEGER,
    vram_gb            REAL NOT NULL,
    config             TEXT
);

CREATE INDEX IF NOT EXISTS idx_file_source ON file(source_id);
CREATE INDEX IF NOT EXISTS idx_file_content_hash ON file(content_hash);
CREATE INDEX IF NOT EXISTS idx_file_processing ON file(processing_status);
CREATE INDEX IF NOT EXISTS idx_file_visibility ON file(visibility);
CREATE INDEX IF NOT EXISTS idx_content_status ON content(processing_status);
CREATE INDEX IF NOT EXISTS idx_task_status ON task(status);
CREATE INDEX IF NOT EXISTS idx_task_content ON task(content_hash);
CREATE INDEX IF NOT EXISTS idx_chunk_content ON chunk(content_hash);
CREATE INDEX IF NOT EXISTS idx_embedding_chunk ON embedding(chunk_id);
CREATE INDEX IF NOT EXISTS idx_embedding_model ON embedding(model_id);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode, busy_timeout, and foreign keys."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Create all MVP tables and indexes if they don't exist."""
    conn.executescript(_MVP_DDL)
    _migrate_embedding_columns(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    existing = conn.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    ).fetchone()
    if existing is None or existing[0] < SCHEMA_VERSION:
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()


def _migrate_embedding_columns(conn: sqlite3.Connection) -> None:
    """Rename legacy Qdrant column names to OpenSearch names (idempotent)."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(embedding)").fetchall()}
    if "qdrant_point_id" in columns:
        conn.execute("ALTER TABLE embedding RENAME COLUMN qdrant_point_id TO opensearch_doc_id")
    if "collection_name" in columns:
        conn.execute("ALTER TABLE embedding RENAME COLUMN collection_name TO index_name")
    conn.commit()


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection and ensure the schema is initialized."""
    conn = connect(db_path)
    initialize_schema(conn)
    return conn
