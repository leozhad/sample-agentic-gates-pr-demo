"""Handler tests with auth stubbed via environment."""
import hashlib
import os

from app.api import Api
from app.config import Config
from app.events import EventPublisher


def _api():
    os.environ["TASKBOARD_TOKEN_SECRET"] = "s3cret"
    cfg = Config(database_path=":memory:", events_topic_arn="",
                 cache_ttl_seconds=30, log_level="INFO")
    return Api(cfg, publisher=EventPublisher(""))


def _headers(principal="alice"):
    digest = hashlib.sha256(b"s3cret").hexdigest()
    return {"authorization": f"Bearer {principal}:{digest}"}


def test_create_and_list_roundtrip():
    api = _api()
    created = api.create_task(_headers(), {"title": "demo"})
    assert created["status"] == 201
    listed = api.list_tasks(_headers())
    assert listed["status"] == 200
    assert [t["title"] for t in listed["body"]] == ["demo"]


def test_create_requires_title():
    api = _api()
    assert api.create_task(_headers(), {})["status"] == 400
