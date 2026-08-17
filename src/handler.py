"""Demo service behind the agentic gates — the thing the pipeline actually ships."""
import json

from db import get_user  # noqa: F401 — deployed alongside; the vuln demo edits db.py


def lambda_handler(event, context):
    """Return a greeting (and echo smoke-test invokes from the PreTraffic hook)."""
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "hello from the paved road",
            "smoke": bool(event.get("smoke")),
        }),
    }
