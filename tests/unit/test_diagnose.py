"""Tests for diagnostic aggregation queries (T024-T026)."""

from __future__ import annotations

from kris.catalog.files import (
    get_failed_by_extension,
    get_failure_path_prefixes,
    get_skipped_by_kind,
)


def _seed_diagnostic_data(db):
    """Seed the DB with files in various failure/skip states."""
    db.execute(
        "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
        ("src1", "Test", "local", "/tmp"),
    )

    # Failed content: 3 .jpg files (image kind), 2 .bin files (binary kind)
    for i in range(3):
        ch = f"fail_jpg_{i}"
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, 'failed')",
            (ch,),
        )
        db.execute(
            """INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind)
               VALUES (?, 'src1', ?, ?, 100, '2024-01-01', 'image')""",
            (f"f-jpg-{i}", ch, f"photos/img_{i}.jpg"),
        )

    for i in range(2):
        ch = f"fail_bin_{i}"
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, 'failed')",
            (ch,),
        )
        db.execute(
            """INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind)
               VALUES (?, 'src1', ?, ?, 200, '2024-01-01', 'binary')""",
            (f"f-bin-{i}", ch, f"data/file_{i}.bin"),
        )

    # Skipped content: 4 image, 2 video
    for i in range(4):
        ch = f"skip_img_{i}"
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, 'skipped')",
            (ch,),
        )
        db.execute(
            """INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind)
               VALUES (?, 'src1', ?, ?, 300, '2024-01-01', 'image')""",
            (f"f-skip-img-{i}", ch, f"assets/photo_{i}.png"),
        )

    for i in range(2):
        ch = f"skip_vid_{i}"
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, 'skipped')",
            (ch,),
        )
        db.execute(
            """INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind)
               VALUES (?, 'src1', ?, ?, 500, '2024-01-01', 'video')""",
            (f"f-skip-vid-{i}", ch, f"media/clip_{i}.mp4"),
        )

    # Add more failures under "photos/" to meet min_count for path prefix test
    for i in range(3, 8):
        ch = f"fail_photos_{i}"
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, 'failed')",
            (ch,),
        )
        db.execute(
            """INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind)
               VALUES (?, 'src1', ?, ?, 100, '2024-01-01', 'image')""",
            (f"f-photos-{i}", ch, f"photos/extra_{i}.jpg"),
        )

    db.commit()


class TestGetFailedByExtension:
    """T024 — verify failure aggregation by extension."""

    def test_groups_by_extension(self, db):
        _seed_diagnostic_data(db)
        results = get_failed_by_extension(db)
        extensions = {r["extension"] for r in results}
        assert ".jpg" in extensions
        assert ".bin" in extensions

    def test_counts_are_correct(self, db):
        _seed_diagnostic_data(db)
        results = get_failed_by_extension(db)
        by_ext = {r["extension"]: r["count"] for r in results}
        assert by_ext[".jpg"] == 8  # 3 original + 5 extra
        assert by_ext[".bin"] == 2

    def test_empty_when_no_failures(self, db):
        db.execute(
            "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
            ("src1", "Test", "local", "/tmp"),
        )
        db.commit()
        results = get_failed_by_extension(db)
        assert results == []


class TestGetSkippedByKind:
    """T025 — verify skipped aggregation by kind."""

    def test_groups_by_kind(self, db):
        _seed_diagnostic_data(db)
        results = get_skipped_by_kind(db)
        by_kind = {r["file_kind"]: r["count"] for r in results}
        assert by_kind["image"] == 4
        assert by_kind["video"] == 2

    def test_empty_when_no_skipped(self, db):
        db.execute(
            "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
            ("src1", "Test", "local", "/tmp"),
        )
        db.commit()
        results = get_skipped_by_kind(db)
        assert results == []


class TestGetFailurePathPrefixes:
    """T026 — verify path prefix aggregation."""

    def test_groups_by_top_dir(self, db):
        _seed_diagnostic_data(db)
        results = get_failure_path_prefixes(db, min_count=3)
        top_dirs = {r["top_dir"] for r in results}
        assert "photos/" in top_dirs

    def test_respects_min_count(self, db):
        _seed_diagnostic_data(db)
        results = get_failure_path_prefixes(db, min_count=5)
        # "data/" has only 2 failures, should not appear
        top_dirs = {r["top_dir"] for r in results}
        assert "data/" not in top_dirs

    def test_empty_when_no_failures(self, db):
        db.execute(
            "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
            ("src1", "Test", "local", "/tmp"),
        )
        db.commit()
        results = get_failure_path_prefixes(db, min_count=1)
        assert results == []
