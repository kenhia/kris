"""Unit tests for File, Content, and Task CRUD operations."""

from __future__ import annotations

import pytest

from kris.catalog.content import (
    get_content,
    get_content_by_status,
    insert_if_not_exists,
    update_status,
)
from kris.catalog.files import (
    get_file_by_id,
    get_files_by_kind,
    get_files_by_source,
    get_files_by_status,
    insert_file,
    update_file_visibility,
    upsert_file,
)
from kris.catalog.models import Content, File, Task
from kris.catalog.tasks import (
    check_dependencies_met,
    create_task,
    get_task,
    get_tasks_by_content,
    get_tasks_by_status,
    update_task_status,
)


def _make_file(
    source_id: str,
    path: str = "/tmp/test.txt",
    content_hash: str = "abc123",
    size: int = 100,
    mtime: int = 1700000000,
    file_kind: str = "text",
    **kwargs: object,
) -> File:
    return File(
        id="",
        source_id=source_id,
        content_hash=content_hash,
        path=path,
        size=size,
        mtime=mtime,
        file_kind=file_kind,
        **kwargs,  # type: ignore[arg-type]
    )


class TestFileCRUD:
    def test_insert_and_get(self, db, sample_source):
        f = _make_file(sample_source)
        result = insert_file(db, f)
        assert result.id  # auto-generated
        fetched = get_file_by_id(db, result.id)
        assert fetched is not None
        assert fetched.path == "/tmp/test.txt"
        assert fetched.file_kind == "text"

    def test_insert_generates_uuid(self, db, sample_source):
        f = _make_file(sample_source)
        result = insert_file(db, f)
        assert len(result.id) == 36  # UUID format

    def test_upsert_inserts_new(self, db, sample_source):
        f = _make_file(sample_source, path="/tmp/new.txt")
        upsert_file(db, f)
        files = get_files_by_source(db, sample_source)
        assert len(files) == 1
        assert files[0].path == "/tmp/new.txt"

    def test_upsert_updates_existing(self, db, sample_source):
        f = _make_file(sample_source, path="/tmp/update.txt", content_hash="hash1")
        upsert_file(db, f)
        f2 = _make_file(sample_source, path="/tmp/update.txt", content_hash="hash2", size=200)
        upsert_file(db, f2)
        files = get_files_by_source(db, sample_source)
        assert len(files) == 1
        assert files[0].content_hash == "hash2"
        assert files[0].size == 200

    def test_get_files_by_source(self, db, sample_source):
        insert_file(db, _make_file(sample_source, path="/tmp/a.txt"))
        insert_file(db, _make_file(sample_source, path="/tmp/b.txt"))
        files = get_files_by_source(db, sample_source)
        assert len(files) == 2

    def test_get_files_by_source_with_visibility(self, db, sample_source):
        f = _make_file(sample_source, path="/tmp/vis.txt")
        result = insert_file(db, f)
        update_file_visibility(db, result.id, "missing", "2026-01-01T00:00:00")
        active = get_files_by_source(db, sample_source, visibility="active")
        missing = get_files_by_source(db, sample_source, visibility="missing")
        assert len(active) == 0
        assert len(missing) == 1

    def test_get_files_by_status(self, db, sample_source):
        insert_file(db, _make_file(sample_source, path="/tmp/s1.txt", processing_status="pending"))
        insert_file(
            db, _make_file(sample_source, path="/tmp/s2.txt", processing_status="completed")
        )
        pending = get_files_by_status(db, "pending")
        assert len(pending) == 1
        assert pending[0].path == "/tmp/s1.txt"

    def test_get_files_by_status_with_source(self, db, sample_source):
        insert_file(db, _make_file(sample_source, path="/tmp/fs.txt"))
        files = get_files_by_status(db, "pending", source_id=sample_source)
        assert len(files) == 1

    def test_get_files_by_kind(self, db, sample_source):
        insert_file(db, _make_file(sample_source, path="/tmp/k1.txt", file_kind="code"))
        insert_file(db, _make_file(sample_source, path="/tmp/k2.txt", file_kind="text"))
        code_files = get_files_by_kind(db, "code")
        assert len(code_files) == 1
        assert code_files[0].file_kind == "code"

    def test_update_visibility(self, db, sample_source):
        f = insert_file(db, _make_file(sample_source))
        update_file_visibility(db, f.id, "missing", "2026-03-19T00:00:00")
        updated = get_file_by_id(db, f.id)
        assert updated is not None
        assert updated.visibility == "missing"
        assert updated.disappeared_at == "2026-03-19T00:00:00"

    def test_get_nonexistent_file(self, db):
        assert get_file_by_id(db, "nonexistent") is None


