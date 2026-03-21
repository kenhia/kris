"""Task CRUD operations for the catalog."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime

from kris.catalog.models import Task


def _row_to_task(row: sqlite3.Row) -> Task:
    depends_raw = row["depends_on"]
    depends_on = json.loads(depends_raw) if depends_raw else []
    return Task(
        id=row["id"],
        content_hash=row["content_hash"],
        task_type=row["task_type"],
        status=row["status"],
        model_hint=row["model_hint"],
        priority=row["priority"],
        depends_on=depends_on,
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        error=row["error"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def create_task(conn: sqlite3.Connection, task: Task) -> Task:
    """Insert a new task record."""
    if not task.id:
        task.id = str(uuid.uuid4())
    depends_json = json.dumps(task.depends_on) if task.depends_on else None
    conn.execute(
        """INSERT INTO task
           (id, content_hash, task_type, status, model_hint, priority,
            depends_on, attempts, max_attempts, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            task.error,
        ),
    )
    conn.commit()
    return task


def get_task(conn: sqlite3.Connection, task_id: str) -> Task | None:
    """Get a task by its ID."""
    row = conn.execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone()
    return _row_to_task(row) if row else None


def get_tasks_by_status(
    conn: sqlite3.Connection,
    status: str,
    model_hint: str | None = None,
) -> list[Task]:
    """Query tasks by status, optionally filtered by model_hint for affinity ordering."""
    if model_hint:
        rows = conn.execute(
            "SELECT * FROM task WHERE status = ? AND model_hint = ? ORDER BY priority ASC",
            (status, model_hint),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM task WHERE status = ? ORDER BY priority ASC",
            (status,),
        ).fetchall()
    return [_row_to_task(r) for r in rows]


def get_tasks_by_content(conn: sqlite3.Connection, content_hash: str) -> list[Task]:
    """Get all tasks for a content record."""
    rows = conn.execute(
        "SELECT * FROM task WHERE content_hash = ? ORDER BY priority ASC",
        (content_hash,),
    ).fetchall()
    return [_row_to_task(r) for r in rows]


def update_task_status(
    conn: sqlite3.Connection,
    task_id: str,
    status: str,
    error: str | None = None,
) -> None:
    """Update task status and timestamps."""
    now = datetime.now(UTC).isoformat()
    if status == "running":
        conn.execute(
            "UPDATE task SET status = ?, started_at = ?, attempts = attempts + 1 WHERE id = ?",
            (status, now, task_id),
        )
    elif status in ("completed", "failed"):
        conn.execute(
            "UPDATE task SET status = ?, completed_at = ?, error = ? WHERE id = ?",
            (status, now, error, task_id),
        )
    else:
        conn.execute(
            "UPDATE task SET status = ? WHERE id = ?",
            (status, task_id),
        )
    conn.commit()


def check_dependencies_met(conn: sqlite3.Connection, task: Task) -> bool:
    """Check if all dependency tasks are completed."""
    if not task.depends_on:
        return True
    placeholders = ",".join("?" for _ in task.depends_on)
    row = conn.execute(
        f"SELECT COUNT(*) FROM task WHERE id IN ({placeholders}) AND status = 'completed'",
        task.depends_on,
    ).fetchone()
    return row[0] == len(task.depends_on)
