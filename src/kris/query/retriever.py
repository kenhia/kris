"""Retriever — embed query, search OpenSearch k-NN, enrich with SQLite metadata."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kris.config.schema import KrisConfig
    from kris.models.manager import ModelManager
    from kris.models.registry import ModelInfo

logger = logging.getLogger(__name__)


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
    config: KrisConfig,
    top_k: int = 10,
    source_filter: str | None = None,
    kind_filter: str | None = None,
) -> list[RetrievalResult]:
    """Embed the query and search OpenSearch k-NN for similar chunks.

    Uses pre-filtering via OpenSearch query DSL for source_id and file_kind.
    Returns results enriched with file metadata from SQLite.
    """
    from kris.processing.embed import create_opensearch_client

    # Embed the query using the same model used for indexing
    model = model_manager.load_embedding_model(model_info)
    query_vector = model.encode([query], show_progress_bar=False)[0].tolist()

    client = create_opensearch_client(config)
    index_name = config.opensearch_index

    if not client.indices.exists(index=index_name):
        return []

    # Build k-NN query with optional pre-filtering
    knn_query: dict = {
        "vector": query_vector,
        "k": top_k,
    }

    # Pre-filter via OpenSearch DSL
    filter_clauses = []
    if source_filter:
        filter_clauses.append({"term": {"source_id": source_filter}})
    if kind_filter:
        filter_clauses.append({"term": {"file_kind": kind_filter}})

    if filter_clauses:
        knn_query["filter"] = {"bool": {"must": filter_clauses}}

    body = {
        "size": top_k,
        "query": {
            "knn": {
                "embedding": knn_query,
            }
        },
    }

    response = client.search(index=index_name, body=body)

    hits = response.get("hits", {}).get("hits", [])
    if not hits:
        return []

    results = []
    for hit in hits:
        source = hit.get("_source", {})
        chunk_id = source.get("chunk_id")
        if not chunk_id:
            continue

        # Enrich with SQLite metadata (source_name primarily)
        meta = _get_chunk_metadata(conn, chunk_id)
        if meta is None:
            continue

        results.append(
            RetrievalResult(
                chunk_id=chunk_id,
                chunk_text=source.get("content", meta["chunk_text"]),
                chunk_index=source.get("chunk_index", meta["chunk_index"]),
                content_hash=source.get("content_hash", meta["content_hash"]),
                file_path=source.get("file_path", meta["file_path"]),
                file_kind=source.get("file_kind", meta["file_kind"]),
                source_id=source.get("source_id", meta["source_id"]),
                source_name=meta["source_name"],
                score=hit.get("_score", 0.0),
            )
        )

    return results


def _get_chunk_metadata(
    conn: sqlite3.Connection,
    chunk_id: str,
) -> dict | None:
    """Look up chunk + file + source metadata from SQLite."""
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

    return {
        "chunk_text": row["content"],
        "chunk_index": row["chunk_index"],
        "content_hash": row["content_hash"],
        "file_path": row["path"],
        "file_kind": row["file_kind"],
        "source_id": row["source_id"],
        "source_name": row["source_name"],
    }
