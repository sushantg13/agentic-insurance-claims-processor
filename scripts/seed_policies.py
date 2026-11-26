"""Load a policy register file into the policies table.

The register has two lists, policyholders and policies. Each policy is written
as one item keyed by policy_id, with the holder's name and email copied in.
Re-running the script overwrites items with the same policy_id, so it is safe
to run again after the register changes.

    python scripts/seed_policies.py --register path/to/policy-register.json \
        --table "$(terraform -chdir=src/infra/tenants/sushant/dev output -raw policies_table)"
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

import boto3


def load_register(path: Path) -> list[dict]:
    register = json.loads(path.read_text(), parse_float=Decimal)
    holders = {h["policyholder_id"]: h for h in register.get("policyholders", [])}
    items = []
    for policy in register.get("policies", []):
        item = dict(policy)
        holder = holders.get(policy["policyholder_id"])
        if holder:
            item["holder_name"] = holder.get("name", "")
            item["holder_email"] = holder.get("email", "")
        if "register_version" in register:
            item["register_version"] = register["register_version"]
        items.append(item)
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--register", required=True, type=Path, help="Path to the policy register JSON file")
    parser.add_argument("--table", required=True, help="Policies table name (terraform output policies_table)")
    parser.add_argument("--region", default="ap-southeast-2")
    args = parser.parse_args()

    items = load_register(args.register)
    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    with table.batch_writer(overwrite_by_pkeys=["policy_id"]) as batch:
        for item in items:
            batch.put_item(Item=item)
    print(f"Wrote {len(items)} policies to {args.table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
