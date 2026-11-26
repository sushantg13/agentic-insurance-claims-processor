"""Lambda entry point: messages from the assessment queue, one claim id each."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

from claims.assessment import start_assessment
from claims.log import log

_claims_table = None


def _get_claims_table():
    global _claims_table
    if _claims_table is None:
        _claims_table = boto3.resource("dynamodb").Table(os.environ["CLAIMS_TABLE"])
    return _claims_table


def handler(event: dict, context: Any) -> dict:
    table = _get_claims_table()
    failures = []
    for record in event.get("Records", []):
        try:
            claim_id = json.loads(record["body"])["claim_id"]
            start_assessment(claim_id, table)
        except Exception as err:  # noqa: BLE001 - report the message as failed so SQS retries it
            log("assessment.message_failed", message_id=record.get("messageId"), error=repr(err))
            failures.append({"itemIdentifier": record["messageId"]})
    # Only failed messages return to the queue; after enough attempts they move to the DLQ.
    return {"batchItemFailures": failures}
