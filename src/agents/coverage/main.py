import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Nova Lite is called in us-east-1 regardless of where the Lambda runs
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = "amazon.nova-lite-v1:0"

SYSTEM_PROMPT = (
    "You are an insurance underwriter. Apply the underwriting rules in the policy "
    "text to the claim text and decide whether the claim is covered. "
    "Reply with 'DECISION: YES' or 'DECISION: NO' on the first line, "
    "then a short summary of the coverage and the reasons."
)


def handler(event, context):
    print(f"Coverage event: {event}")
    logger.info("Coverage event: %s", event)

    prompt = (
        f"POLICY TEXT:\n{event['policy_text']}\n\n"
        f"CLAIM TEXT:\n{event['extracted_text']}"
    )

    response = bedrock.converse(
        modelId=MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 1024, "temperature": 0},
    )
    answer = response["output"]["message"]["content"][0]["text"].strip()
    logger.info("Bedrock answer: %s", answer)

    first_line, _, summary = answer.partition("\n")
    covered = "YES" in first_line.upper()

    return {
        "contract_id": event["contract_id"],
        "s3": event["s3"],
        "s3_uri": event["s3_uri"],
        "covered": covered,
        "summary": summary.strip() or answer,
    }
