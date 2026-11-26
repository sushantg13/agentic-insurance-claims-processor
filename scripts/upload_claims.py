"""Upload claim folders to the inbox bucket, attachments first and the claim JSON last.

A claim folder holds one claim-*.json file and, optionally, a docs/ folder:

    home-burglary/
        claim-CLM-2026-000101.json
        docs/photo-1.txt

Pass one or more claim folders, or a parent folder that contains claim folders.
The claim JSON triggers intake, so it is uploaded only after every other file
in the folder. Files named expected.json are never uploaded: they are answer keys.

    python scripts/upload_claims.py --bucket "$(terraform -chdir=src/infra/tenants/sushant/dev output -raw inbox_bucket)" \
        clean-claims/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3

ANSWER_KEY_NAMES = {"expected.json"}


def find_claim_folders(paths: list[Path]) -> list[Path]:
    folders: list[Path] = []
    for path in paths:
        if not path.is_dir():
            raise SystemExit(f"Not a folder: {path}")
        if list(path.glob("claim-*.json")):
            folders.append(path)
        else:
            folders.extend(sorted(p for p in path.iterdir() if p.is_dir() and list(p.glob("claim-*.json"))))
    if not folders:
        raise SystemExit("No claim folders found (a claim folder contains a claim-*.json file).")
    return folders


def plan_uploads(folder: Path) -> list[tuple[Path, str]]:
    """Return (local file, S3 key) pairs in upload order: everything else first, claim JSON last."""
    claim_files = sorted(folder.glob("claim-*.json"))
    if len(claim_files) != 1:
        raise SystemExit(f"{folder} must contain exactly one claim-*.json file, found {len(claim_files)}")

    others = sorted(
        p for p in folder.rglob("*") if p.is_file() and p not in claim_files and p.name not in ANSWER_KEY_NAMES
    )
    skipped = [p for p in folder.rglob("*") if p.is_file() and p.name in ANSWER_KEY_NAMES]
    for p in skipped:
        print(f"  skipping answer key {p}")

    ordered = others + claim_files
    return [(p, f"{folder.name}/{p.relative_to(folder).as_posix()}") for p in ordered]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True, help="Inbox bucket name (terraform output inbox_bucket)")
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be uploaded without uploading")
    parser.add_argument("paths", nargs="+", type=Path, help="Claim folders, or folders that contain claim folders")
    args = parser.parse_args()

    s3 = None if args.dry_run else boto3.client("s3", region_name=args.region)
    for folder in find_claim_folders(args.paths):
        print(f"{folder.name}:")
        for local, key in plan_uploads(folder):
            print(f"  {local} -> s3://{args.bucket}/{key}")
            if s3:
                s3.upload_file(str(local), args.bucket, key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
