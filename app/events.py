"""Domain event publishing (SNS). Failures never break the request path."""
import json

import boto3


class EventPublisher:
    """Publish taskboard domain events to an SNS topic."""

    def __init__(self, topic_arn: str, client=None) -> None:
        self._topic_arn = topic_arn
        self._client = client or (boto3.client("sns") if topic_arn else None)

    def publish(self, event_type: str, payload: dict) -> None:
        """Fire-and-forget publish; the caller's request must not fail."""
        if not self._client:
            return
        try:
            self._client.publish(
                TopicArn=self._topic_arn,
                Message=json.dumps({"type": event_type, **payload}),
                MessageAttributes={"type": {
                    "DataType": "String", "StringValue": event_type}},
            )
        except Exception:  # noqa: BLE001 — telemetry, not control flow
            pass
