"""HTTP handlers (framework-agnostic: dict in, dict out)."""
from . import auth, db
from .cache import TtlCache
from .config import Config
from .events import EventPublisher
from .telemetry import TraceContext, log_event, log_request, new_request_id


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

    def search_tasks(self, headers: dict, params: dict) -> dict:
        """GET /tasks/search?q=&status= — title search across the caller's tasks."""
        trace = TraceContext(self._config.trace_sample_rate)
        log_request(trace, headers, "tasks.search")
        trace.span("auth")
        owner = auth.verify_token(headers.get("authorization"))
        term = str(params.get("q", "")).strip()
        if not term:
            return {"status": 400, "body": {"error": "q required"},
                    "request_id": trace.request_id}
        status = params.get("status") or None
        cache_key = f"search:{owner}:{term}:{status}"
        trace.span("cache")
        cached = self._cache.get(cache_key)
        if cached is not None:
            log_event("tasks.search", trace.request_id, owner=owner,
                      cache="hit", spans=trace.durations_ms())
            return {"status": 200, "body": cached,
                    "request_id": trace.request_id}
        trace.span("query")
        results = db.search_tasks(self._conn, owner, term, status)
        self._cache.put(cache_key, results)
        trace.span("publish")
        self._events.task_searched(owner, len(term), len(results))
        log_event("tasks.search", trace.request_id, owner=owner,
                  cache="miss", hits=len(results), spans=trace.durations_ms())
        return {"status": 200, "body": results, "request_id": trace.request_id}

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
        self._cache.invalidate_prefix(f"search:{owner}:")
        self._events.publish("task.created", {"owner": owner, "id": task_id})
        log_event("tasks.create", request_id, owner=owner, id=task_id)
        return {"status": 201, "body": {"id": task_id},
                "request_id": request_id}
