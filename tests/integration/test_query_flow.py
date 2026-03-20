"""Integration test for full query flow: query -> embed -> search -> enrich -> synthesize."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from kris.catalog.db import get_connection
from kris.models.manager import ModelManager
from kris.models.registry import ModelRegistry
from kris.processing.chunk import chunk_text, save_chunks
from kris.processing.extract import extract_for_content
from kris.query.engine import query
from kris.scanner import find_scanner_binary


@pytest.fixture
def scanner_binary():
    try:
        return find_scanner_binary()
    except Exception:
        pytest.skip("kris-scanner binary not built")


@pytest.fixture
def indexed_env(tmp_path, scanner_binary):
    """Environment with scanned, extracted, and chunked files (no real embedding)."""
    db_path = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    (data_dir / "readme.md").write_text(
        "# My Project\n\nThis project processes files using Python.\n\n"
        "## Features\n\nIt supports text, code, and markdown files.\n",
        encoding="utf-8",
    )
    (data_dir / "notes.txt").write_text(
        "Important note: the system uses SQLite for the catalog.\n",
        encoding="utf-8",
    )

    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
        ("src-1", "Test", "local", str(data_dir)),
    )
    conn.commit()

    # Scan
    subprocess.run(
        [
            str(scanner_binary),
            "--db",
            str(db_path),
            "--source-id",
            "src-1",
            "--base-path",
            str(data_dir),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    # Extract + chunk (no embed)
    content_rows = conn.execute("SELECT content_hash FROM content").fetchall()
    for row in content_rows:
        result = extract_for_content(conn, row["content_hash"], data_dir)
        chunks = chunk_text(result.text, row["content_hash"])
        save_chunks(conn, chunks)

    conn.close()

    return {"db_path": db_path, "data_dir": data_dir}


class TestQueryFlow:
    def test_retrieval_only_mode(self, indexed_env):
        """Retrieve chunks without LLM synthesis using mocked embedding search."""
        conn = get_connection(indexed_env["db_path"])

        # Get actual chunk IDs from DB
        chunks_in_db = conn.execute("SELECT id, content_hash FROM chunk").fetchall()
        assert len(chunks_in_db) > 0

        # Build mock qdrant points from real chunk data
        mock_points = []
        for i, c in enumerate(chunks_in_db[:3]):
            pt = MagicMock()
            pt.id = f"pt-{i}"
            pt.score = 0.9 - i * 0.1
            pt.payload = {"chunk_id": c["id"], "content_hash": c["content_hash"], "chunk_index": i}
            mock_points.append(pt)

        mock_client = MagicMock()
        mock_client.query_points.return_value.points = mock_points

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])

        registry = ModelRegistry()
        registry._models["embedding"] = MagicMock(
            model_id="embedding", model_type="embedding", dimensions=768
        )

        manager = ModelManager()

        with (
            patch.object(manager, "load_embedding_model", return_value=mock_model),
            patch("qdrant_client.QdrantClient", return_value=mock_client),
        ):
            result = query(
                question="what does this project do?",
                conn=conn,
                model_manager=manager,
                registry=registry,
                qdrant_path="/tmp/qdrant",
                top_k=5,
                retrieval_only=True,
            )

        assert result.retrieval_only is True
        assert result.answer is None
        assert len(result.results) > 0
        # Results should have file metadata
        for r in result.results:
            assert r.file_path
            assert r.source_id == "src-1"
        conn.close()

    def test_full_query_with_mocked_llm(self, indexed_env):
        """Full query flow with mocked embedding search and LLM synthesis."""
        conn = get_connection(indexed_env["db_path"])

        chunks_in_db = conn.execute("SELECT id, content_hash FROM chunk").fetchall()

        mock_points = []
        for i, c in enumerate(chunks_in_db[:2]):
            pt = MagicMock()
            pt.id = f"pt-{i}"
            pt.score = 0.9 - i * 0.1
            pt.payload = {"chunk_id": c["id"], "content_hash": c["content_hash"], "chunk_index": i}
            mock_points.append(pt)

        mock_qdrant = MagicMock()
        mock_qdrant.query_points.return_value.points = mock_points

        mock_embed_model = MagicMock()
        mock_embed_model.encode.return_value = np.array([[0.1] * 768])

        mock_llm = MagicMock()
        mock_llm.create_chat_completion.return_value = {
            "choices": [
                {"message": {"content": "This project processes files using Python and SQLite."}}
            ],
        }

        manager = ModelManager()

        registry = ModelRegistry()
        embed_info = MagicMock(model_id="embedding", model_type="embedding", dimensions=768)
        llm_info = MagicMock(
            model_id="llm", model_type="llm", name="test-llm", path_or_repo="/tmp/model.gguf"
        )
        registry._models["embedding"] = embed_info
        registry._models["llm"] = llm_info

        with (
            patch.object(manager, "load_embedding_model", return_value=mock_embed_model),
            patch.object(manager, "load_llm", return_value=mock_llm),
            patch("qdrant_client.QdrantClient", return_value=mock_qdrant),
        ):
            result = query(
                question="what does this project do?",
                conn=conn,
                model_manager=manager,
                registry=registry,
                qdrant_path="/tmp/qdrant",
                top_k=5,
                retrieval_only=False,
            )

        assert result.retrieval_only is False
        assert result.answer is not None
        assert "Python" in result.answer or "SQLite" in result.answer
        assert len(result.results) > 0
        mock_llm.create_chat_completion.assert_called_once()
        conn.close()

    def test_query_no_llm_configured_raises(self, indexed_env):
        """Query without LLM configured should raise RuntimeError."""
        conn = get_connection(indexed_env["db_path"])

        mock_qdrant = MagicMock()
        mock_qdrant.query_points.return_value.points = []

        mock_embed_model = MagicMock()
        mock_embed_model.encode.return_value = np.array([[0.1] * 768])

        manager = ModelManager()

        registry = ModelRegistry()
        registry._models["embedding"] = MagicMock(
            model_id="embedding", model_type="embedding", dimensions=768
        )
        # No LLM configured

        with (
            patch.object(manager, "load_embedding_model", return_value=mock_embed_model),
            patch("qdrant_client.QdrantClient", return_value=mock_qdrant),
            pytest.raises(RuntimeError, match="LLM model not configured"),
        ):
            query(
                question="test?",
                conn=conn,
                model_manager=manager,
                registry=registry,
                qdrant_path="/tmp/qdrant",
                retrieval_only=False,
            )
        conn.close()
