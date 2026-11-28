"""Precheck one lodged claim.

Intake's claim item is only used to find the evidence. The claim itself is
re-read from the write-once evidence bucket, its hash checked against the one
recorded at intake, and the policy read fresh from the policies table. The
policy as seen is stored with the result, so the audit record shows exactly
what the checks ran against even if the register changes later.

The result moves the claim from RECEIVED to PRECHECKED, INELIGIBLE or
NEEDS_REVIEW in one conditional write. Only PRECHECKED claims are picked up
by the stream for assessment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from botocore.exceptions import ClientError

from precheck.checks import Check, Outcome, Precheck, Result, run_checks
from shared.log import log

STATUS_RECEIVED = "RECEIVED"
STATUS_FOR_OUTCOME = {
    Outcome.ELIGIBLE: "PRECHECKED",
    Outcome.INELIGIBLE: "INELIGIBLE",
    Outcome.NEEDS_REVIEW: "NEEDS_REVIEW",
}


class RunOutcome(str, Enum):
    DONE = "DONE"
    ALREADY_DONE = "ALREADY_DONE"
    NOT_FOUND = "NOT_FOUND"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PrecheckDeps:
    """Everything the precheck touches, passed in so tests can supply fakes."""

    s3: Any
    claims: Any
    policies: Any
    now: Callable[[], datetime] = field(default=_utc_now)


def precheck_claim(claim_id: str, deps: PrecheckDeps) -> RunOutcome:
    item = deps.claims.get_item(Key={"claim_id": claim_id}, ConsistentRead=True).get("Item")
    if item is None:
        log("precheck.claim_not_found", claim_id=claim_id)
        return RunOutcome.NOT_FOUND
    if item.get("status") != STATUS_RECEIVED:
        # A redelivered message for a claim that is already past RECEIVED.
        log("precheck.already_done", claim_id=claim_id, status=item.get("status"))
        return RunOutcome.ALREADY_DONE

    claim, integrity = _load_claim(deps.s3, item)
    if integrity.result is Result.FAIL:
        pre, policy = Precheck(Outcome.NEEDS_REVIEW, [integrity]), None
    else:
        policy = _get_policy(deps.policies, claim)
        pre = run_checks(claim, policy)
        pre.checks.insert(0, integrity)

    record = pre.to_item()
    record["checked_at"] = deps.now().isoformat()
    if policy is not None:
        record["policy_as_seen"] = policy
    status = STATUS_FOR_OUTCOME[pre.outcome]

    try:
        deps.claims.update_item(
            Key={"claim_id": claim_id},
            UpdateExpression="SET #status = :status, precheck = :precheck, updated_at = :ts",
            ConditionExpression="#status = :received",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": status,
                ":precheck": record,
                ":received": STATUS_RECEIVED,
                ":ts": record["checked_at"],
            },
        )
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        log("precheck.already_done", claim_id=claim_id)
        return RunOutcome.ALREADY_DONE

    log(
        "precheck." + pre.outcome.value.lower(),
        claim_id=claim_id,
        status=status,
        failed=[c.name for c in pre.checks if c.result is Result.FAIL],
        flags=[f.code for f in pre.flags],
    )
    return RunOutcome.DONE


def _load_claim(s3: Any, item: dict) -> tuple[Any, Check]:
    """Read the claim JSON from the evidence bucket and confirm it is the copy intake stored."""
    record = next((e for e in item.get("evidence", []) if e.get("kind") == "claim"), None)
    if record is None:
        return None, Check("evidence_intact", Result.FAIL, "claim item lists no evidence copy of the claim")

    bucket, key = record["stored_at"].removeprefix("s3://").split("/", 1)
    request = {"Bucket": bucket, "Key": key}
    if record.get("version_id"):
        request["VersionId"] = record["version_id"]
    try:
        body = s3.get_object(**request)["Body"].read()
    except ClientError as err:
        if err.response["Error"]["Code"] not in ("NoSuchKey", "NoSuchVersion", "404"):
            raise
        return None, Check("evidence_intact", Result.FAIL, f"evidence copy is missing: {record['stored_at']}")

    sha = hashlib.sha256(body).hexdigest()
    if sha != record.get("sha256") or sha != item.get("submission_sha256"):
        return None, Check("evidence_intact", Result.FAIL, "evidence copy does not match the hash recorded at intake")

    try:
        claim = json.loads(body)
    except (UnicodeDecodeError, ValueError):
        return None, Check("evidence_intact", Result.FAIL, "evidence copy is not valid JSON")
    return claim, Check("evidence_intact", Result.PASS, f"sha256 {sha[:12]}… matches intake")


def _get_policy(policies: Any, claim: Any) -> dict | None:
    policy_id = claim.get("policy_id") if isinstance(claim, dict) else None
    if not isinstance(policy_id, str) or not policy_id:
        return None
    return policies.get_item(Key={"policy_id": policy_id}, ConsistentRead=True).get("Item")
