"""Tests for the task planner."""

from __future__ import annotations

from kris.catalog.models import Content
from kris.planner.planner import EXTRACTABLE_KINDS, plan_pending_content, plan_tasks_for_content


class TestPlanTasksForContent:
    def test_creates_three_tasks(self, db):
        content = Content(content_hash="hash_abc")
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
            (content.content_hash, "pending"),
        )
        db.commit()

        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 3

        types = [t.task_type for t in tasks]
        assert types == ["extract", "chunk", "embed"]

    def test_dependency_chain(self, db):
        content = Content(content_hash="hash_dep")
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
            (content.content_hash, "pending"),
        )
        db.commit()

        tasks = plan_tasks_for_content(db, content)
        extract, chunk, embed = tasks

        assert extract.depends_on == []
        assert chunk.depends_on == [extract.id]
        assert embed.depends_on == [chunk.id]

    def test_embed_has_model_hint(self, db):
        content = Content(content_hash="hash_hint")
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
            (content.content_hash, "pending"),
        )
        db.commit()

        tasks = plan_tasks_for_content(db, content, embedding_model_hint="my_model")
        embed = tasks[2]
        assert embed.model_hint == "my_model"

    def test_no_duplicate_tasks(self, db):
        content = Content(content_hash="hash_dup")
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
            (content.content_hash, "pending"),
        )
        db.commit()

        tasks1 = plan_tasks_for_content(db, content)
        tasks2 = plan_tasks_for_content(db, content)
        assert len(tasks1) == 3
        assert len(tasks2) == 0  # no new tasks

    def test_priority_ordering(self, db):
        content = Content(content_hash="hash_prio")
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
            (content.content_hash, "pending"),
        )
        db.commit()

        tasks = plan_tasks_for_content(db, content)
        priorities = [t.priority for t in tasks]
        assert priorities == sorted(priorities)


class TestPlanPendingContent:
    def test_plans_multiple_content(self, db):
        for i in range(3):
            db.execute(
                "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
                (f"hash_{i}", "pending"),
            )
        db.commit()

        planned = plan_pending_content(db)
        assert planned == 3

        count = db.execute("SELECT COUNT(*) FROM task").fetchone()[0]
        assert count == 9  # 3 tasks per content x 3 content

    def test_skips_completed_content(self, db):
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, ?)",
            ("hash_done", "completed"),
        )
        db.commit()

        planned = plan_pending_content(db)
        assert planned == 0


class TestPlannerSkipLogic:
    """T022, T023 — non-extractable file kinds are skipped, extractable get 3 tasks."""

    def _insert_file_and_content(self, db, content_hash, file_kind):
        db.execute(
            "INSERT INTO content (content_hash, processing_status) VALUES (?, 'pending')",
            (content_hash,),
        )
        db.execute(
            "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
            ("src1", "Test", "local", "/tmp"),
        )
        db.execute(
            """INSERT INTO file (id, source_id, content_hash, path, size, mtime, file_kind)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                f"file-{content_hash}",
                "src1",
                content_hash,
                f"test.{file_kind}",
                100,
                "2024-01-01",
                file_kind,
            ),
        )
        db.commit()

    def test_skips_image_kind(self, db):
        self._insert_file_and_content(db, "hash_img", "image")
        content = Content(content_hash="hash_img")
        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 0
        status = db.execute(
            "SELECT processing_status FROM content WHERE content_hash = ?", ("hash_img",)
        ).fetchone()["processing_status"]
        assert status == "skipped"

    def test_skips_binary_kind(self, db):
        self._insert_file_and_content(db, "hash_bin", "binary")
        content = Content(content_hash="hash_bin")
        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 0

    def test_skips_archive_kind(self, db):
        self._insert_file_and_content(db, "hash_arc", "archive")
        content = Content(content_hash="hash_arc")
        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 0

    def test_skips_video_kind(self, db):
        self._insert_file_and_content(db, "hash_vid", "video")
        content = Content(content_hash="hash_vid")
        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 0

    def test_skips_audio_kind(self, db):
        self._insert_file_and_content(db, "hash_aud", "audio")
        content = Content(content_hash="hash_aud")
        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 0

    def test_skips_unknown_kind(self, db):
        self._insert_file_and_content(db, "hash_unk", "unknown")
        content = Content(content_hash="hash_unk")
        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 0

    def test_extractable_text_gets_tasks(self, db):
        self._insert_file_and_content(db, "hash_txt", "text")
        content = Content(content_hash="hash_txt")
        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 3

    def test_extractable_code_gets_tasks(self, db):
        self._insert_file_and_content(db, "hash_code", "code")
        content = Content(content_hash="hash_code")
        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 3

    def test_extractable_markdown_gets_tasks(self, db):
        self._insert_file_and_content(db, "hash_md", "markdown")
        content = Content(content_hash="hash_md")
        tasks = plan_tasks_for_content(db, content)
        assert len(tasks) == 3

    def test_all_extractable_kinds_defined(self):
        assert {"text", "code", "markdown", "config", "data"} == EXTRACTABLE_KINDS
