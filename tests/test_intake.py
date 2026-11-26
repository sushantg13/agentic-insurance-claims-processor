import json

from conftest import ATTACHMENTS, EVIDENCE, INBOX, make_claim, log_entry, run_intake, upload_claim

from claims.intake import Outcome


def test_valid_claim_is_lodged_with_evidence(aws):
    claim = make_claim()
    key = upload_claim(aws.s3, claim)

    result = run_intake(aws, key)

    assert result.outcome is Outcome.ACCEPTED
    item = aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"]
    assert item["status"] == "RECEIVED"
    assert item["product"] == "home"
    assert item["pds_id"] == "CLA-HOME-2024"
    assert item["claimed_amount_aud"] == 4300
    assert item["source"] == f"s3://{INBOX}/{key}"

    names = {record["name"]: record for record in item["evidence"]}
    assert set(names) == {"claim-CLM-2026-000101.json", "docs/photo-1.txt", "docs/other-1.txt"}
    for record in item["evidence"]:
        bucket, _, evidence_key = record["stored_at"].removeprefix("s3://").partition("/")
        assert bucket == EVIDENCE
        assert evidence_key.startswith(f"claims/CLM-2026-000101/{item['submission_sha256']}/")
        stored = aws.s3.get_object(Bucket=EVIDENCE, Key=evidence_key)
        assert stored["VersionId"] == record["version_id"]
    assert names["docs/photo-1.txt"]["attachment_type"] == "photo"

    assert log_entry(aws, key)["outcome"] == "ACCEPTED"


def test_evidence_objects_are_locked(aws):
    key = upload_claim(aws.s3, make_claim())
    run_intake(aws, key)

    item = aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"]
    evidence_key = item["evidence"][0]["stored_at"].removeprefix(f"s3://{EVIDENCE}/")
    head = aws.s3.head_object(Bucket=EVIDENCE, Key=evidence_key)
    assert head["ObjectLockMode"] == "GOVERNANCE"


def test_same_claim_uploaded_again_is_a_duplicate_and_changes_nothing(aws):
    claim = make_claim()
    first_key = upload_claim(aws.s3, claim)
    run_intake(aws, first_key)
    original = aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"]

    second_key = upload_claim(aws.s3, claim, folder="home-burglary-again")
    result = run_intake(aws, second_key, sequencer="0002")

    assert result.outcome is Outcome.DUPLICATE
    assert aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"] == original
    assert log_entry(aws, second_key, "0002")["outcome"] == "DUPLICATE"


def test_replayed_event_is_idempotent(aws):
    key = upload_claim(aws.s3, make_claim())
    run_intake(aws, key)
    original = aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"]

    result = run_intake(aws, key)

    assert result.outcome is Outcome.ACCEPTED
    assert aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"] == original
    assert log_entry(aws, key)["outcome"] == "ACCEPTED"


def test_same_id_with_different_content_is_a_conflict_and_keeps_the_original(aws):
    first_key = upload_claim(aws.s3, make_claim())
    run_intake(aws, first_key)
    original = aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"]

    altered = make_claim(claimed_amount_aud=43000)
    second_key = upload_claim(aws.s3, altered, folder="home-burglary-altered")
    result = run_intake(aws, second_key, sequencer="0002")

    assert result.outcome is Outcome.CONFLICT
    assert aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})["Item"] == original


def test_policy_of_another_policyholder_is_rejected(aws):
    key = upload_claim(aws.s3, make_claim(policyholder_id="MEM-999999"))

    result = run_intake(aws, key)

    assert result.outcome is Outcome.REJECTED
    assert result.reasons == ("policy does not belong to this policyholder",)
    assert "Item" not in aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})
    assert log_entry(aws, key)["reasons"] == ["policy does not belong to this policyholder"]


def test_unknown_policy_is_rejected(aws):
    key = upload_claim(aws.s3, make_claim(policy_id="POL-HOME-000000"))

    result = run_intake(aws, key)

    assert result.outcome is Outcome.REJECTED
    assert result.reasons == ("policy not found",)


def test_missing_attachment_is_rejected_and_nothing_is_stored(aws):
    key = upload_claim(aws.s3, make_claim(), attachments={"docs/photo-1.txt": ATTACHMENTS["docs/photo-1.txt"]})

    result = run_intake(aws, key)

    assert result.outcome is Outcome.REJECTED
    assert result.reasons == ("attachment not found: docs/other-1.txt",)
    assert "Item" not in aws.claims.get_item(Key={"claim_id": "CLM-2026-000101"})
    assert aws.s3.list_objects_v2(Bucket=EVIDENCE).get("KeyCount", 0) == 0


def test_invalid_json_is_rejected(aws):
    key = upload_claim(aws.s3, None, raw_body=b"{not json", claim_name="claim-broken.json", attachments={})

    result = run_intake(aws, key)

    assert result.outcome is Outcome.REJECTED
    assert result.reasons == ("claim file is not valid JSON",)


def test_badly_shaped_claim_is_rejected_with_reasons(aws):
    claim = make_claim()
    claim["incident"]["event_type"] = "volcano"
    key = upload_claim(aws.s3, claim)

    result = run_intake(aws, key)

    assert result.outcome is Outcome.REJECTED
    assert result.claim_id == "CLM-2026-000101"
    assert any("event_type" in reason for reason in result.reasons)


def test_attachment_path_outside_the_folder_is_rejected(aws):
    claim = make_claim()
    claim["attachments"][0]["file"] = "../other-claim/claim-CLM-2026-000999.json"
    key = upload_claim(aws.s3, claim)

    result = run_intake(aws, key)

    assert result.outcome is Outcome.REJECTED


def test_answer_key_and_other_files_are_ignored(aws):
    aws.s3.put_object(Bucket=INBOX, Key="home-burglary/expected.json", Body=json.dumps({"outcome": "approved"}))

    result = run_intake(aws, "home-burglary/expected.json")

    assert result.outcome is Outcome.IGNORED
    assert log_entry(aws, "home-burglary/expected.json") is None


def test_claim_file_deleted_before_intake_is_rejected(aws):
    result = run_intake(aws, "home-burglary/claim-CLM-2026-000101.json")

    assert result.outcome is Outcome.REJECTED
    assert result.reasons == ("claim file no longer exists",)
