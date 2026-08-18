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
