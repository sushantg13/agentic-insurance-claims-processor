import json

from seed_policies import load_register
from upload_claims import find_claim_folders, plan_uploads


def make_folder(tmp_path, name="home-burglary"):
    folder = tmp_path / name
    (folder / "docs").mkdir(parents=True)
    (folder / "claim-CLM-2026-000101.json").write_text("{}")
    (folder / "docs" / "photo-1.txt").write_text("photo")
    (folder / "docs" / "other-1.txt").write_text("list")
    (folder / "expected.json").write_text('{"outcome": "approved"}')
    return folder


def test_upload_plan_puts_attachments_first_claim_last_and_skips_answer_key(tmp_path):
    folder = make_folder(tmp_path)

    keys = [key for _, key in plan_uploads(folder)]

    assert keys == [
        "home-burglary/docs/other-1.txt",
        "home-burglary/docs/photo-1.txt",
        "home-burglary/claim-CLM-2026-000101.json",
    ]


def test_parent_folder_expands_to_its_claim_folders(tmp_path):
    make_folder(tmp_path, "b-claim")
    make_folder(tmp_path, "a-claim")
    (tmp_path / "not-a-claim").mkdir()

    folders = find_claim_folders([tmp_path])

    assert [f.name for f in folders] == ["a-claim", "b-claim"]


def test_register_policies_carry_holder_details(tmp_path):
    register = tmp_path / "register.json"
    register.write_text(
        json.dumps(
            {
                "register_version": "REG-TEST",
                "policyholders": [{"policyholder_id": "MEM-1", "name": "S. Williams", "email": "s@example.com"}],
                "policies": [{"policy_id": "POL-1", "policyholder_id": "MEM-1", "sum_insured_aud": 750000.5}],
            }
        )
    )

    [item] = load_register(register)

    assert item["holder_name"] == "S. Williams"
    assert item["register_version"] == "REG-TEST"
    assert str(item["sum_insured_aud"]) == "750000.5"
