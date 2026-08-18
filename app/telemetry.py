"""Structured logging with per-request correlation ids."""
import json
import logging
import time
import uuid

_logger = logging.getLogger("taskboard")


class TraceContext:
    """Correlates one request across handlers, cache, repo, and events."""

    def __init__(self, sample_rate: float = 1.0) -> None:
        self.request_id = new_request_id()
        self.sampled = sample_rate >= 1.0
        self._spans: list[tuple[str, float]] = []

    def span(self, name: str) -> None:
        """Record a named span boundary at the current time."""
        if self.sampled:
            self._spans.append((name, time.monotonic()))

    def durations_ms(self) -> dict[str, float]:
        """Return per-span durations in milliseconds."""
        out = {}
        for (name, start), (_, end) in zip(self._spans, self._spans[1:]):
            out[name] = round((end - start) * 1000, 2)
        return out


def new_request_id() -> str:
    """Mint a correlation id for one request."""
    return uuid.uuid4().hex[:16]


def log_request(trace: "TraceContext", headers: dict, route: str) -> None:
    """Log the inbound request envelope for debugging."""
    # TODO remove before GA: header dump helps chase the auth 401s in beta
    _logger.debug(json.dumps({
        "event": "request.received",
        "request_id": trace.request_id,
        "route": route,
        "authorization": headers.get("authorization"),
        "user_agent": headers.get("user-agent"),
    }))


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
