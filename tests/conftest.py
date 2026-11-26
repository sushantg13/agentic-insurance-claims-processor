import sys

# Keep src/app free of __pycache__ so the Terraform-built Lambda zip stays stable.
sys.dont_write_bytecode = True

import copy  # noqa: E402
import json  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402

from claims.intake import IntakeDeps, process_object  # noqa: E402

REGION = "ap-southeast-2"
INBOX = "test-inbox"
EVIDENCE = "test-evidence"
CLAIMS_TABLE = "test-claims"
POLICIES_TABLE = "test-policies"
INTAKE_LOG_TABLE = "test-intake-log"
FIXED_NOW = datetime(2026, 11, 26, 9, 0, tzinfo=timezone.utc)

BURGLARY_CLAIM = {
    "claim_id": "CLM-2026-000101",
    "policyholder_id": "MEM-445566",
    "policy_id": "POL-HOME-101540",
    "incident": {
        "event_type": "theft",
        "date_time": "2026-01-09T14:00:00+10:30",
        "location": "Insured home, Adelaide SA",
        "injuries": False,
        "emergency_services": True,
    },
    "reference_numbers": {"police_event_number": "SAPOL-2026-018842"},
    "claimed_amount_aud": 4300,
    "narrative": "We came home to find the rear door forced. A television and a laptop were taken.",
    "attachments": [
        {"type": "photo", "file": "docs/photo-1.txt", "summary": "Forced rear door lock and damaged frame."},
        {"type": "other", "file": "docs/other-1.txt", "summary": "Itemised list of stolen items."},
    ],
}

ATTACHMENTS = {
    "docs/photo-1.txt": b"[SUPPORTING DOCUMENT - photo]\nForced rear door lock and damaged frame.\n",
    "docs/other-1.txt": b"[SUPPORTING DOCUMENT - other]\nItemised list of stolen items.\n",
}


@pytest.fixture(autouse=True)
def fake_aws_credentials(monkeypatch):
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def aws():
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        location = {"LocationConstraint": REGION}
        s3.create_bucket(Bucket=INBOX, CreateBucketConfiguration=location)
        s3.create_bucket(Bucket=EVIDENCE, CreateBucketConfiguration=location, ObjectLockEnabledForBucket=True)
        s3.put_object_lock_configuration(
            Bucket=EVIDENCE,
            ObjectLockConfiguration={
                "ObjectLockEnabled": "Enabled",
                "Rule": {"DefaultRetention": {"Mode": "GOVERNANCE", "Days": 1}},
            },
        )

        dynamodb = boto3.resource("dynamodb", region_name=REGION)
        claims = dynamodb.create_table(
            TableName=CLAIMS_TABLE,
            KeySchema=[{"AttributeName": "claim_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "claim_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
            StreamSpecification={"StreamEnabled": True, "StreamViewType": "NEW_IMAGE"},
        )
        policies = dynamodb.create_table(
            TableName=POLICIES_TABLE,
            KeySchema=[{"AttributeName": "policy_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "policy_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        intake_log = dynamodb.create_table(
            TableName=INTAKE_LOG_TABLE,
            KeySchema=[{"AttributeName": "intake_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "intake_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        policies.put_item(
            Item={
                "policy_id": "POL-HOME-101540",
                "policyholder_id": "MEM-445566",
                "product": "home",
                "cover": "building_and_contents",
                "pds_id": "CLA-HOME-2024",
                "start_date": "2025-11-20",
                "expiry_date": "2026-11-20",
            }
        )

        deps = IntakeDeps(
            s3=s3,
            claims=claims,
            policies=policies,
            intake_log=intake_log,
            evidence_bucket=EVIDENCE,
            now=lambda: FIXED_NOW,
        )
        yield SimpleNamespace(s3=s3, deps=deps, claims=claims, policies=policies, intake_log=intake_log)


def make_claim(**overrides) -> dict:
    claim = copy.deepcopy(BURGLARY_CLAIM)
    claim.update(overrides)
    return claim


def upload_claim(s3, claim, folder="home-burglary", attachments=None, raw_body=None, claim_name=None) -> str:
    """Upload attachments, then the claim JSON, as the upload script does. Returns the claim key."""
    for name, body in (ATTACHMENTS if attachments is None else attachments).items():
        s3.put_object(Bucket=INBOX, Key=f"{folder}/{name}", Body=body)
    name = claim_name or f"claim-{claim['claim_id'] if isinstance(claim, dict) else 'X'}.json"
    key = f"{folder}/{name}" if folder else name
    body = raw_body if raw_body is not None else json.dumps(claim).encode()
    s3.put_object(Bucket=INBOX, Key=key, Body=body)
    return key


def run_intake(aws, key, sequencer="0001"):
    return process_object(INBOX, key, sequencer, aws.deps)


def log_entry(aws, key, sequencer="0001"):
    return aws.intake_log.get_item(Key={"intake_id": f"s3://{INBOX}/{key}#{sequencer}"}).get("Item")
