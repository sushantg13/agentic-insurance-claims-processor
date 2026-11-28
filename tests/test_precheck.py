import json

import pytest
from conftest import CLAIMS_TABLE, POLICIES_TABLE, make_claim, run_intake, upload_claim

from precheck import handler as precheck_handler
from precheck.checks import Outcome, Result, run_checks
from precheck.process import PrecheckDeps, RunOutcome, precheck_claim

HOME_POLICY = {
    "policy_id": "POL-HOME-101540",
    "policyholder_id": "MEM-445566",
    "product": "home",
    "cover": "building_and_contents",
    "pds_id": "CLA-HOME-2024",
    "start_date": "2025-11-20",
    "expiry_date": "2026-11-20",
    "sum_insured_aud": 750000,
    "excess_aud": 500,
}


def policy(**overrides) -> dict:
    return {**HOME_POLICY, **overrides}


def claim_at(date_time: str, **overrides) -> dict:
    claim = make_claim(**overrides)
    claim["incident"]["date_time"] = date_time
    return claim


def results(pre) -> dict:
    return {c.name: c.result for c in pre.checks}


def flag_codes(pre) -> set:
    return {f.code for f in pre.flags}


# --- The checks on their own ---


def test_burglary_claim_is_eligible_with_no_flags():
    pre = run_checks(make_claim(), policy())

    assert pre.outcome is Outcome.ELIGIBLE
    assert pre.flags == []
    assert results(pre) == {
        "claim_well_formed": Result.PASS,
        "policy_found": Result.PASS,
        "policy_belongs_to_claimant": Result.PASS,
        "policy_record_valid": Result.PASS,
        "pds_applies": Result.PASS,
        "incident_in_term": Result.PASS,
        "event_fits_product": Result.PASS,
        "waiting_period": Result.DEFERRED,
    }


@pytest.mark.parametrize("event_type", ["storm", "flood", "earthquake"])
def test_environmental_events_always_route(event_type):
    claim = make_claim()
    claim["incident"]["event_type"] = event_type

    pre = run_checks(claim, policy())

    assert pre.outcome is Outcome.ELIGIBLE
    assert [(f.code, f.always_route) for f in pre.flags] == [("environmental_event", True)]


def test_claim_over_50000_always_routes_but_exactly_50000_does_not():
    assert "high_value" in flag_codes(run_checks(make_claim(claimed_amount_aud=50000.01), policy()))
    assert "high_value" not in flag_codes(run_checks(make_claim(claimed_amount_aud=50000), policy()))


def test_claim_above_sum_insured_is_flagged_not_failed():
    pre = run_checks(make_claim(claimed_amount_aud=80000), policy(sum_insured_aud=21500))

    assert pre.outcome is Outcome.ELIGIBLE
    assert flag_codes(pre) == {"high_value", "claimed_exceeds_sum_insured"}


def test_missing_amount_is_flagged_for_the_assessment_to_value():
    claim = make_claim()
    del claim["claimed_amount_aud"]

    assert flag_codes(run_checks(claim, policy())) == {"claim_value_unknown"}


@pytest.mark.parametrize("date_time", ["2025-11-19T23:30:00+10:30", "2026-11-21T09:00:00+10:30"])
def test_incident_outside_the_term_is_ineligible(date_time):
    pre = run_checks(claim_at(date_time), policy())

    assert pre.outcome is Outcome.INELIGIBLE
    assert results(pre)["incident_in_term"] is Result.FAIL


@pytest.mark.parametrize("date_time", ["2025-11-20T10:00:00+10:30", "2026-11-20T10:00:00+10:30"])
def test_incident_on_first_or_last_day_is_uncertain_and_flagged(date_time):
    pre = run_checks(claim_at(date_time), policy())

    assert pre.outcome is Outcome.ELIGIBLE
    assert results(pre)["incident_in_term"] is Result.UNCERTAIN
    assert "incident_on_term_boundary" in flag_codes(pre)


def test_term_uses_the_incidents_local_date_not_utc():
    # 01:00 on 21 Nov in Adelaide is still 20 Nov in UTC, the policy's first day.
    pre = run_checks(claim_at("2025-11-21T01:00:00+10:30"), policy())

    assert results(pre)["incident_in_term"] is Result.PASS


def test_collision_on_a_home_policy_is_flagged():
    claim = make_claim()
    claim["incident"]["event_type"] = "collision"

    pre = run_checks(claim, policy())

    assert pre.outcome is Outcome.ELIGIBLE
    assert "event_type_unusual_for_product" in flag_codes(pre)


def test_malformed_stored_claim_needs_review():
    pre = run_checks({"claim_id": "CLM-1"}, policy())

    assert pre.outcome is Outcome.NEEDS_REVIEW
    assert results(pre) == {"claim_well_formed": Result.FAIL}


