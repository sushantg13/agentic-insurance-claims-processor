import logging
import re
import time

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

textract = boto3.client("textract")

POLL_SECONDS = 2
POLICY_NUMBER_RE = re.compile(
    r"policy\s*(?:number|no\.?)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-]*)",
    re.IGNORECASE,
)


def extract_text_from_s3(bucket, key):
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


def extract_policy_number(claim_text):
    """Return the policy number from the claim text, e.g. 'Policy Number: POL-123456'."""
    match = POLICY_NUMBER_RE.search(claim_text)
    if not match:
        logger.warning("Policy number not found in claim text")
        return None
    logger.info("Policy number found: %s", match.group(1))
    return match.group(1)


def handler(event, context):
    print(f"Ingestion event: {event}")
    logger.info("Ingestion event: %s", event)

    job_id = event["job_id"]
    bucket = event["s3"]["bucket"]
    claim_key = event["s3"]["key"]

    # Step 1 - extract text from the claim PDF
    logger.info("Step 1: Extracting claim text from s3://%s/%s", bucket, claim_key)
    claim_text = extract_text_from_s3(bucket, claim_key)

    # Step 2 - derive the policy document key from the policy number in the claim
    policy_number = extract_policy_number(claim_text)
    if not policy_number:
        raise ValueError(f"Could not determine policy number from claim: {claim_key}")

    # The policy document sits in the same folder as the claim: <prefix>/<policy_number>.pdf
    prefix = claim_key.rsplit("/", 1)[0] if "/" in claim_key else ""
    policy_key = f"{prefix}/{policy_number}.pdf" if prefix else f"{policy_number}.pdf"

    # Step 3 - extract text from the policy PDF
    logger.info("Step 2: Extracting policy text from s3://%s/%s", bucket, policy_key)
    policy_text = extract_text_from_s3(bucket, policy_key)

    output = {
        "job_id": job_id,
        "policy_number": policy_number,
        "claim_text": claim_text,
        "policy_text": policy_text,
    }
    logger.info(
        "Ingestion complete. job_id=%s policy_number=%s claim_chars=%d policy_chars=%d",
        job_id,
        policy_number,
        len(claim_text),
        len(policy_text),
    )
    return output
