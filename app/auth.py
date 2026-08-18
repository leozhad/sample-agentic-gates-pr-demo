"""Bearer-token verification for taskboard requests."""
import hashlib
import hmac
import os


class AuthError(Exception):
    """Raised when a request cannot be authenticated."""


def _expected_digest() -> str:
    secret = os.environ.get("TASKBOARD_TOKEN_SECRET", "")
    if not secret:
        raise AuthError("server missing token secret")
    return hashlib.sha256(secret.encode()).hexdigest()


def verify_token(authorization_header: str | None) -> str:
    """Validate a Bearer token; return the principal name.

    The token format is '<principal>:<sha256(secret)>'. Comparison is
    constant-time. The raw header must never be logged.
    """
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise AuthError("missing bearer token")
    token = authorization_header.removeprefix("Bearer ")
    principal, _, digest = token.partition(":")
    if not principal or not hmac.compare_digest(digest, _expected_digest()):
        raise AuthError("invalid token")
    return principal
