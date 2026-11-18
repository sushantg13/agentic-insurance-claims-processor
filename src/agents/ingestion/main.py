import logging
import time

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract = boto3.client("textract")

POLL_SECONDS = 2


def extract_text(bucket, key):
    """Run async Textract text detection on an S3 object and return its text."""
    job_id = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
    )["JobId"]
    logger.info("Textract job %s started for s3://%s/%s", job_id, bucket, key)

    while True:
        status = textract.get_document_text_detection(JobId=job_id)["JobStatus"]
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "PARTIAL_SUCCESS"):
            raise RuntimeError(f"Textract job {job_id} ended with status {status}")
        time.sleep(POLL_SECONDS)

    lines = []
    kwargs = {"JobId": job_id}
    while True:
        resp = textract.get_document_text_detection(**kwargs)
        lines += [b["Text"] for b in resp["Blocks"] if b["BlockType"] == "LINE"]
        if "NextToken" not in resp:
            break
        kwargs["NextToken"] = resp["NextToken"]

    return "\n".join(lines)


def handler(event, context):
    print(f"Ingestion event: {event}")
    logger.info("Ingestion event: %s", event)

    contract_id = event["contract_id"]
    bucket = event["s3"]["bucket"]
    key = event["s3"]["key"]

    # The policy document already exists next to the claim: <cust>/policy.pdf
    cust = key.split("/")[0]
    policy_key = event["s3"].get("policy_key", f"{cust}/policy.pdf")

    claims_text = extract_text(bucket, key)
    policy_text = extract_text(bucket, policy_key)
    logger.info(
        "Extracted %d chars from claim and %d chars from policy",
        len(claims_text),
        len(policy_text),
    )

    return {
        "contract_id": contract_id,
        "s3": {"bucket": bucket, "key": key},
        "s3_uri": f"s3://{bucket}/{key}",
        "extracted_text": claims_text,
        "policy_text": policy_text,
    }
