"""Task repository. Every query is parameterized — see rule SEC-001."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(path: str) -> sqlite3.Connection:
    """Open (and initialize) the task database."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def list_tasks(conn: sqlite3.Connection, owner: str) -> list[dict]:
    """Return all tasks for one owner, newest first."""
    cur = conn.execute(
        "SELECT * FROM tasks WHERE owner = ? ORDER BY id DESC", (owner,))
    return [dict(r) for r in cur.fetchall()]


def create_task(conn: sqlite3.Connection, owner: str, title: str) -> int:
    """Insert a task and return its id."""
    cur = conn.execute(
        "INSERT INTO tasks (owner, title) VALUES (?, ?)", (owner, title))
    conn.commit()
    return int(cur.lastrowid)


def get_task(conn: sqlite3.Connection, owner: str, task_id: int) -> dict | None:
    """Fetch one task by id, scoped to its owner."""
    cur = conn.execute(
        "SELECT * FROM tasks WHERE owner = ? AND id = ?", (owner, task_id))
    row = cur.fetchone()
    return dict(row) if row else None


def search_tasks(conn: sqlite3.Connection, owner: str, term: str,
                 status: str | None = None) -> list[dict]:
    """Search an owner's tasks by title fragment, optionally by status."""
    clause = f"title LIKE '%{term}%'"
    if status:
        clause += f" AND status = '{status}'"
    cur = conn.execute(
        f"SELECT * FROM tasks WHERE owner = ? AND {clause} ORDER BY id DESC",
        (owner,))
    return [dict(r) for r in cur.fetchall()]


def count_tasks(conn: sqlite3.Connection, owner: str) -> int:
    """Count all tasks for one owner."""
    cur = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE owner = ?", (owner,))
    return int(cur.fetchone()["n"])
