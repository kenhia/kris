"""Embedding pipeline — encode chunks and write to Qdrant + SQLite."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kris.catalog.models import Embedding

if TYPE_CHECKING:
    from kris.models.manager import ModelManager
    from kris.models.registry import ModelInfo

logger = logging.getLogger(__name__)

COLLECTION_NAME = "kris_chunks"


def create_qdrant_client(qdrant_path: Path) -> Any:
    """Create a QdrantClient for embedded-mode storage."""
    from qdrant_client import QdrantClient

    return QdrantClient(path=str(qdrant_path))


def ensure_collection(client: Any, dimensions: int) -> None:
    """Create the Qdrant collection if it doesn't exist."""
    from qdrant_client.models import Distance, VectorParams

    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s' (dim=%d)", COLLECTION_NAME, dimensions)


def embed_chunks(
    conn: sqlite3.Connection,
    content_hash: str,
    model_manager: ModelManager,
    model_info: ModelInfo,
    qdrant_path: Path,
    *,
    client: Any | None = None,
) -> int:
    """Embed all chunks for a content record and write to Qdrant + SQLite.

    Returns the number of embeddings created.
    """
    from qdrant_client.models import PointStruct

    # Get chunks for this content
    rows = conn.execute(
        "SELECT * FROM chunk WHERE content_hash = ? ORDER BY chunk_index",
        (content_hash,),
    ).fetchall()

    if not rows:
        return 0

    # Load model
    model = model_manager.load_embedding_model(model_info)

    # Encode all chunk texts
    texts = [row["content"] for row in rows]
    embeddings = model.encode(texts, show_progress_bar=False)

    # Ensure collection exists
    dimensions = model_info.dimensions or len(embeddings[0])
    if client is None:
        client = create_qdrant_client(qdrant_path)
    ensure_collection(client, dimensions)

    points = []
    embedding_records = []

    for _i, (row, vector) in enumerate(zip(rows, embeddings, strict=True)):
        point_id = str(uuid.uuid4())
        points.append(
            PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={
                    "content_hash": content_hash,
                    "chunk_id": row["id"],
                    "chunk_index": row["chunk_index"],
                    "chunking_strategy": row["chunking_strategy"],
                },
            )
        )
        embedding_records.append(
            Embedding(
                id=str(uuid.uuid4()),
                chunk_id=row["id"],
                model_id=model_info.model_id,
                collection_name=COLLECTION_NAME,
                qdrant_point_id=point_id,
            )
        )

    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)

    # Write embedding records to SQLite
    for emb in embedding_records:
        conn.execute(
            """INSERT OR REPLACE INTO embedding
               (id, chunk_id, model_id, collection_name, qdrant_point_id)
               VALUES (?, ?, ?, ?, ?)""",
            (emb.id, emb.chunk_id, emb.model_id, emb.collection_name, emb.qdrant_point_id),
        )
    conn.commit()

    return len(embedding_records)


def delete_points(qdrant_path: Path, point_ids: list[str]) -> int:
    """Delete points from Qdrant by their IDs.

    Returns the number of points requested for deletion.
    """
    if not point_ids:
        return 0

    from qdrant_client import QdrantClient
    from qdrant_client.models import PointIdsList

    client = QdrantClient(path=str(qdrant_path))
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        return 0

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=PointIdsList(points=point_ids),  # type: ignore[arg-type]
    )
    logger.info("Deleted %d points from Qdrant collection '%s'", len(point_ids), COLLECTION_NAME)
    return len(point_ids)
