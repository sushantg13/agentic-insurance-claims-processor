import json
from urllib.parse import quote_plus

import pytest
from conftest import CLAIMS_TABLE, EVIDENCE, INBOX, INTAKE_LOG_TABLE, POLICIES_TABLE, make_claim, upload_claim

from intake import handler as intake_handler
from worker import handler as worker_handler
from worker.assessment import StartOutcome, start_assessment


@pytest.fixture
def lambda_env(monkeypatch, aws):
    monkeypatch.setenv("EVIDENCE_BUCKET", EVIDENCE)
    monkeypatch.setenv("CLAIMS_TABLE", CLAIMS_TABLE)
    monkeypatch.setenv("POLICIES_TABLE", POLICIES_TABLE)
    monkeypatch.setenv("INTAKE_LOG_TABLE", INTAKE_LOG_TABLE)
    monkeypatch.setattr(intake_handler, "_deps", None)
    monkeypatch.setattr(worker_handler, "_claims_table", None)
    return aws


def s3_event(key, sequencer="0001"):
    return {
        "Records": [
            {"s3": {"bucket": {"name": INBOX}, "object": {"key": quote_plus(key), "sequencer": sequencer}}}
        ]
    }


def test_intake_handler_decodes_url_encoded_keys(lambda_env):
    key = upload_claim(lambda_env.s3, make_claim(), folder="home burglary")

    response = intake_handler.handler(s3_event(key), None)

    assert response["results"][0]["outcome"] == "ACCEPTED"
    item = lambda_env.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"]
    assert item["source"] == f"s3://{INBOX}/home burglary/claim-CLM-2026-000101.json"


def put_received_claim(aws, claim_id="CLM-2026-000101"):
    aws.claims.put_item(Item={"claim_id": claim_id, "status": "RECEIVED"})


def test_start_assessment_moves_a_received_claim_to_assessing(aws):
    put_received_claim(aws)

    assert start_assessment("CLM-2026-000101", aws.claims) is StartOutcome.STARTED
    assert aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"]["status"] == "ASSESSING"


def test_redelivered_message_does_not_restart_assessment(aws):
    put_received_claim(aws)
    start_assessment("CLM-2026-000101", aws.claims)
    started = aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"]

    assert start_assessment("CLM-2026-000101", aws.claims) is StartOutcome.ALREADY_STARTED
    assert aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"] == started


def test_message_for_unknown_claim_is_dropped_without_creating_it(aws):
    assert start_assessment("CLM-0000-000000", aws.claims) is StartOutcome.NOT_FOUND
    assert "Item" not in aws.claims.get_item(Key={"claim_id": "CLM-0000-000000"})


def test_worker_reports_only_failed_messages(lambda_env):
    put_received_claim(lambda_env)
    event = {
        "Records": [
            {"messageId": "good", "body": json.dumps({"claim_id": "CLM-2026-000101"})},
            {"messageId": "bad", "body": "not json"},
        ]
    }

    response = worker_handler.handler(event, None)

    assert response == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    assert lambda_env.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"]["status"] == "ASSESSING"