class TestContentCRUD:
    def test_insert_new_content(self, db):
        c = Content(content_hash="sha256_abc")
        insert_if_not_exists(db, c)
        fetched = get_content(db, "sha256_abc")
        assert fetched is not None
        assert fetched.processing_status == "pending"

    def test_insert_ignores_duplicate(self, db):
        c1 = Content(content_hash="sha256_dup", processing_status="pending")
        c2 = Content(content_hash="sha256_dup", processing_status="completed")
        insert_if_not_exists(db, c1)
        insert_if_not_exists(db, c2)
        fetched = get_content(db, "sha256_dup")
        assert fetched is not None
        assert fetched.processing_status == "pending"  # first insert wins

    def test_update_status(self, db):
        insert_if_not_exists(db, Content(content_hash="sha256_upd"))
        update_status(db, "sha256_upd", "completed")
        fetched = get_content(db, "sha256_upd")
        assert fetched is not None
        assert fetched.processing_status == "completed"
        assert fetched.last_processed is not None

    def test_get_by_status(self, db):
        insert_if_not_exists(db, Content(content_hash="sha256_p1"))
        insert_if_not_exists(db, Content(content_hash="sha256_p2"))
        insert_if_not_exists(db, Content(content_hash="sha256_c1", processing_status="completed"))
        pending = get_content_by_status(db, "pending")
        assert len(pending) == 2

    def test_get_nonexistent_content(self, db):
        assert get_content(db, "nonexistent") is None


class TestTaskCRUD:
    @pytest.fixture
    def content_hash(self, db):
        insert_if_not_exists(db, Content(content_hash="sha256_task_test"))
        return "sha256_task_test"

    def test_create_and_get(self, db, content_hash):
        t = Task(id="", content_hash=content_hash, task_type="extract")
        result = create_task(db, t)
        assert result.id
        fetched = get_task(db, result.id)
        assert fetched is not None
        assert fetched.task_type == "extract"
        assert fetched.status == "queued"

    def test_get_tasks_by_status(self, db, content_hash):
        create_task(db, Task(id="t1", content_hash=content_hash, task_type="extract"))
        create_task(
            db, Task(id="t2", content_hash=content_hash, task_type="chunk", status="running")
        )
        queued = get_tasks_by_status(db, "queued")
        assert len(queued) == 1
        assert queued[0].id == "t1"

    def test_get_tasks_by_model_hint(self, db, content_hash):
        create_task(
            db,
            Task(
                id="t-emb",
                content_hash=content_hash,
                task_type="embed",
                model_hint="bge-base",
            ),
        )
        create_task(db, Task(id="t-ext", content_hash=content_hash, task_type="extract"))
        emb_tasks = get_tasks_by_status(db, "queued", model_hint="bge-base")
        assert len(emb_tasks) == 1
        assert emb_tasks[0].id == "t-emb"

    def test_get_tasks_by_content(self, db, content_hash):
        create_task(db, Task(id="tc1", content_hash=content_hash, task_type="extract"))
        create_task(db, Task(id="tc2", content_hash=content_hash, task_type="chunk"))
        tasks = get_tasks_by_content(db, content_hash)
        assert len(tasks) == 2

    def test_update_status_running(self, db, content_hash):
        create_task(db, Task(id="t-run", content_hash=content_hash, task_type="extract"))
        update_task_status(db, "t-run", "running")
        t = get_task(db, "t-run")
        assert t is not None
        assert t.status == "running"
        assert t.started_at is not None
        assert t.attempts == 1

    def test_update_status_completed(self, db, content_hash):
        create_task(db, Task(id="t-comp", content_hash=content_hash, task_type="extract"))
        update_task_status(db, "t-comp", "completed")
        t = get_task(db, "t-comp")
        assert t is not None
        assert t.status == "completed"
        assert t.completed_at is not None

    def test_update_status_failed_with_error(self, db, content_hash):
        create_task(db, Task(id="t-fail", content_hash=content_hash, task_type="extract"))
        update_task_status(db, "t-fail", "failed", error="Connection refused")
        t = get_task(db, "t-fail")
        assert t is not None
        assert t.status == "failed"
        assert t.error == "Connection refused"

    def test_check_dependencies_no_deps(self, db, content_hash):
        t = Task(id="t-nodep", content_hash=content_hash, task_type="extract")
        create_task(db, t)
        assert check_dependencies_met(db, t)

    def test_check_dependencies_met(self, db, content_hash):
        t1 = Task(id="dep1", content_hash=content_hash, task_type="extract", status="completed")
        create_task(db, t1)
        update_task_status(db, "dep1", "completed")
        t2 = Task(
            id="dep2",
            content_hash=content_hash,
            task_type="chunk",
            depends_on=["dep1"],
        )
        create_task(db, t2)
        assert check_dependencies_met(db, t2)

    def test_check_dependencies_not_met(self, db, content_hash):
        t1 = Task(id="dep-nm1", content_hash=content_hash, task_type="extract")
        create_task(db, t1)
        t2 = Task(
            id="dep-nm2",
            content_hash=content_hash,
            task_type="chunk",
            depends_on=["dep-nm1"],
        )
        create_task(db, t2)
        assert not check_dependencies_met(db, t2)

    def test_get_nonexistent_task(self, db):
        assert get_task(db, "nonexistent") is None

    def test_priority_ordering(self, db, content_hash):
        create_task(
            db,
            Task(id="tp-low", content_hash=content_hash, task_type="extract", priority=200),
        )
        create_task(
            db,
            Task(id="tp-high", content_hash=content_hash, task_type="extract", priority=50),
        )
        tasks = get_tasks_by_status(db, "queued")
        assert tasks[0].id == "tp-high"
        assert tasks[1].id == "tp-low"
