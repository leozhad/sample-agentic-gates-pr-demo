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


def test_add_label_then_filter_by_it():
    api = _api()
    task_id = api.create_task(_headers(), {"title": "demo"})["body"]["id"]
    added = api.add_label(_headers(), task_id, {"label": "Urgent "})
    assert added["status"] == 201
    assert added["body"]["labels"] == ["urgent"]          # normalized
    filtered = api.list_tasks_by_label(_headers(), {"label": "urgent"})
    assert [t["title"] for t in filtered["body"]] == ["demo"]


def test_label_validation_rejects_bad_input():
    api = _api()
    task_id = api.create_task(_headers(), {"title": "demo"})["body"]["id"]
    assert api.add_label(_headers(), task_id, {})["status"] == 400
    assert api.add_label(_headers(), task_id, {"label": "not valid!"})["status"] == 400
    assert api.add_label(_headers(), task_id, {"label": "x" * 33})["status"] == 400


def test_labeling_another_principals_task_is_not_found():
    api = _api()
    task_id = api.create_task(_headers("alice"), {"title": "private"})["body"]["id"]
    assert api.add_label(_headers("bob"), task_id, {"label": "urgent"})["status"] == 404
