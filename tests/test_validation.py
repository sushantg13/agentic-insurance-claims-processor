from conftest import make_claim

from intake.validation import is_safe_relative_path, validate_claim


def test_sample_claim_is_well_formed():
    assert validate_claim(make_claim()) == []


def test_claim_amount_is_optional():
    claim = make_claim()
    del claim["claimed_amount_aud"]
    assert validate_claim(claim) == []


def test_unknown_event_type_is_rejected():
    claim = make_claim()
    claim["incident"]["event_type"] = "volcano"
    assert any("event_type" in e for e in validate_claim(claim))


def test_timestamp_without_offset_is_rejected():
    claim = make_claim()
    claim["incident"]["date_time"] = "2026-01-09T14:00:00"
    assert any("UTC offset" in e for e in validate_claim(claim))


def test_negative_or_boolean_amount_is_rejected():
    assert validate_claim(make_claim(claimed_amount_aud=-1))
    assert validate_claim(make_claim(claimed_amount_aud=True))


def test_unsafe_identifier_is_rejected():
    assert any("claim_id" in e for e in validate_claim(make_claim(claim_id="../CLM-1")))


def test_empty_narrative_is_rejected():
    assert any("narrative" in e for e in validate_claim(make_claim(narrative="   ")))


def test_non_object_payload_is_rejected():
    assert validate_claim(["not", "a", "claim"]) == ["claim must be a JSON object"]


def test_attachment_paths_cannot_escape_the_claim_folder():
    for bad in ["../other-claim/claim.json", "/etc/passwd", "docs/../../x", "docs//x", "docs\\x", "./docs/x", ""]:
        assert not is_safe_relative_path(bad), bad
    assert is_safe_relative_path("docs/photo-1.txt")
