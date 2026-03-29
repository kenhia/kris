"""Embedding pipeline — encode chunks and write to OpenSearch + SQLite."""

from __future__ import annotations

import logging
import sqlite3
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from kris.catalog.models import Embedding

if TYPE_CHECKING:
    from kris.config.schema import KrisConfig
    from kris.models.manager import ModelManager
    from kris.models.registry import ModelInfo

logger = logging.getLogger(__name__)


def create_opensearch_client(config: KrisConfig) -> Any:
    """Create an OpenSearch client from configuration.

    Supports HTTPS with username/password auth and optional cert verification.
    Reads password from KRIS_OPENSEARCH_PASSWORD env var if config password is empty.
    """
    from opensearchpy import OpenSearch

    parsed = urlparse(config.opensearch.url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 9200
    use_ssl = parsed.scheme == "https"

    kwargs: dict[str, Any] = {
        "hosts": [{"host": host, "port": port}],
        "use_ssl": use_ssl,
        "verify_certs": config.opensearch.verify_certs,
        "ssl_show_warn": False,
    }

    if config.opensearch.username:
        kwargs["http_auth"] = (config.opensearch.username, config.opensearch.password)

    try:
        client = OpenSearch(**kwargs)
        # Verify connectivity
        info = client.info()
        logger.debug("Connected to OpenSearch %s", info.get("version", {}).get("number", "?"))
        return client
    except Exception as e:
        error_str = str(e)
        if "401" in error_str or "Unauthorized" in error_str:
            raise ConnectionError(
                f"OpenSearch authentication failed at {config.opensearch.url}. "
                "Check username/password in config.toml or KRIS_OPENSEARCH_PASSWORD env var."
            ) from e
        raise ConnectionError(
            f"Cannot connect to OpenSearch at {config.opensearch.url}. "
            "Is the service running? Check: docker ps | grep opensearch"
        ) from e


def ensure_index(client: Any, config: KrisConfig, dimensions: int) -> None:
    """Create the kris_chunks index with k-NN mapping if it doesn't exist.

    If the index exists, verifies the embedding dimension matches.
    """
    index_name = config.opensearch_index

    if client.indices.exists(index=index_name):
        # Verify existing mapping dimensions match
        mapping = client.indices.get_mapping(index=index_name)
        try:
            props = mapping[index_name]["mappings"]["properties"]
            existing_dim = props["embedding"]["dimension"]
            if existing_dim != dimensions:
                raise ValueError(
                    f"OpenSearch index '{index_name}' exists with incompatible mapping "
                    f"(expected {dimensions}-dim vectors, found {existing_dim}). "
                    f"Delete the index or use a different index_prefix."
                )
        except (KeyError, TypeError):
            pass  # No embedding field yet or unexpected structure — proceed
        return

    body = {
        "settings": {
            "index": {
                "knn": True,
                "number_of_shards": 1,
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "knn_vector",
                    "dimension": dimensions,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                    },
                },
                "content": {"type": "text"},
                "content_hash": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "chunking_strategy": {"type": "keyword"},
                "file_kind": {"type": "keyword"},
                "source_id": {"type": "keyword"},
                "file_path": {"type": "keyword"},
            }
        },
    }
    client.indices.create(index=index_name, body=body)
    logger.info("Created OpenSearch index '%s' (dim=%d)", index_name, dimensions)


def embed_chunks(
    conn: sqlite3.Connection,
    content_hash: str,
    model_manager: ModelManager,
    model_info: ModelInfo,
    config: KrisConfig,
    *,
    client: Any | None = None,
) -> int:
    """Embed all chunks for a content record and write to OpenSearch + SQLite.

    Returns the number of embeddings created.
    """
    from opensearchpy import helpers

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

    # Ensure index exists
    dimensions = model_info.dimensions or len(embeddings[0])
    if client is None:
        client = create_opensearch_client(config)
    ensure_index(client, config, dimensions)

    index_name = config.opensearch_index

    # Look up file metadata for enriching OpenSearch documents
    file_meta = conn.execute(
        "SELECT f.file_kind, f.source_id, f.path "
        "FROM file f WHERE f.content_hash = ? AND f.visibility = 'active' LIMIT 1",
        (content_hash,),
    ).fetchone()
    file_kind = file_meta["file_kind"] if file_meta else "unknown"
    source_id = file_meta["source_id"] if file_meta else ""
    file_path = file_meta["path"] if file_meta else ""

    actions = []
    embedding_records = []

    for row, vector in zip(rows, embeddings, strict=True):
        doc_id = str(uuid.uuid4())
        actions.append(
            {
                "_index": index_name,
                "_id": doc_id,
                "_source": {
                    "embedding": vector.tolist(),
                    "content": row["content"],
                    "content_hash": content_hash,
                    "chunk_id": row["id"],
                    "chunk_index": row["chunk_index"],
                    "chunking_strategy": row["chunking_strategy"],
                    "file_kind": file_kind,
                    "source_id": source_id,
                    "file_path": file_path,
                },
            }
        )
        embedding_records.append(
            Embedding(
                id=str(uuid.uuid4()),
                chunk_id=row["id"],
                model_id=model_info.model_id,
                index_name=index_name,
                opensearch_doc_id=doc_id,
            )
        )

    if actions:
        success, errors = helpers.bulk(client, actions, raise_on_error=False)
        if errors:
            logger.warning(
                "Indexed %d/%d documents. %d failed: %s",
                success,
                len(actions),
                len(errors),
                errors[0] if errors else "",
            )

    # Write embedding records to SQLite
    for emb in embedding_records:
        conn.execute(
            """INSERT OR REPLACE INTO embedding
               (id, chunk_id, model_id, index_name, opensearch_doc_id)
               VALUES (?, ?, ?, ?, ?)""",
            (emb.id, emb.chunk_id, emb.model_id, emb.index_name, emb.opensearch_doc_id),
        )
    conn.commit()

    return len(embedding_records)


def delete_documents(client: Any, index_name: str, doc_ids: list[str]) -> int:
    """Delete documents from OpenSearch by their IDs.

    Returns the number of documents requested for deletion.
    """
    if not doc_ids:
        return 0

    deleted = 0
    for doc_id in doc_ids:
        try:
            client.delete(index=index_name, id=doc_id, ignore=[404])
            deleted += 1
        except Exception:
            logger.warning("Failed to delete OpenSearch document %s", doc_id)

    logger.info("Deleted %d documents from OpenSearch index '%s'", deleted, index_name)
    return deleted
