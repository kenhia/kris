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


def get_status_summary(
    conn: sqlite3.Connection,
    source_id: str | None = None,
) -> list[dict]:
    """Get aggregate file counts per source, grouped by kind and status.

    Returns a list of dicts, one per source, with keys:
    source_id, source_name, total_files, by_kind, by_status,
    total_chunks, total_embeddings.
    """
    source_filter = ""
    params: list = []
    if source_id:
        source_filter = "WHERE s.id = ?"
        params = [source_id]

    sources = conn.execute(
        f"SELECT s.id, s.name, s.last_scan FROM source s {source_filter}",
        params,
    ).fetchall()

    results = []
    for src in sources:
        sid = src["id"]

        total = conn.execute(
            "SELECT COUNT(*) FROM file WHERE source_id = ? AND visibility = 'active'",
            (sid,),
        ).fetchone()[0]

        kind_rows = conn.execute(
            "SELECT file_kind, COUNT(*) as cnt FROM file "
            "WHERE source_id = ? AND visibility = 'active' GROUP BY file_kind",
            (sid,),
        ).fetchall()
        by_kind = {r["file_kind"]: r["cnt"] for r in kind_rows}

        status_rows = conn.execute(
            "SELECT processing_status, COUNT(*) as cnt FROM file "
            "WHERE source_id = ? AND visibility = 'active' GROUP BY processing_status",
            (sid,),
        ).fetchall()
        by_status = {r["processing_status"]: r["cnt"] for r in status_rows}

        chunk_count = conn.execute(
            "SELECT COUNT(*) FROM chunk c "
            "JOIN file f ON f.content_hash = c.content_hash "
            "WHERE f.source_id = ? AND f.visibility = 'active'",
            (sid,),
        ).fetchone()[0]

        embed_count = conn.execute(
            "SELECT COUNT(*) FROM embedding e "
            "JOIN chunk c ON c.id = e.chunk_id "
            "JOIN file f ON f.content_hash = c.content_hash "
            "WHERE f.source_id = ? AND f.visibility = 'active'",
            (sid,),
        ).fetchone()[0]

        results.append(
            {
                "source_id": sid,
                "source_name": src["name"],
                "last_scan": src["last_scan"],
                "total_files": total,
                "by_kind": by_kind,
                "by_status": by_status,
                "total_chunks": chunk_count,
                "total_embeddings": embed_count,
            }
        )

    return results


def get_failed_files(
    conn: sqlite3.Connection,
    source_id: str | None = None,
) -> list[dict]:
    """List failed files with their error reasons from tasks."""
    source_filter = ""
    params: list = []
    if source_id:
        source_filter = "AND f.source_id = ?"
        params = [source_id]

    rows = conn.execute(
        f"""SELECT f.path, f.source_id, f.file_kind, f.size, t.error
            FROM file f
            JOIN task t ON t.content_hash = f.content_hash AND t.status = 'failed'
            WHERE f.visibility = 'active' {source_filter}
            ORDER BY f.source_id, f.path""",
        params,
    ).fetchall()

    return [
        {
            "path": r["path"],
            "source_id": r["source_id"],
            "file_kind": r["file_kind"],
            "size": r["size"],
            "error": r["error"],
        }
        for r in rows
    ]


def cleanup_missing_files(
    conn: sqlite3.Connection,
    older_than_days: int | None = None,
    source_id: str | None = None,
    path_pattern: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Remove missing files and their associated artifacts.

    Returns a dict with: files_removed, chunks_removed, embeddings_removed,
    qdrant_point_ids (list of Qdrant point IDs to delete externally).
    """
    conditions = ["f.visibility = 'missing'"]
    params: list = []

    if older_than_days is not None:
        conditions.append("f.disappeared_at <= datetime('now', ?)")
        params.append(f"-{older_than_days} days")

    if source_id:
        conditions.append("f.source_id = ?")
        params.append(source_id)

    if path_pattern:
        conditions.append("f.path LIKE ?")
        params.append(path_pattern)

    where = " AND ".join(conditions)

    # Find the files to clean up
    file_rows = conn.execute(
        f"SELECT f.id, f.content_hash FROM file f WHERE {where}",
        params,
    ).fetchall()

    if not file_rows:
        return {
            "files_removed": 0,
            "chunks_removed": 0,
            "embeddings_removed": 0,
            "qdrant_point_ids": [],
        }

    file_ids = [r["id"] for r in file_rows]
    # Collect content hashes to check for orphaned content
    content_hashes = list({r["content_hash"] for r in file_rows})

    # Collect Qdrant point IDs before deleting embeddings
    qdrant_point_ids: list[str] = []
    embeddings_removed = 0
    chunks_removed = 0

    for ch in content_hashes:
        # Only clean up artifacts if no other active files reference this content
        other_active = conn.execute(
            "SELECT COUNT(*) FROM file WHERE content_hash = ? AND visibility = 'active'",
            (ch,),
        ).fetchone()[0]
        if other_active > 0:
            continue

        # Collect qdrant point IDs
        point_rows = conn.execute(
            "SELECT e.qdrant_point_id FROM embedding e "
            "JOIN chunk c ON c.id = e.chunk_id "
            "WHERE c.content_hash = ?",
            (ch,),
        ).fetchall()
        qdrant_point_ids.extend(r["qdrant_point_id"] for r in point_rows)

        if not dry_run:
            # Delete embeddings for chunks of this content
            emb_count = conn.execute(
                "DELETE FROM embedding WHERE chunk_id IN "
                "(SELECT id FROM chunk WHERE content_hash = ?)",
                (ch,),
            ).rowcount
            embeddings_removed += emb_count

            # Delete chunks
            chunk_count = conn.execute(
                "DELETE FROM chunk WHERE content_hash = ?",
                (ch,),
            ).rowcount
            chunks_removed += chunk_count

            # Delete tasks
            conn.execute("DELETE FROM task WHERE content_hash = ?", (ch,))

            # Delete content record
            conn.execute("DELETE FROM content WHERE content_hash = ?", (ch,))
        else:
            embeddings_removed += len(point_rows)
            chunks_removed += conn.execute(
                "SELECT COUNT(*) FROM chunk WHERE content_hash = ?", (ch,)
            ).fetchone()[0]

    files_removed = len(file_ids)

    if not dry_run:
        # Delete the file records
        placeholders = ",".join("?" * len(file_ids))
        conn.execute(f"DELETE FROM file WHERE id IN ({placeholders})", file_ids)
        conn.commit()

    return {
        "files_removed": files_removed,
        "chunks_removed": chunks_removed,
        "embeddings_removed": embeddings_removed,
        "qdrant_point_ids": qdrant_point_ids,
    }
