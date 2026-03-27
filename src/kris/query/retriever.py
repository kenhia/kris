"""Retriever — embed query, search Qdrant, enrich with SQLite metadata."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kris.config.schema import KrisConfig
    from kris.models.manager import ModelManager
    from kris.models.registry import ModelInfo

logger = logging.getLogger(__name__)

COLLECTION_NAME = "kris_chunks"


@dataclass
class RetrievalResult:
    chunk_id: str
    chunk_text: str
    chunk_index: int
    content_hash: str
    file_path: str
    file_kind: str
    source_id: str
    source_name: str
    score: float


def retrieve(
    query: str,
    conn: sqlite3.Connection,
    model_manager: ModelManager,
    model_info: ModelInfo,
    qdrant_path: str | Path,
    top_k: int = 10,
    source_filter: str | None = None,
    kind_filter: str | None = None,
    config: KrisConfig | None = None,
) -> list[RetrievalResult]:
    """Embed the query and search Qdrant for similar chunks.

    Returns results enriched with file metadata from SQLite.
    """
    from kris.processing.embed import create_qdrant_client

    # Embed the query using the same model used for indexing
    model = model_manager.load_embedding_model(model_info)
    query_vector = model.encode([query], show_progress_bar=False)[0].tolist()

    client = create_qdrant_client(config, qdrant_path=Path(qdrant_path))
    search_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
    )

    if not search_results.points:
        return []

    results = []
    for point in search_results.points:
        if not point.payload:
            continue
        chunk_id = point.payload.get("chunk_id")
        if not chunk_id:
            continue

        # Enrich with SQLite metadata
        meta = _get_chunk_metadata(conn, chunk_id, source_filter, kind_filter)
        if meta is None:
            continue

        results.append(
            RetrievalResult(
                chunk_id=chunk_id,
                chunk_text=meta["chunk_text"],
                chunk_index=meta["chunk_index"],
                content_hash=meta["content_hash"],
                file_path=meta["file_path"],
                file_kind=meta["file_kind"],
                source_id=meta["source_id"],
                source_name=meta["source_name"],
                score=point.score,
            )
        )

    return results


def _get_chunk_metadata(
    conn: sqlite3.Connection,
    chunk_id: str,
    source_filter: str | None,
    kind_filter: str | None,
) -> dict | None:
    """Look up chunk + file + source metadata from SQLite.

    Returns None if the chunk doesn't match the applied filters.
    """
    row = conn.execute(
        """SELECT c.content, c.chunk_index, c.content_hash,
                  f.path, f.file_kind, f.source_id,
                  s.name as source_name
           FROM chunk c
           JOIN file f ON f.content_hash = c.content_hash AND f.visibility = 'active'
           JOIN source s ON s.id = f.source_id
           WHERE c.id = ?
           LIMIT 1""",
        (chunk_id,),
    ).fetchone()

    if row is None:
        return None

    if source_filter and row["source_id"] != source_filter:
        return None
    if kind_filter and row["file_kind"] != kind_filter:
        return None

    return {
        "chunk_text": row["content"],
        "chunk_index": row["chunk_index"],
        "content_hash": row["content_hash"],
        "file_path": row["path"],
        "file_kind": row["file_kind"],
        "source_id": row["source_id"],
        "source_name": row["source_name"],
    }
