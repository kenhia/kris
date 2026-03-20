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


def get_duplicate_groups(
    conn: sqlite3.Connection,
    source_id: str | None = None,
    min_size: int | None = None,
) -> list[dict]:
    """Find groups of files sharing the same content_hash.

    Returns a list of dicts with keys: content_hash, count, files.
    Each file entry has: path, source_id, size.
    Only includes active files. Groups with count < 2 are excluded.
    """
    conditions = ["f.visibility = 'active'"]
    params: list = []

    if source_id:
        conditions.append("f.source_id = ?")
        params.append(source_id)
    if min_size is not None:
        conditions.append("f.size >= ?")
        params.append(min_size)

    where = " AND ".join(conditions)

    # Find content_hashes that appear in more than one active file
    hash_rows = conn.execute(
        f"""SELECT content_hash, COUNT(*) as cnt
            FROM file f
            WHERE {where}
            GROUP BY content_hash
            HAVING cnt > 1
            ORDER BY cnt DESC""",
        params,
    ).fetchall()

    groups = []
    for row in hash_rows:
        ch = row["content_hash"]
        file_params: list = [ch]
        file_conditions = ["f.content_hash = ?", "f.visibility = 'active'"]
        if source_id:
            file_conditions.append("f.source_id = ?")
            file_params.append(source_id)

        file_rows = conn.execute(
            f"""SELECT f.path, f.source_id, f.size
                FROM file f
                WHERE {" AND ".join(file_conditions)}
                ORDER BY f.source_id, f.path""",
            file_params,
        ).fetchall()

        groups.append(
            {
                "content_hash": ch,
                "count": row["cnt"],
                "files": [
                    {"path": fr["path"], "source_id": fr["source_id"], "size": fr["size"]}
                    for fr in file_rows
                ],
            }
        )

    return groups
