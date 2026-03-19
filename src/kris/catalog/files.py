"""File CRUD operations for the catalog."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime

from kris.catalog.models import File


def _row_to_file(row: sqlite3.Row) -> File:
    return File(
        id=row["id"],
        source_id=row["source_id"],
        content_hash=row["content_hash"],
        path=row["path"],
        size=row["size"],
        mtime=row["mtime"],
        file_kind=row["file_kind"],
        mime_type=row["mime_type"],
        processing_status=row["processing_status"],
        visibility=row["visibility"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        disappeared_at=row["disappeared_at"],
        permissions=row["permissions"],
    )


def insert_file(conn: sqlite3.Connection, file: File) -> File:
    """Insert a new file record."""
    if not file.id:
        file.id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO file
           (id, source_id, content_hash, path, size, mtime, file_kind,
            mime_type, processing_status, visibility, permissions)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            file.id,
            file.source_id,
            file.content_hash,
            file.path,
            file.size,
            file.mtime,
            file.file_kind,
            file.mime_type,
            file.processing_status,
            file.visibility,
            file.permissions,
        ),
    )
    conn.commit()
    return file


def upsert_file(conn: sqlite3.Connection, file: File) -> File:
    """Insert or update a file record (keyed on source_id + path).

    On conflict, updates content_hash, size, mtime, file_kind, mime_type,
    processing_status, visibility, last_seen, and permissions.
    """
    if not file.id:
        file.id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """INSERT INTO file
           (id, source_id, content_hash, path, size, mtime, file_kind,
            mime_type, processing_status, visibility, last_seen, permissions)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(source_id, path) DO UPDATE SET
               content_hash = excluded.content_hash,
               size = excluded.size,
               mtime = excluded.mtime,
               file_kind = excluded.file_kind,
               mime_type = excluded.mime_type,
               processing_status = excluded.processing_status,
               visibility = excluded.visibility,
               last_seen = excluded.last_seen,
               permissions = excluded.permissions""",
        (
            file.id,
            file.source_id,
            file.content_hash,
            file.path,
            file.size,
            file.mtime,
            file.file_kind,
            file.mime_type,
            file.processing_status,
            file.visibility,
            now,
            file.permissions,
        ),
    )
    conn.commit()
    return file


def get_file_by_id(conn: sqlite3.Connection, file_id: str) -> File | None:
    """Get a file by its ID."""
    row = conn.execute("SELECT * FROM file WHERE id = ?", (file_id,)).fetchone()
    return _row_to_file(row) if row else None


def get_files_by_source(
    conn: sqlite3.Connection,
    source_id: str,
    visibility: str | None = None,
) -> list[File]:
    """List files for a source, optionally filtered by visibility."""
    if visibility:
        rows = conn.execute(
            "SELECT * FROM file WHERE source_id = ? AND visibility = ?",
            (source_id, visibility),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM file WHERE source_id = ?", (source_id,)).fetchall()
    return [_row_to_file(r) for r in rows]


def get_files_by_status(
    conn: sqlite3.Connection,
    processing_status: str,
    source_id: str | None = None,
) -> list[File]:
    """List files by processing status, optionally filtered by source."""
    if source_id:
        rows = conn.execute(
            "SELECT * FROM file WHERE processing_status = ? AND source_id = ?",
            (processing_status, source_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM file WHERE processing_status = ?",
            (processing_status,),
        ).fetchall()
    return [_row_to_file(r) for r in rows]


def get_files_by_kind(conn: sqlite3.Connection, file_kind: str) -> list[File]:
    """List files of a specific kind."""
    rows = conn.execute("SELECT * FROM file WHERE file_kind = ?", (file_kind,)).fetchall()
    return [_row_to_file(r) for r in rows]


def update_file_visibility(
    conn: sqlite3.Connection,
    file_id: str,
    visibility: str,
    disappeared_at: str | None = None,
) -> None:
    """Update a file's visibility status."""
    conn.execute(
        "UPDATE file SET visibility = ?, disappeared_at = ? WHERE id = ?",
        (visibility, disappeared_at, file_id),
    )
    conn.commit()
