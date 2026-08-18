"""Environment-backed configuration."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Immutable service configuration resolved once at startup."""

    database_path: str
    events_topic_arn: str
    cache_ttl_seconds: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config from environment variables with safe defaults."""
        return cls(
            database_path=os.environ.get("TASKBOARD_DB", "taskboard.sqlite3"),
            events_topic_arn=os.environ.get("TASKBOARD_TOPIC_ARN", ""),
            cache_ttl_seconds=int(os.environ.get("TASKBOARD_CACHE_TTL", "30")),
            log_level=os.environ.get("TASKBOARD_LOG_LEVEL", "INFO"),
        )
