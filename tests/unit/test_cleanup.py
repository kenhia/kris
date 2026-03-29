"""Unit tests for cleanup operations: selector filtering, cascade delete."""

from __future__ import annotations

from kris.catalog.content import insert_if_not_exists
from kris.catalog.files import (
    cleanup_missing_files,
    get_file_by_id,
    get_files_by_source,
    insert_file,
    update_file_visibility,
)
from kris.catalog.models import Content, File


def _make_file(
    source_id: str,
    path: str = "/tmp/test.txt",
    content_hash: str = "abc123",
    size: int = 100,
    **kwargs: object,
) -> File:
    return File(
        id="",
        source_id=source_id,
        content_hash=content_hash,
        path=path,
        size=size,
        mtime=1700000000,
        file_kind="text",
        **kwargs,  # type: ignore[arg-type]
    )


class TestCleanupMissingFiles:
    """Tests for cleanup_missing_files: selector filtering and cascade deletion."""

    def test_removes_missing_file(self, db, sample_source):
        """Missing files are removed by cleanup."""
        insert_if_not_exists(db, Content(content_hash="ch1"))
        f = insert_file(db, _make_file(sample_source, content_hash="ch1"))
        update_file_visibility(db, f.id, "missing", "2026-01-01T00:00:00")
        result = cleanup_missing_files(db)
        assert result["files_removed"] == 1
        assert get_file_by_id(db, f.id) is None

    def test_keeps_active_files(self, db, sample_source):
        """Active files are not removed by cleanup."""
        insert_if_not_exists(db, Content(content_hash="ch_active"))
        insert_file(db, _make_file(sample_source, path="/active.txt", content_hash="ch_active"))
        result = cleanup_missing_files(db)
        assert result["files_removed"] == 0
        files = get_files_by_source(db, sample_source)
        assert len(files) == 1

    def test_older_than_filter(self, db, sample_source):
        """Only files missing longer than specified days are removed."""
        insert_if_not_exists(db, Content(content_hash="old_hash"))
        insert_if_not_exists(db, Content(content_hash="new_hash"))
        f_old = insert_file(
            db, _make_file(sample_source, path="/old.txt", content_hash="old_hash")
        )
        f_new = insert_file(
            db, _make_file(sample_source, path="/new.txt", content_hash="new_hash")
        )
        # Old file went missing 100 days ago
        update_file_visibility(db, f_old.id, "missing", "2025-12-10T00:00:00")
        # New file went missing just now
        update_file_visibility(db, f_new.id, "missing", "2026-03-19T00:00:00")

        result = cleanup_missing_files(db, older_than_days=30)
        assert result["files_removed"] == 1
        assert get_file_by_id(db, f_old.id) is None
        assert get_file_by_id(db, f_new.id) is not None

    def test_source_filter(self, db, sample_source):
        """Cleanup can be limited to a specific source."""
        db.execute(
            "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
            ("src-2", "Source 2", "local", "/tmp/src2"),
        )
        db.commit()
        insert_if_not_exists(db, Content(content_hash="ch_s1"))
        insert_if_not_exists(db, Content(content_hash="ch_s2"))
        f1 = insert_file(db, _make_file(sample_source, path="/a.txt", content_hash="ch_s1"))
        f2 = insert_file(db, _make_file("src-2", path="/b.txt", content_hash="ch_s2"))
        update_file_visibility(db, f1.id, "missing", "2026-01-01T00:00:00")
        update_file_visibility(db, f2.id, "missing", "2026-01-01T00:00:00")

        result = cleanup_missing_files(db, source_id=sample_source)
        assert result["files_removed"] == 1
        assert get_file_by_id(db, f1.id) is None
        assert get_file_by_id(db, f2.id) is not None

    def test_path_pattern_filter(self, db, sample_source):
        """Cleanup can be limited to files matching a path pattern."""
        insert_if_not_exists(db, Content(content_hash="ch_logs"))
        insert_if_not_exists(db, Content(content_hash="ch_data"))
        f1 = insert_file(
            db, _make_file(sample_source, path="/logs/app.log", content_hash="ch_logs")
        )
        f2 = insert_file(
            db, _make_file(sample_source, path="/data/file.csv", content_hash="ch_data")
        )
        update_file_visibility(db, f1.id, "missing", "2026-01-01T00:00:00")
        update_file_visibility(db, f2.id, "missing", "2026-01-01T00:00:00")

        result = cleanup_missing_files(db, path_pattern="%logs%")
        assert result["files_removed"] == 1
        assert get_file_by_id(db, f1.id) is None
        assert get_file_by_id(db, f2.id) is not None

    def test_cascade_deletes_chunks_and_embeddings(self, db, sample_source):
        """Cleanup cascades to remove chunks and embeddings for orphaned content."""
        insert_if_not_exists(db, Content(content_hash="ch_cascade"))
        f = insert_file(
            db, _make_file(sample_source, path="/cascade.txt", content_hash="ch_cascade")
        )
        # Add associated chunk and embedding
        db.execute(
            "INSERT INTO chunk (id, content_hash, chunk_index, chunk_content_hash, "
            "content, start_offset, end_offset, chunking_strategy) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("chunk-1", "ch_cascade", 0, "chunk_hash_1", "text", 0, 4, "text"),
        )
        db.execute(
            "INSERT INTO embedding (id, chunk_id, model_id, index_name, opensearch_doc_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("emb-1", "chunk-1", "model-1", "kris_chunks", "point-1"),
        )
        db.commit()

        update_file_visibility(db, f.id, "missing", "2026-01-01T00:00:00")
        result = cleanup_missing_files(db)
        assert result["files_removed"] == 1
        assert result["chunks_removed"] >= 1
        assert result["embeddings_removed"] >= 1

        # Verify cascade
        chunks = db.execute(
            "SELECT COUNT(*) FROM chunk WHERE content_hash = ?", ("ch_cascade",)
        ).fetchone()[0]
        assert chunks == 0
        embeddings = db.execute(
            "SELECT COUNT(*) FROM embedding WHERE chunk_id = ?", ("chunk-1",)
        ).fetchone()[0]
        assert embeddings == 0

    def test_dry_run_returns_counts_without_deleting(self, db, sample_source):
        """Dry run returns counts but doesn't actually delete."""
        insert_if_not_exists(db, Content(content_hash="ch_dry"))
        f = insert_file(db, _make_file(sample_source, path="/dry.txt", content_hash="ch_dry"))
        update_file_visibility(db, f.id, "missing", "2026-01-01T00:00:00")

        result = cleanup_missing_files(db, dry_run=True)
        assert result["files_removed"] == 1
        # File should still exist after dry run
        assert get_file_by_id(db, f.id) is not None

    def test_collects_opensearch_doc_ids(self, db, sample_source):
        """Cleanup returns OpenSearch document IDs for external deletion."""
        insert_if_not_exists(db, Content(content_hash="ch_qdrant"))
        f = insert_file(
            db, _make_file(sample_source, path="/qdrant.txt", content_hash="ch_qdrant")
        )
        db.execute(
            "INSERT INTO chunk (id, content_hash, chunk_index, chunk_content_hash, "
            "content, start_offset, end_offset, chunking_strategy) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("chunk-q", "ch_qdrant", 0, "chunk_hash_q", "text", 0, 4, "text"),
        )
        db.execute(
            "INSERT INTO embedding (id, chunk_id, model_id, index_name, opensearch_doc_id) "
            "VALUES (?, ?, ?, ?, ?)",
            ("emb-q", "chunk-q", "model-1", "kris_chunks", "qdrant-point-abc"),
        )
        db.commit()

        update_file_visibility(db, f.id, "missing", "2026-01-01T00:00:00")
        result = cleanup_missing_files(db)
        assert "qdrant-point-abc" in result["opensearch_doc_ids"]
