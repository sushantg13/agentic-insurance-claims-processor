import json
import os

from main import handler

event = {
    "job_id": "job-001",
    "s3": {
        "bucket": os.environ.get("BUCKET_NAME", "<project>-<env>-<account-id>"),
        "key": "sushant/claim.pdf",
    },
}

if __name__ == "__main__":
    print(json.dumps(handler(event, None), indent=2))
