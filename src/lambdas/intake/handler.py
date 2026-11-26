"""Lambda entry point: S3 ObjectCreated events from the inbox bucket."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import unquote_plus

import boto3

from intake.process import IntakeDeps, process_object

_deps: IntakeDeps | None = None


def _get_deps() -> IntakeDeps:
    global _deps
    if _deps is None:
        dynamodb = boto3.resource("dynamodb")
        _deps = IntakeDeps(
            s3=boto3.client("s3"),
            claims=dynamodb.Table(os.environ["CLAIMS_TABLE"]),
            policies=dynamodb.Table(os.environ["POLICIES_TABLE"]),
            intake_log=dynamodb.Table(os.environ["INTAKE_LOG_TABLE"]),
            evidence_bucket=os.environ["EVIDENCE_BUCKET"],
        )
    return _deps


def handler(event: dict, context: Any) -> dict:
    deps = _get_deps()
    results = []
    for record in event.get("Records", []):
        s3_info = record["s3"]
        # S3 URL-encodes object keys in event notifications.
        key = unquote_plus(s3_info["object"]["key"])
        result = process_object(
            bucket=s3_info["bucket"]["name"],
            key=key,
            sequencer=s3_info["object"].get("sequencer", ""),
            deps=deps,
        )
        results.append({"source": result.source, "outcome": result.outcome.value, "claim_id": result.claim_id})
    # Unexpected errors propagate, so Lambda retries and then sends the event to the failure queue.
    return {"results": results}
