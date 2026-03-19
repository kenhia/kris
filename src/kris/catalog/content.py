"""Content CRUD operations for the catalog."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from kris.catalog.models import Content


def _row_to_content(row: sqlite3.Row) -> Content:
    return Content(
        content_hash=row["content_hash"],
        processing_status=row["processing_status"],
        last_processed=row["last_processed"],
        parent_content_hash=row["parent_content_hash"],
    )


def insert_if_not_exists(conn: sqlite3.Connection, content: Content) -> Content:
    """Insert a content record only if the content_hash doesn't already exist."""
    conn.execute(
        """INSERT OR IGNORE INTO content (content_hash, parent_content_hash, processing_status)
           VALUES (?, ?, ?)""",
        (content.content_hash, content.parent_content_hash, content.processing_status),
    )
    conn.commit()
    return content


def get_content(conn: sqlite3.Connection, content_hash: str) -> Content | None:
    """Get a content record by its hash."""
    row = conn.execute("SELECT * FROM content WHERE content_hash = ?", (content_hash,)).fetchone()
    return _row_to_content(row) if row else None


def update_status(
    conn: sqlite3.Connection,
    content_hash: str,
    processing_status: str,
) -> None:
    """Update the processing status of a content record."""
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE content SET processing_status = ?, last_processed = ? WHERE content_hash = ?",
        (processing_status, now, content_hash),
    )
    conn.commit()


def get_content_by_status(conn: sqlite3.Connection, processing_status: str) -> list[Content]:
    """List content records with a specific processing status."""
    rows = conn.execute(
        "SELECT * FROM content WHERE processing_status = ?",
        (processing_status,),
    ).fetchall()
    return [_row_to_content(r) for r in rows]
