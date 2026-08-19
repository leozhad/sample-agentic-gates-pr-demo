"""Repository tests against an in-memory database."""
from app import db


def _conn():
    return db.connect(":memory:")


def test_create_then_list_scopes_by_owner():
    conn = _conn()
    db.create_task(conn, "alice", "write spec")
    db.create_task(conn, "bob", "other work")
    tasks = db.list_tasks(conn, "alice")
    assert [t["title"] for t in tasks] == ["write spec"]


def test_get_task_wrong_owner_returns_none():
    conn = _conn()
    task_id = db.create_task(conn, "alice", "private")
    assert db.get_task(conn, "bob", task_id) is None


def test_add_label_rejects_other_owners_task():
    conn = _conn()
    task_id = db.create_task(conn, "alice", "private")
    assert db.add_label(conn, "bob", task_id, "urgent") is False
    assert db.labels_for(conn, "alice", task_id) == []


def test_labels_roundtrip_and_filter():
    conn = _conn()
    first = db.create_task(conn, "alice", "write spec")
    second = db.create_task(conn, "alice", "review spec")
    assert db.add_label(conn, "alice", first, "urgent") is True
    assert db.add_label(conn, "alice", second, "urgent") is True
    assert db.add_label(conn, "alice", first, "docs") is True
    assert db.labels_for(conn, "alice", first) == ["docs", "urgent"]
    titles = [t["title"] for t in db.list_tasks_by_label(conn, "alice", "urgent")]
    assert titles == ["review spec", "write spec"]


def test_add_label_is_idempotent_and_remove_reports_misses():
    conn = _conn()
    task_id = db.create_task(conn, "alice", "write spec")
    assert db.add_label(conn, "alice", task_id, "urgent") is True
    assert db.add_label(conn, "alice", task_id, "urgent") is False
    assert db.remove_label(conn, "alice", task_id, "urgent") is True
    assert db.remove_label(conn, "alice", task_id, "urgent") is False
