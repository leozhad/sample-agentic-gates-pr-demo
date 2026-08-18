"""Structured logging with per-request correlation ids."""
import json
import logging
import time
import uuid

_logger = logging.getLogger("taskboard")


def new_request_id() -> str:
    """Mint a correlation id for one request."""
    return uuid.uuid4().hex[:16]


def log_event(event: str, request_id: str, **fields) -> None:
    """Emit one structured log line.

    Fields are caller-provided key/values; never pass secrets or raw
    credentials here — log lines outlive requests.
    """
    _logger.info(json.dumps({
        "event": event,
        "request_id": request_id,
        "ts": round(time.time(), 3),
        **fields,
    }))
