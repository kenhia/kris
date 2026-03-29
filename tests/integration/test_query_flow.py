"""Integration test for full query flow: query -> embed -> search -> enrich -> synthesize."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from kris.catalog.db import get_connection
from kris.config.schema import KrisConfig, OpenSearchConfig
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
    def test_retrieval_only_mode(self, indexed_env, tmp_path):
        """Retrieve chunks without LLM synthesis using mocked OpenSearch search."""
        conn = get_connection(indexed_env["db_path"])

        # Get actual chunk IDs from DB
        chunks_in_db = conn.execute("SELECT id, content_hash FROM chunk").fetchall()
        assert len(chunks_in_db) > 0

        # Build mock OpenSearch search response
        hits = []
        for i, c in enumerate(chunks_in_db[:3]):
            chunk_row = conn.execute("SELECT * FROM chunk WHERE id = ?", (c["id"],)).fetchone()
            file_row = conn.execute(
                "SELECT * FROM file WHERE content_hash = ? LIMIT 1", (c["content_hash"],)
            ).fetchone()
            hits.append(
                {
                    "_id": f"doc-{i}",
                    "_score": 0.9 - i * 0.1,
                    "_source": {
                        "chunk_id": c["id"],
                        "content": chunk_row["content"],
                        "content_hash": c["content_hash"],
                        "chunk_index": i,
                        "file_kind": file_row["file_kind"] if file_row else "text",
                        "source_id": file_row["source_id"] if file_row else "src-1",
                        "file_path": file_row["path"] if file_row else "",
                    },
                }
            )

        mock_client = MagicMock()
        mock_client.indices.exists.return_value = True
        mock_client.search.return_value = {"hits": {"total": {"value": len(hits)}, "hits": hits}}

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 768])

        config = KrisConfig(
            data_dir=str(tmp_path),
            opensearch=OpenSearchConfig(url="https://localhost:9200"),
        )

        registry = ModelRegistry()
        registry._models["embedding"] = MagicMock(
            model_id="embedding", model_type="embedding", dimensions=768
        )

        manager = ModelManager()

        with (
            patch.object(manager, "load_embedding_model", return_value=mock_model),
            patch("kris.processing.embed.create_opensearch_client", return_value=mock_client),
        ):
            result = query(
                question="what does this project do?",
                conn=conn,
                model_manager=manager,
                registry=registry,
                config=config,
                top_k=5,
                retrieval_only=True,
            )

        assert result.retrieval_only is True
        assert result.answer is None
        assert len(result.results) > 0
        for r in result.results:
            assert r.file_path
            assert r.source_id == "src-1"
        conn.close()

    def test_full_query_with_mocked_llm(self, indexed_env, tmp_path):
        """Full query flow with mocked embedding search and LLM synthesis."""
        conn = get_connection(indexed_env["db_path"])

        chunks_in_db = conn.execute("SELECT id, content_hash FROM chunk").fetchall()

        hits = []
        for i, c in enumerate(chunks_in_db[:2]):
            chunk_row = conn.execute("SELECT * FROM chunk WHERE id = ?", (c["id"],)).fetchone()
            file_row = conn.execute(
                "SELECT * FROM file WHERE content_hash = ? LIMIT 1", (c["content_hash"],)
            ).fetchone()
            hits.append(
                {
                    "_id": f"doc-{i}",
                    "_score": 0.9 - i * 0.1,
                    "_source": {
                        "chunk_id": c["id"],
                        "content": chunk_row["content"],
                        "content_hash": c["content_hash"],
                        "chunk_index": i,
                        "file_kind": file_row["file_kind"] if file_row else "text",
                        "source_id": file_row["source_id"] if file_row else "src-1",
                        "file_path": file_row["path"] if file_row else "",
                    },
                }
            )

        mock_os_client = MagicMock()
        mock_os_client.indices.exists.return_value = True
        mock_os_client.search.return_value = {
            "hits": {"total": {"value": len(hits)}, "hits": hits}
        }

        mock_embed_model = MagicMock()
        mock_embed_model.encode.return_value = np.array([[0.1] * 768])

        mock_llm = MagicMock()
        mock_llm.create_chat_completion.return_value = {
            "choices": [
                {"message": {"content": "This project processes files using Python and SQLite."}}
            ],
        }

        config = KrisConfig(
            data_dir=str(tmp_path),
            opensearch=OpenSearchConfig(url="https://localhost:9200"),
        )

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
            patch("kris.processing.embed.create_opensearch_client", return_value=mock_os_client),
        ):
            result = query(
                question="what does this project do?",
                conn=conn,
                model_manager=manager,
                registry=registry,
                config=config,
                top_k=5,
                retrieval_only=False,
            )

        assert result.retrieval_only is False
        assert result.answer is not None
        assert "Python" in result.answer or "SQLite" in result.answer
        assert len(result.results) > 0
        mock_llm.create_chat_completion.assert_called_once()
        conn.close()

    def test_query_no_llm_configured_raises(self, indexed_env, tmp_path):
        """Query without LLM configured should raise RuntimeError."""
        conn = get_connection(indexed_env["db_path"])

        mock_os_client = MagicMock()
        mock_os_client.indices.exists.return_value = True
        mock_os_client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}

        mock_embed_model = MagicMock()
        mock_embed_model.encode.return_value = np.array([[0.1] * 768])

        config = KrisConfig(
            data_dir=str(tmp_path),
            opensearch=OpenSearchConfig(url="https://localhost:9200"),
        )

        manager = ModelManager()

        registry = ModelRegistry()
        registry._models["embedding"] = MagicMock(
            model_id="embedding", model_type="embedding", dimensions=768
        )
        # No LLM configured

        with (
            patch.object(manager, "load_embedding_model", return_value=mock_embed_model),
            patch("kris.processing.embed.create_opensearch_client", return_value=mock_os_client),
            pytest.raises(RuntimeError, match="LLM model not configured"),
        ):
            query(
                question="test?",
                conn=conn,
                model_manager=manager,
                registry=registry,
                config=config,
                retrieval_only=False,
            )
        conn.close()
