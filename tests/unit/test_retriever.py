"""Unit tests for the retriever — Qdrant vector search + SQLite metadata enrichment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from kris.catalog.db import get_connection


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
        "INSERT INTO embedding (id, chunk_id, model_id, collection_name, qdrant_point_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("e1", "c1", "embedding", "kris_chunks", "pt-1"),
    )
    conn.execute(
        "INSERT INTO embedding (id, chunk_id, model_id, collection_name, qdrant_point_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("e2", "c2", "embedding", "kris_chunks", "pt-2"),
    )
    conn.execute(
        "INSERT INTO embedding (id, chunk_id, model_id, collection_name, qdrant_point_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("e3", "c3", "embedding", "kris_chunks", "pt-3"),
    )

    conn.commit()
    yield conn
    conn.close()


class TestRetrieve:
    def test_retrieve_returns_results(self, query_db):
        from kris.query.retriever import retrieve

        # Mock Qdrant search to return scored points
        mock_point1 = MagicMock()
        mock_point1.id = "pt-1"
        mock_point1.score = 0.95
        mock_point1.payload = {"chunk_id": "c1", "content_hash": "hash-a", "chunk_index": 0}

        mock_point2 = MagicMock()
        mock_point2.id = "pt-2"
        mock_point2.score = 0.80
        mock_point2.payload = {"chunk_id": "c2", "content_hash": "hash-a", "chunk_index": 1}

        mock_client = MagicMock()
        mock_client.query_points.return_value.points = [mock_point1, mock_point2]

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])

        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model

        mock_info = MagicMock()
        mock_info.dimensions = 768

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            results = retrieve(
                query="how does this project work?",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                qdrant_path="/tmp/qdrant",
                top_k=5,
            )

        assert len(results) == 2
        assert results[0].score == 0.95
        assert results[0].chunk_text == "This project uses Python for data processing."
        assert results[0].file_path == "docs/readme.md"
        assert results[0].source_id == "src-1"
        assert results[1].score == 0.80

    def test_retrieve_empty_collection(self, query_db):
        from kris.query.retriever import retrieve

        mock_client = MagicMock()
        mock_client.query_points.return_value.points = []

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])

        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model

        mock_info = MagicMock()

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            results = retrieve(
                query="anything",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                qdrant_path="/tmp/qdrant",
                top_k=5,
            )

        assert results == []

    def test_retrieve_with_source_filter(self, query_db):
        from kris.query.retriever import retrieve

        mock_point = MagicMock()
        mock_point.id = "pt-1"
        mock_point.score = 0.9
        mock_point.payload = {"chunk_id": "c1", "content_hash": "hash-a", "chunk_index": 0}

        mock_client = MagicMock()
        mock_client.query_points.return_value.points = [mock_point]

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])

        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model

        mock_info = MagicMock()

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            results = retrieve(
                query="test",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                qdrant_path="/tmp/qdrant",
                top_k=5,
                source_filter="src-1",
            )

        assert len(results) == 1
        assert results[0].source_id == "src-1"

    def test_retrieve_with_kind_filter(self, query_db):
        from kris.query.retriever import retrieve

        mock_point = MagicMock()
        mock_point.id = "pt-3"
        mock_point.score = 0.85
        mock_point.payload = {"chunk_id": "c3", "content_hash": "hash-b", "chunk_index": 0}

        mock_client = MagicMock()
        mock_client.query_points.return_value.points = [mock_point]

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])

        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model

        mock_info = MagicMock()

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            results = retrieve(
                query="main function",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                qdrant_path="/tmp/qdrant",
                top_k=5,
                kind_filter="code",
            )

        assert len(results) == 1
        assert results[0].file_kind == "code"

    def test_retrieve_respects_top_k(self, query_db):
        from kris.query.retriever import retrieve

        mock_client = MagicMock()
        mock_client.query_points.return_value.points = []

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])

        mock_manager = MagicMock()
        mock_manager.load_embedding_model.return_value = mock_model

        mock_info = MagicMock()

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            retrieve(
                query="test",
                conn=query_db,
                model_manager=mock_manager,
                model_info=mock_info,
                qdrant_path="/tmp/qdrant",
                top_k=3,
            )

        # Verify top_k was passed to query_points
        call_kwargs = mock_client.query_points.call_args
        assert call_kwargs.kwargs.get("limit") == 3 or call_kwargs[1].get("limit") == 3


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