def test_missing_policy_needs_review():
    pre = run_checks(make_claim(), None)

    assert pre.outcome is Outcome.NEEDS_REVIEW
    assert results(pre)["policy_found"] is Result.FAIL


def test_policy_held_by_someone_else_needs_review():
    pre = run_checks(make_claim(), policy(policyholder_id="MEM-999999"))

    assert pre.outcome is Outcome.NEEDS_REVIEW
    assert results(pre)["policy_belongs_to_claimant"] is Result.FAIL


@pytest.mark.parametrize(
    "overrides",
    [
        {"product": "boat"},
        {"start_date": "20/11/2025"},
        {"expiry_date": None},
        {"start_date": "2026-11-20", "expiry_date": "2025-11-20"},
        {"pds_id": ""},
        {"sum_insured_aud": "lots"},
    ],
)
def test_malformed_policy_record_needs_review(overrides):
    pre = run_checks(make_claim(), policy(**overrides))

    assert pre.outcome is Outcome.NEEDS_REVIEW
    assert results(pre)["policy_record_valid"] is Result.FAIL


@pytest.mark.parametrize(
    "overrides",
    [
        {"pds_id": "CLA-HOME-1999"},
        {"pds_id": "CLA-MOTOR-2026"},
        {"product": "motor", "pds_id": "CLA-MOTOR-2024", "start_date": "2026-02-01", "expiry_date": "2027-02-01"},
        {"product": "motor", "pds_id": "CLA-MOTOR-2026", "start_date": "2025-09-01", "expiry_date": "2026-09-01"},
    ],
    ids=["unknown", "wrong-product", "superseded", "not-yet-effective"],
)
def test_pds_that_does_not_apply_needs_review(overrides):
    pre = run_checks(make_claim(), policy(**overrides))

    assert pre.outcome is Outcome.NEEDS_REVIEW
    assert results(pre)["pds_applies"] is Result.FAIL


# --- Against the stored claim, after intake ---


@pytest.fixture
def lodged(aws):
    run_intake(aws, upload_claim(aws.s3, make_claim()))
    return aws


def deps(aws):
    return PrecheckDeps(s3=aws.s3, claims=aws.claims, policies=aws.policies, now=aws.deps.now)


def stored(aws, claim_id="CLM-2026-000101"):
    return aws.claims.get_item(Key={"claim_id": claim_id})["Item"]


def test_lodged_claim_becomes_prechecked_with_its_record(lodged):
    assert precheck_claim("CLM-2026-000101", deps(lodged)) is RunOutcome.DONE

    item = stored(lodged)
    assert item["status"] == "PRECHECKED"
    assert item["precheck"]["outcome"] == "ELIGIBLE"
    assert item["precheck"]["checks"][0]["name"] == "evidence_intact"
    assert item["precheck"]["checks"][0]["result"] == "PASS"
    assert item["precheck"]["policy_as_seen"]["pds_id"] == "CLA-HOME-2024"


def test_precheck_runs_once_per_claim(lodged):
    precheck_claim("CLM-2026-000101", deps(lodged))
    first = stored(lodged)

    assert precheck_claim("CLM-2026-000101", deps(lodged)) is RunOutcome.ALREADY_DONE
    assert stored(lodged) == first


def test_hash_mismatch_with_evidence_needs_review(lodged):
    lodged.claims.update_item(
        Key={"claim_id": "CLM-2026-000101"},
        UpdateExpression="SET submission_sha256 = :sha",
        ExpressionAttributeValues={":sha": "0" * 64},
    )

    precheck_claim("CLM-2026-000101", deps(lodged))

    item = stored(lodged)
    assert item["status"] == "NEEDS_REVIEW"
    assert item["precheck"]["checks"] == [
        {"name": "evidence_intact", "result": "FAIL", "detail": "evidence copy does not match the hash recorded at intake"}
    ]


def test_policy_removed_after_intake_needs_review(lodged):
    lodged.policies.delete_item(Key={"policy_id": "POL-HOME-101540"})

    precheck_claim("CLM-2026-000101", deps(lodged))

    assert stored(lodged)["status"] == "NEEDS_REVIEW"


def test_unknown_claim_is_not_created(aws):
    assert precheck_claim("CLM-0000-000000", deps(aws)) is RunOutcome.NOT_FOUND
    assert "Item" not in aws.claims.get_item(Key={"claim_id": "CLM-0000-000000"})


def test_handler_reports_only_failed_messages(lodged, monkeypatch):
    monkeypatch.setenv("CLAIMS_TABLE", CLAIMS_TABLE)
    monkeypatch.setenv("POLICIES_TABLE", POLICIES_TABLE)
    monkeypatch.setattr(precheck_handler, "_deps", None)
    event = {
        "Records": [
            {"messageId": "good", "body": json.dumps({"claim_id": "CLM-2026-000101"})},
            {"messageId": "bad", "body": "not json"},
        ]
    }

    assert precheck_handler.handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    assert stored(lodged)["status"] == "PRECHECKED"
