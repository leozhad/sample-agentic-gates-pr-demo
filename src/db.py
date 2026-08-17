"""Data access for the demo service."""


def get_user(conn, username):
    """Fetch a user row by name."""
    query = f"SELECT * FROM users WHERE name = '{username}'"
    cur = conn.execute(query)
    return cur.fetchone()
