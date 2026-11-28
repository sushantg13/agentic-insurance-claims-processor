"""Lodge a claim from the inbox bucket.

For each claim JSON dropped in the inbox:

1. Ignore anything that is not a claim file, such as an answer key.
2. Reject a payload that is not valid JSON or fails the shape checks.
3. If the claim id is already lodged: same content is a duplicate, different
   content is a conflict. Neither overwrites the original.
4. Reject if the policy is unknown or belongs to another policyholder, or if a
   listed attachment is missing.
5. Copy the claim and its attachments to the write-once evidence bucket, under
   a key that includes the submission's hash, so a retry rewrites identical bytes.
6. Write the claim item only if its id does not exist yet. The DynamoDB stream
   then queues it for the precheck.

Every decision is recorded in the intake log with its reasons.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

from botocore.exceptions import ClientError

from shared.log import log
from shared.validation import validate_claim

CLAIM_STATUS_RECEIVED = "RECEIVED"
ITEM_SCHEMA_VERSION = 1


class Outcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"
    REJECTED = "REJECTED"
    IGNORED = "IGNORED"


@dataclass(frozen=True)
class IntakeResult:
    outcome: Outcome
    source: str
    claim_id: str | None = None
    reasons: tuple[str, ...] = ()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class IntakeDeps:
    """Everything intake touches, passed in so tests can supply fakes."""

    s3: Any
    claims: Any
    policies: Any
    intake_log: Any
    evidence_bucket: str
    now: Callable[[], datetime] = field(default=_utc_now)


def is_claim_key(key: str) -> bool:
    name = posixpath.basename(key)
    return name.startswith("claim-") and name.endswith(".json")


def process_object(bucket: str, key: str, sequencer: str, deps: IntakeDeps) -> IntakeResult:
    source = f"s3://{bucket}/{key}"
    intake_id = f"{source}#{sequencer}"

    if not is_claim_key(key):
        result = IntakeResult(Outcome.IGNORED, source, reasons=("not a claim file",))
        log("intake.ignored", source=source)
        return result

    body = _read_object(deps.s3, bucket, key)
    if body is None:
        return _finish(deps, intake_id, IntakeResult(Outcome.REJECTED, source, reasons=("claim file no longer exists",)))

    submission_sha = _sha256(body)

    try:
        doc = json.loads(body)
    except (UnicodeDecodeError, ValueError):
        return _finish(deps, intake_id, IntakeResult(Outcome.REJECTED, source, reasons=("claim file is not valid JSON",)))

    errors = validate_claim(doc)
    if errors:
        claim_id = doc.get("claim_id") if isinstance(doc, dict) and isinstance(doc.get("claim_id"), str) else None
        return _finish(deps, intake_id, IntakeResult(Outcome.REJECTED, source, claim_id, tuple(errors)))

    claim_id = doc["claim_id"]

    existing = deps.claims.get_item(Key={"claim_id": claim_id}, ConsistentRead=True).get("Item")
    if existing:
        return _finish(deps, intake_id, _classify_existing(existing, claim_id, source, intake_id, submission_sha))

    policy = deps.policies.get_item(Key={"policy_id": doc["policy_id"]}).get("Item")
    if not policy:
        return _finish(deps, intake_id, IntakeResult(Outcome.REJECTED, source, claim_id, ("policy not found",)))
    if policy.get("policyholder_id") != doc["policyholder_id"]:
        return _finish(
            deps,
            intake_id,
            IntakeResult(Outcome.REJECTED, source, claim_id, ("policy does not belong to this policyholder",)),
        )

    folder = posixpath.dirname(key)
    attachments, missing = _read_attachments(deps.s3, bucket, folder, doc.get("attachments", []))
    if missing:
        reasons = tuple(f"attachment not found: {name}" for name in missing)
        return _finish(deps, intake_id, IntakeResult(Outcome.REJECTED, source, claim_id, reasons))

    evidence = _store_evidence(deps, claim_id, submission_sha, posixpath.basename(key), body, attachments)
    item = _claim_item(doc, policy, source, intake_id, submission_sha, evidence, deps.now())

    try:
        deps.claims.put_item(Item=item, ConditionExpression="attribute_not_exists(claim_id)")
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        # Another upload of the same claim id won the race.
        existing = deps.claims.get_item(Key={"claim_id": claim_id}, ConsistentRead=True)["Item"]
        return _finish(deps, intake_id, _classify_existing(existing, claim_id, source, intake_id, submission_sha))

    return _finish(deps, intake_id, IntakeResult(Outcome.ACCEPTED, source, claim_id))


def _classify_existing(existing: dict, claim_id: str, source: str, intake_id: str, submission_sha: str) -> IntakeResult:
    if existing.get("submission_sha256") == submission_sha:
        if existing.get("intake_id") == intake_id:
            # The same S3 event delivered again: this event already lodged the claim.
            return IntakeResult(Outcome.ACCEPTED, source, claim_id, ("event replayed; claim already lodged",))
        return IntakeResult(Outcome.DUPLICATE, source, claim_id, ("identical claim already lodged",))
    return IntakeResult(
        Outcome.CONFLICT,
        source,
        claim_id,
        ("claim id already lodged with different content; original kept",),
    )


def _read_object(s3: Any, bucket: str, key: str) -> bytes | None:
    try:
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as err:
        if err.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


def _read_attachments(
    s3: Any, bucket: str, folder: str, attachments: list[dict]
) -> tuple[list[tuple[dict, bytes]], list[str]]:
    found: list[tuple[dict, bytes]] = []
    missing: list[str] = []
    for attachment in attachments:
        key = posixpath.join(folder, attachment["file"]) if folder else attachment["file"]
        body = _read_object(s3, bucket, key)
        if body is None:
            missing.append(attachment["file"])
        else:
            found.append((attachment, body))
    return found, missing


def _store_evidence(
    deps: IntakeDeps,
    claim_id: str,
    submission_sha: str,
    claim_file_name: str,
    claim_body: bytes,
    attachments: list[tuple[dict, bytes]],
) -> list[dict]:
    prefix = f"claims/{claim_id}/{submission_sha}"
    records = [
        _put_evidence(deps, f"{prefix}/{claim_file_name}", claim_body, "claim", claim_file_name, "application/json")
    ]
    for attachment, body in attachments:
        record = _put_evidence(deps, f"{prefix}/{attachment['file']}", body, "attachment", attachment["file"], None)
        record["attachment_type"] = attachment["type"]
        records.append(record)
    return records


def _put_evidence(
    deps: IntakeDeps, key: str, body: bytes, kind: str, name: str, content_type: str | None
) -> dict:
    extra = {"ContentType": content_type} if content_type else {}
    # Object Lock buckets require an integrity checksum on every upload.
    response = deps.s3.put_object(
        Bucket=deps.evidence_bucket, Key=key, Body=body, ChecksumAlgorithm="SHA256", **extra
    )
    return {
        "kind": kind,
        "name": name,
        "sha256": _sha256(body),
        "stored_at": f"s3://{deps.evidence_bucket}/{key}",
        "version_id": response.get("VersionId", ""),
    }


def _claim_item(
    doc: dict,
    policy: dict,
    source: str,
    intake_id: str,
    submission_sha: str,
    evidence: list[dict],
    now: datetime,
) -> dict:
    timestamp = now.isoformat()
    item = {
        "claim_id": doc["claim_id"],
        "status": CLAIM_STATUS_RECEIVED,
        "schema_version": ITEM_SCHEMA_VERSION,
        "policy_id": doc["policy_id"],
        "policyholder_id": doc["policyholder_id"],
        "product": policy.get("product", ""),
        "pds_id": policy.get("pds_id", ""),
        "event_type": doc["incident"]["event_type"],
        "incident_at": doc["incident"]["date_time"],
        "submitted_at": timestamp,
        "updated_at": timestamp,
        "submission_sha256": submission_sha,
        "source": source,
        "intake_id": intake_id,
        "evidence": evidence,
    }
    amount = doc.get("claimed_amount_aud")
    if amount is not None:
        item["claimed_amount_aud"] = Decimal(str(amount))
    return item


def _finish(deps: IntakeDeps, intake_id: str, result: IntakeResult) -> IntakeResult:
    entry = {
        "intake_id": intake_id,
        "outcome": result.outcome.value,
        "source": result.source,
        "reasons": list(result.reasons),
        "recorded_at": deps.now().isoformat(),
    }
    if result.claim_id:
        entry["claim_id"] = result.claim_id
    deps.intake_log.put_item(Item=entry)
    log(
        "intake." + result.outcome.value.lower(),
        claim_id=result.claim_id,
        source=result.source,
        reasons=list(result.reasons),
    )
    return result


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
