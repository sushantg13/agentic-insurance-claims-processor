"""Lambda entry point: messages from the precheck queue, one claim id each."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

from precheck.process import PrecheckDeps, precheck_claim
from shared.log import log

_deps: PrecheckDeps | None = None


def _get_deps() -> PrecheckDeps:
    global _deps
    if _deps is None:
        dynamodb = boto3.resource("dynamodb")
        _deps = PrecheckDeps(
            s3=boto3.client("s3"),
            claims=dynamodb.Table(os.environ["CLAIMS_TABLE"]),
            policies=dynamodb.Table(os.environ["POLICIES_TABLE"]),
        )
    return _deps


def handler(event: dict, context: Any) -> dict:
    deps = _get_deps()
    failures = []
    for record in event.get("Records", []):
        try:
            claim_id = json.loads(record["body"])["claim_id"]
            precheck_claim(claim_id, deps)
        except Exception as err:  # noqa: BLE001 - report the message as failed so SQS retries it
            log("precheck.message_failed", message_id=record.get("messageId"), error=repr(err))
            failures.append({"itemIdentifier": record["messageId"]})
    # Only failed messages return to the queue; after enough attempts they move to the DLQ.
    return {"batchItemFailures": failures}
