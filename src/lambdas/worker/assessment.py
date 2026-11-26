"""Start a claim's assessment. For now this only moves the claim to ASSESSING.

The AI pipeline will replace the body of start_assessment. The queue, retries
and dead-letter handling around it stay the same.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from botocore.exceptions import ClientError

from shared.log import log

STATUS_RECEIVED = "RECEIVED"
STATUS_ASSESSING = "ASSESSING"


class StartOutcome(str, Enum):
    STARTED = "STARTED"
    ALREADY_STARTED = "ALREADY_STARTED"
    NOT_FOUND = "NOT_FOUND"


def start_assessment(
    claim_id: str,
    claims: Any,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> StartOutcome:
    timestamp = now().isoformat()
    try:
        claims.update_item(
            Key={"claim_id": claim_id},
            UpdateExpression="SET #status = :assessing, assessment_started_at = :ts, updated_at = :ts",
            ConditionExpression="attribute_exists(claim_id) AND #status = :received",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":assessing": STATUS_ASSESSING,
                ":received": STATUS_RECEIVED,
                ":ts": timestamp,
            },
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        item = claims.get_item(Key={"claim_id": claim_id}, ConsistentRead=True).get("Item")
        if item is None:
            log("assessment.claim_not_found", claim_id=claim_id)
            return StartOutcome.NOT_FOUND
        # A redelivered message for a claim that is already past RECEIVED: nothing to redo.
        log("assessment.already_started", claim_id=claim_id, status=item.get("status"))
        return StartOutcome.ALREADY_STARTED

    log("assessment.started", claim_id=claim_id)
    return StartOutcome.STARTED
