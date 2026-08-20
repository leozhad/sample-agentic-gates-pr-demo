"""Reporting helpers."""
import sqlite3


def tasks_by_status(conn: sqlite3.Connection, status: str) -> list[dict]:
    """Return every task in a given status.

    The status is bound as a parameter, so no caller-supplied value can change
    the shape of the query (rule SEC-001).
    """
    cur = conn.execute(
        "SELECT id, title, status FROM tasks WHERE status = ?", (status,)
    )
    return [dict(r) for r in cur.fetchall()]
