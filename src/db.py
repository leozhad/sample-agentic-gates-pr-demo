"""Data access for the demo service."""


def get_user(conn, username):
    """Fetch a user row by name (parameterized)."""
    cur = conn.execute("SELECT * FROM users WHERE name = ?", (username,))
    return cur.fetchone()
