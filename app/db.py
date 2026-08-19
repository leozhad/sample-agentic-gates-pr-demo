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

CREATE TABLE IF NOT EXISTS task_labels (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    PRIMARY KEY (task_id, label)
);

CREATE INDEX IF NOT EXISTS idx_task_labels_label ON task_labels(label);
"""


def connect(path: str) -> sqlite3.Connection:
    """Open (and initialize) the task database."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # Required for the ON DELETE CASCADE on task_labels: SQLite enforces
    # foreign keys per-connection and defaults to off.
    conn.execute("PRAGMA foreign_keys = ON")
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


def add_label(conn: sqlite3.Connection, owner: str, task_id: int,
              label: str) -> bool:
    """Attach a label to one of the owner's tasks.

    Ownership is enforced inside the statement rather than by a preceding
    SELECT, so there is no window between the check and the write. Returns
    False when the task does not exist or belongs to someone else.
    """
    cur = conn.execute(
        "INSERT OR IGNORE INTO task_labels (task_id, label) "
        "SELECT id, ? FROM tasks WHERE id = ? AND owner = ?",
        (label, task_id, owner))
    conn.commit()
    return cur.rowcount > 0


def remove_label(conn: sqlite3.Connection, owner: str, task_id: int,
                 label: str) -> bool:
    """Detach a label, returning False when nothing matched."""
    cur = conn.execute(
        "DELETE FROM task_labels WHERE label = ? AND task_id IN "
        "(SELECT id FROM tasks WHERE id = ? AND owner = ?)",
        (label, task_id, owner))
    conn.commit()
    return cur.rowcount > 0


def labels_for(conn: sqlite3.Connection, owner: str, task_id: int) -> list[str]:
    """Return the labels on one of the owner's tasks, alphabetically."""
    cur = conn.execute(
        "SELECT l.label FROM task_labels AS l "
        "JOIN tasks AS t ON t.id = l.task_id "
        "WHERE l.task_id = ? AND t.owner = ? ORDER BY l.label",
        (task_id, owner))
    return [row["label"] for row in cur.fetchall()]


def list_tasks_by_label(conn: sqlite3.Connection, owner: str,
                        label: str) -> list[dict]:
    """Return the owner's tasks carrying `label`, newest first."""
    cur = conn.execute(
        "SELECT t.* FROM tasks AS t "
        "JOIN task_labels AS l ON l.task_id = t.id "
        "WHERE t.owner = ? AND l.label = ? ORDER BY t.id DESC",
        (owner, label))
    return [dict(row) for row in cur.fetchall()]
