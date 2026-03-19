"""Task worker — pulls and executes processing tasks."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from kris.catalog.tasks import get_task, get_tasks_by_status, update_task_status

if TYPE_CHECKING:
    from kris.models.manager import ModelManager
    from kris.models.registry import ModelRegistry
from kris.processing.chunk import chunk_code, chunk_markdown, chunk_text, save_chunks
from kris.processing.embed import embed_chunks
from kris.processing.extract import extract_for_content

logger = logging.getLogger(__name__)


def _check_dependencies(conn: sqlite3.Connection, task) -> bool:
    """Check if all dependency tasks are completed."""
    if not task.depends_on:
        return True
    for dep_id in task.depends_on:
        dep = get_task(conn, dep_id)
        if dep is None or dep.status != "completed":
            return False
    return True


def _detect_file_kind(conn: sqlite3.Connection, content_hash: str) -> str:
    """Look up the file_kind for a content hash."""
    row = conn.execute(
        "SELECT file_kind FROM file WHERE content_hash = ? LIMIT 1",
        (content_hash,),
    ).fetchone()
    return row["file_kind"] if row else "unknown"


def _detect_language(conn: sqlite3.Connection, content_hash: str) -> str:
    """Guess programming language from file extension."""
    row = conn.execute(
        "SELECT path FROM file WHERE content_hash = ? LIMIT 1",
        (content_hash,),
    ).fetchone()
    if not row:
        return "unknown"

    path = row["path"]
    ext_map = {
        ".py": "python",
        ".rs": "rust",
        ".js": "javascript",
        ".ts": "typescript",
        ".go": "go",
        ".rb": "ruby",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
    }
    for ext, lang in ext_map.items():
        if path.endswith(ext):
            return lang
    return "unknown"


def execute_task(
    conn: sqlite3.Connection,
    task,
    data_dir: Path,
    qdrant_path: Path,
    model_manager: ModelManager,
    registry: ModelRegistry,
) -> bool:
    """Execute a single task. Returns True on success."""
    now = datetime.now(UTC).isoformat()

    # Mark as running
    conn.execute(
        "UPDATE task SET status = 'running', started_at = ?, attempts = attempts + 1 WHERE id = ?",
        (now, task.id),
    )
    conn.commit()

    try:
        if task.task_type == "extract":
            result = extract_for_content(conn, task.content_hash, data_dir)
            # Store extracted text in content table metadata (or just mark complete)
            # The text is available through the file — we just validated extraction works
            logger.info("Extracted %d chars for %s", result.size, task.content_hash[:12])

        elif task.task_type == "chunk":
            # Get the extracted text
            result = extract_for_content(conn, task.content_hash, data_dir)
            file_kind = _detect_file_kind(conn, task.content_hash)

            if file_kind == "markdown":
                chunks = chunk_markdown(result.text, task.content_hash)
            elif file_kind == "code":
                lang = _detect_language(conn, task.content_hash)
                chunks = chunk_code(result.text, task.content_hash, language=lang)
            else:
                chunks = chunk_text(result.text, task.content_hash)

            saved = save_chunks(conn, chunks)
            logger.info("Created %d chunks for %s", saved, task.content_hash[:12])

        elif task.task_type == "embed":
            model_info = registry.get(task.model_hint or "embedding")
            if model_info is None:
                raise RuntimeError("Embedding model not found in registry")

            count = embed_chunks(conn, task.content_hash, model_manager, model_info, qdrant_path)
            logger.info("Embedded %d chunks for %s", count, task.content_hash[:12])

        else:
            raise RuntimeError(f"Unknown task type: {task.task_type}")

        # Mark completed
        update_task_status(conn, task.id, "completed")
        return True

    except Exception as e:
        logger.error("Task %s failed: %s", task.id, e)
        error_msg = str(e)
        if task.attempts >= task.max_attempts:
            update_task_status(conn, task.id, "failed", error=error_msg)
        else:
            update_task_status(conn, task.id, "queued", error=error_msg)
        return False


def run_worker(
    conn: sqlite3.Connection,
    data_dir: Path,
    qdrant_path: Path,
    model_manager: ModelManager,
    registry: ModelRegistry,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int, int]:
    """Process all queued tasks in dependency order.

    Groups tasks by model_hint to minimize model load/unload cycles (FR-017).
    Returns (completed_count, failed_count).
    """
    completed = 0
    failed = 0

    # Process in priority order, grouped by model_hint for affinity
    # First pass: non-model tasks (extract, chunk)
    for task_type in ["extract", "chunk", "embed"]:
        while True:
            tasks = get_tasks_by_status(conn, "queued")
            type_tasks = [t for t in tasks if t.task_type == task_type]

            if not type_tasks:
                break

            made_progress = False
            for task in type_tasks:
                if not _check_dependencies(conn, task):
                    continue

                success = execute_task(conn, task, data_dir, qdrant_path, model_manager, registry)
                if success:
                    completed += 1
                else:
                    failed += 1
                made_progress = True

                if on_progress:
                    on_progress(completed, failed)

            if not made_progress:
                break

    # Mark content as completed when all tasks are done
    _finalize_content(conn)

    return completed, failed


def _finalize_content(conn: sqlite3.Connection) -> None:
    """Mark content records as completed when all their tasks are done."""
    conn.execute(
        """UPDATE content SET processing_status = 'completed', last_processed = datetime('now')
           WHERE content_hash IN (
               SELECT DISTINCT content_hash FROM task
               GROUP BY content_hash
               HAVING COUNT(*) = SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END)
           ) AND processing_status != 'completed'"""
    )
    conn.commit()
