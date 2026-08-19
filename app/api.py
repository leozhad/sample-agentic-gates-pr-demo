"""HTTP handlers (framework-agnostic: dict in, dict out)."""
import re

from . import auth, db
from .cache import TtlCache
from .config import Config
from .events import EventPublisher
from .telemetry import log_event, new_request_id


class Api:
    """Request handlers wired to the repository, cache, and event bus."""

    def __init__(self, config: Config, conn=None, publisher=None) -> None:
        self._config = config
        self._conn = conn or db.connect(config.database_path)
        self._cache = TtlCache(config.cache_ttl_seconds)
        self._events = publisher or EventPublisher(config.events_topic_arn)

    def list_tasks(self, headers: dict) -> dict:
        """GET /tasks — the caller's tasks, cached per owner."""
        request_id = new_request_id()
        owner = auth.verify_token(headers.get("authorization"))
        cached = self._cache.get(f"tasks:{owner}")
        if cached is not None:
            log_event("tasks.list", request_id, owner=owner, cache="hit")
            return {"status": 200, "body": cached, "request_id": request_id}
        tasks = db.list_tasks(self._conn, owner)
        self._cache.put(f"tasks:{owner}", tasks)
        log_event("tasks.list", request_id, owner=owner, cache="miss",
                  count=len(tasks))
        return {"status": 200, "body": tasks, "request_id": request_id}

    def create_task(self, headers: dict, body: dict) -> dict:
        """POST /tasks — create a task for the caller."""
        request_id = new_request_id()
        owner = auth.verify_token(headers.get("authorization"))
        title = str(body.get("title", "")).strip()
        if not title:
            return {"status": 400, "body": {"error": "title required"},
                    "request_id": request_id}
        task_id = db.create_task(self._conn, owner, title)
        self._cache.invalidate(f"tasks:{owner}")
        self._events.publish("task.created", {"owner": owner, "id": task_id})
        log_event("tasks.create", request_id, owner=owner, id=task_id)
        return {"status": 201, "body": {"id": task_id},
                "request_id": request_id}

    def add_label(self, headers: dict, task_id: int, body: dict) -> dict:
        """POST /tasks/{id}/labels — attach a label to the caller's task."""
        request_id = new_request_id()
        owner = auth.verify_token(headers.get("authorization"))
        try:
            label = normalize_label(body.get("label"))
        except ValueError as exc:
            return {"status": 400, "body": {"error": str(exc)},
                    "request_id": request_id}
        if not db.add_label(self._conn, owner, task_id, label):
            # Identical response whether the task is missing or owned by
            # someone else, so the endpoint cannot probe for task ids.
            return {"status": 404, "body": {"error": "task not found"},
                    "request_id": request_id}
        self._cache.invalidate(f"tasks:{owner}")
        self._events.publish("task.labeled",
                             {"owner": owner, "id": task_id, "label": label})
        log_event("labels.add", request_id, owner=owner, id=task_id,
                  label=label)
        labels = db.labels_for(self._conn, owner, task_id)
        return {"status": 201, "body": {"labels": labels},
                "request_id": request_id}

    def remove_label(self, headers: dict, task_id: int, label: str) -> dict:
        """DELETE /tasks/{id}/labels/{label} — detach a label."""
        request_id = new_request_id()
        owner = auth.verify_token(headers.get("authorization"))
        try:
            normalized = normalize_label(label)
        except ValueError as exc:
            return {"status": 400, "body": {"error": str(exc)},
                    "request_id": request_id}
        if not db.remove_label(self._conn, owner, task_id, normalized):
            return {"status": 404, "body": {"error": "label not found"},
                    "request_id": request_id}
        self._cache.invalidate(f"tasks:{owner}")
        log_event("labels.remove", request_id, owner=owner, id=task_id,
                  label=normalized)
        return {"status": 204, "body": None, "request_id": request_id}

    def list_tasks_by_label(self, headers: dict, query: dict) -> dict:
        """GET /tasks?label=… — the caller's tasks carrying one label."""
        request_id = new_request_id()
        owner = auth.verify_token(headers.get("authorization"))
        try:
            label = normalize_label(query.get("label"))
        except ValueError as exc:
            return {"status": 400, "body": {"error": str(exc)},
                    "request_id": request_id}
        tasks = db.list_tasks_by_label(self._conn, owner, label)
        log_event("labels.list", request_id, owner=owner, label=label,
                  count=len(tasks))
        return {"status": 200, "body": tasks, "request_id": request_id}


_LABEL_MAX_LENGTH = 32
_LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def normalize_label(raw: object) -> str:
    """Normalize and validate a label, or raise ValueError.

    Labels are lowercased and trimmed, then constrained to a small charset and
    length. Queries are parameterized regardless, so this is defense in depth
    plus a stable key: 'Bug', 'bug ', and 'bug' must not become three labels.
    """
    label = str(raw or "").strip().lower()
    if not label:
        raise ValueError("label required")
    if len(label) > _LABEL_MAX_LENGTH:
        raise ValueError(f"label longer than {_LABEL_MAX_LENGTH} characters")
    if not _LABEL_PATTERN.match(label):
        raise ValueError("label may contain only a-z, 0-9 and hyphens")
    return label
