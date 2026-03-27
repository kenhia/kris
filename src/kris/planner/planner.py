"""Task planner — generates processing task DAGs from pending content."""

from __future__ import annotations

import sqlite3
import uuid

from kris.catalog.models import Content, Task

# Task types in execution order
TASK_TYPE_EXTRACT = "extract"
TASK_TYPE_CHUNK = "chunk"
TASK_TYPE_EMBED = "embed"

# File kinds eligible for text extraction. All others are skipped.
EXTRACTABLE_KINDS = {"text", "code", "markdown", "config", "data"}


def plan_tasks_for_content(
    conn: sqlite3.Connection,
    content: Content,
    embedding_model_hint: str = "embedding",
) -> list[Task]:
    """Generate the extract → chunk → embed task DAG for a content record.

    If the file's kind is not extractable, mark the content as 'skipped'
    and return no tasks.

    Returns the created tasks in dependency order.
    """
    # Check if tasks already exist for this content
    existing = conn.execute(
        "SELECT COUNT(*) FROM task WHERE content_hash = ?",
        (content.content_hash,),
    ).fetchone()
    if existing and existing[0] > 0:
        return []

    # Check if any file referencing this content has a non-extractable kind
    file_row = conn.execute(
        "SELECT file_kind FROM file WHERE content_hash = ? LIMIT 1",
        (content.content_hash,),
    ).fetchone()
    if file_row and file_row["file_kind"] not in EXTRACTABLE_KINDS:
        conn.execute(
            "UPDATE content SET processing_status = 'skipped' WHERE content_hash = ?",
            (content.content_hash,),
        )
        conn.commit()
        return []

    extract_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    embed_id = str(uuid.uuid4())

    tasks = [
        Task(
            id=extract_id,
            content_hash=content.content_hash,
            task_type=TASK_TYPE_EXTRACT,
            priority=100,
        ),
        Task(
            id=chunk_id,
            content_hash=content.content_hash,
            task_type=TASK_TYPE_CHUNK,
            priority=200,
            depends_on=[extract_id],
        ),
        Task(
            id=embed_id,
            content_hash=content.content_hash,
            task_type=TASK_TYPE_EMBED,
            priority=300,
            depends_on=[chunk_id],
            model_hint=embedding_model_hint,
        ),
    ]

    for task in tasks:
        import json

        depends_json = json.dumps(task.depends_on) if task.depends_on else None
        conn.execute(
            """INSERT INTO task
               (id, content_hash, task_type, status, model_hint, priority,
                depends_on, attempts, max_attempts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id,
                task.content_hash,
                task.task_type,
                task.status,
                task.model_hint,
                task.priority,
                depends_json,
                task.attempts,
                task.max_attempts,
            ),
        )
    conn.commit()
    return tasks


def plan_pending_content(
    conn: sqlite3.Connection,
    embedding_model_hint: str = "embedding",
) -> int:
    """Plan tasks for all pending content records.

    Returns the number of content records that had tasks planned.
    """
    rows = conn.execute("SELECT * FROM content WHERE processing_status = 'pending'").fetchall()

    planned = 0
    for row in rows:
        content = Content(
            content_hash=row["content_hash"],
            processing_status=row["processing_status"],
            last_processed=row["last_processed"],
            parent_content_hash=row["parent_content_hash"],
        )
        tasks = plan_tasks_for_content(conn, content, embedding_model_hint)
        if tasks:
            planned += 1

    return planned
