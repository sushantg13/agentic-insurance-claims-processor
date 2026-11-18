import json
import os

from main import handler

event = {
    "contract_id": "abc-123",
    "s3": {
        "bucket": os.environ.get("BUCKET_NAME", "<project>-<env>-<account-id>"),
        "key": "sushant/claims.pdf",
    },
}

if __name__ == "__main__":
    print(json.dumps(handler(event, None), indent=2))
