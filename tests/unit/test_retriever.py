"""Unit tests for the retriever — OpenSearch k-NN vector search + SQLite metadata enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from kris.catalog.db import get_connection
from kris.config.schema import KrisConfig, OpenSearchConfig


@pytest.fixture
def query_db(tmp_path):
    """Database with sample files, content, chunks, and embeddings for query testing."""
    db_path = tmp_path / "query-test.db"
    conn = get_connection(db_path)

    # Source
    conn.execute(
        "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
        ("src-1", "Test", "local", "/tmp/data"),
    )

    # Content records
    for _i, h in enumerate(["hash-a", "hash-b"]):
        conn.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
            (h, "completed"),
        )

    # File records
    conn.execute(
        "INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind, visibility) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("f1", "src-1", "hash-a", "docs/readme.md", 500, 1000, "markdown", "active"),
    )
    conn.execute(
        "INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind, visibility) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("f2", "src-1", "hash-b", "src/main.py", 200, 1000, "code", "active"),
    )

    # Chunks
    conn.execute(
        "INSERT INTO chunk (id, content_hash, chunk_index, chunk_content_hash, content, "
        "start_offset, end_offset, chunking_strategy) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "c1",
            "hash-a",
            0,
            "ch1",
            "This project uses Python for data processing.",
            0,
            45,
            "markdown",
        ),
    )
    conn.execute(
        "INSERT INTO chunk (id, content_hash, chunk_index, chunk_content_hash, content, "
        "start_offset, end_offset, chunking_strategy) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "c2",
            "hash-a",
            1,
            "ch2",
            "Setup instructions for the development environment.",
            45,
            95,
            "markdown",
        ),
    )
    conn.execute(
        "INSERT INTO chunk (id, content_hash, chunk_index, chunk_content_hash, content, "
        "start_offset, end_offset, chunking_strategy) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("c3", "hash-b", 0, "ch3", "def main():\n    print('hello')\n", 0, 30, "code"),
    )

    # Embeddings
    conn.execute(
        "INSERT INTO embedding (id, chunk_id, model_id, index_name, opensearch_doc_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("e1", "c1", "embedding", "kris_chunks", "doc-1"),
    )
    conn.execute(
        "INSERT INTO embedding (id, chunk_id, model_id, index_name, opensearch_doc_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("e2", "c2", "embedding", "kris_chunks", "doc-2"),
    )
    conn.execute(
        "INSERT INTO embedding (id, chunk_id, model_id, index_name, opensearch_doc_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("e3", "c3", "embedding", "kris_chunks", "doc-3"),
    )

    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def os_config(tmp_path) -> KrisConfig:
    return KrisConfig(
        data_dir=str(tmp_path),
        opensearch=OpenSearchConfig(
            url="https://localhost:9200",
            username="admin",
            password="admin",
            index_prefix="kris",
        ),
    )


def _make_search_response(*hits):
    """Build an OpenSearch search response from (doc_id, score, source) tuples."""
    return {
        "hits": {
            "total": {"value": len(hits)},
            "hits": [{"_id": h[0], "_score": h[1], "_source": h[2]} for h in hits],
        }
    }


class TestRetrieve:
    def test_retrieve_returns_results(self, query_db, os_config):
        from kris.query.retriever import retrieve

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.search.return_value = _make_search_response(
            (
                "doc-1",
                0.95,
                {
                    "chunk_id": "c1",
                    "content": "This project uses Python for data processing.",
                    "content_hash": "hash-a",
                    "chunk_index": 0,
                    "file_kind": "markdown",
                    "source_id": "src-1",
                    "file_path": "docs/readme.md",
                },
            ),
            (
                "doc-2",
                0.80,
                {
                    "chunk_id": "c2",
                    "content": "Setup instructions for the development environment.",
                    "content_hash": "hash-a",
                    "chunk_index": 1,
                    "file_kind": "markdown",
                    "source_id": "src-1",
                    "file_path": "docs/readme.md",
                },
            ),
        )

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])

        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model

        mock_info = MagicMock()
        mock_info.dimensions = 768

        with patch("kris.processing.embed.create_opensearch_client", return_value=mock_client):
            results = retrieve(
                query="how does this project work?",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                config=os_config,
                top_k=5,
            )

        assert len(results) == 2
        assert results[0].score == 0.95
        assert results[0].chunk_text == "This project uses Python for data processing."
        assert results[0].file_path == "docs/readme.md"
        assert results[0].source_id == "src-1"
        assert results[1].score == 0.80

    def test_retrieve_empty_index(self, query_db, os_config):
        from kris.query.retriever import retrieve

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = False

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])

        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model

        mock_info = MagicMock()

        with patch("kris.processing.embed.create_opensearch_client", return_value=mock_client):
            results = retrieve(
                query="anything",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                config=os_config,
                top_k=5,
            )

        assert results == []

    def test_retrieve_with_source_filter(self, query_db, os_config):
        from kris.query.retriever import retrieve

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.search.return_value = _make_search_response(
            (
                "doc-1",
                0.9,
                {
                    "chunk_id": "c1",
                    "content": "This project uses Python.",
                    "content_hash": "hash-a",
                    "chunk_index": 0,
                    "file_kind": "markdown",
                    "source_id": "src-1",
                    "file_path": "docs/readme.md",
                },
            ),
        )

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])
        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model
        mock_info = MagicMock()

        with patch("kris.processing.embed.create_opensearch_client", return_value=mock_client):
            results = retrieve(
                query="test",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                config=os_config,
                top_k=5,
                source_filter="src-1",
            )

        assert len(results) == 1
        assert results[0].source_id == "src-1"

        # Verify the search body contains a filter clause
        search_body = mock_client.search.call_args.kwargs.get(
            "body"
        ) or mock_client.search.call_args[1].get("body")
        knn_filter = search_body["query"]["knn"]["embedding"].get("filter")
        assert knn_filter is not None
        assert {"term": {"source_id": "src-1"}} in knn_filter["bool"]["must"]

    def test_retrieve_with_kind_filter(self, query_db, os_config):
        from kris.query.retriever import retrieve

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.search.return_value = _make_search_response(
            (
                "doc-3",
                0.85,
                {
                    "chunk_id": "c3",
                    "content": "def main():\n    print('hello')\n",
                    "content_hash": "hash-b",
                    "chunk_index": 0,
                    "file_kind": "code",
                    "source_id": "src-1",
                    "file_path": "src/main.py",
                },
            ),
        )

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])
        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model
        mock_info = MagicMock()

        with patch("kris.processing.embed.create_opensearch_client", return_value=mock_client):
            results = retrieve(
                query="main function",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                config=os_config,
                top_k=5,
                kind_filter="code",
            )

        assert len(results) == 1
        assert results[0].file_kind == "code"

    def test_retrieve_passes_top_k(self, query_db, os_config):
        from kris.query.retriever import retrieve

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.search.return_value = _make_search_response()

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])
        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model
        mock_info = MagicMock()

        with patch("kris.processing.embed.create_opensearch_client", return_value=mock_client):
            retrieve(
                query="test",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                config=os_config,
                top_k=3,
            )

        # Verify top_k was passed in the body
        search_body = mock_client.search.call_args.kwargs.get(
            "body"
        ) or mock_client.search.call_args[1].get("body")
        assert search_body["size"] == 3
        assert search_body["query"]["knn"]["embedding"]["k"] == 3


class TestRetrievalResult:
    def test_result_dataclass_fields(self):
        from kris.query.retriever import RetrievalResult

        result = RetrievalResult(
            chunk_id="c1",
            chunk_text="some text",
            chunk_index=0,
            content_hash="abc",
            file_path="test.py",
            file_kind="code",
            source_id="src-1",
            source_name="Test",
            score=0.95,
        )
        assert result.score == 0.95
        assert result.file_path == "test.py"
