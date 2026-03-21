"""Tests for the task planner."""

from __future__ import annotations

from kris.catalog.models import Content
from kris.planner.planner import plan_pending_content, plan_tasks_for_content


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
