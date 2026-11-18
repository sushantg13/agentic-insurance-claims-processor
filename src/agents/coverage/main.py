import json
import logging
import re
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Nova Lite is called in us-east-1 regardless of where the Lambda runs
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
BEDROCK_MODEL_ID = "amazon.nova-lite-v1:0"

VALID_DECISIONS = ("APPROVED", "REJECTED")


def build_prompt(claim_text, policy_text):
    """Build the underwriting prompt for the model."""
    today = datetime.now(timezone.utc).strftime("%d-%b-%Y")
    return (
        "You are an insurance underwriter. Evaluate the claim against the policy.\n"
        f"Today's date is {today}.\n\n"
        "Instructions:\n"
        "- Check that the treatment is covered under the policy.\n"
        "- Check date validity: the admission and discharge dates in the claim must "
        "fall within the policy period, and any waiting period must be satisfied.\n"
        "- Check for any exclusions that may apply.\n"
        "- Provide an underwriting decision: APPROVED or REJECTED.\n"
        "- Provide a short plain-English reason (3-5 sentences) covering:\n"
        "  * Coverage match\n"
        "  * Date validity\n"
        "  * Any exclusions triggered\n"
        "  * Recommended reimbursable amount if approved, or the reason for rejection\n\n"
        "Respond in this exact JSON format (no markdown, no extra keys):\n"
        '{"decision": "APPROVED" | "REJECTED", "reason": "<plain-English reason>"}\n\n'
        "---\n"
        f"POLICY DOCUMENT:\n{policy_text}\n\n"
        "---\n"
        f"CLAIM DOCUMENT:\n{claim_text}\n"
    )


def parse_decision(raw_text):
    """Parse the model's JSON reply, tolerating markdown fences and extra text."""
    text = re.sub(r"```(?:json)?", "", raw_text).strip()
    start, end = text.find("{"), text.rfind("}")
    try:
        result = json.loads(text[start : end + 1])
        decision = str(result.get("decision", "")).strip().upper()
        reason = str(result.get("reason", "")).strip()
    except (ValueError, AttributeError):
        logger.warning("Could not parse model output as JSON")
        return {"decision": "UNKNOWN", "reason": raw_text.strip()}

    if decision not in VALID_DECISIONS:
        decision = "UNKNOWN"
    return {"decision": decision, "reason": reason}


def invoke_bedrock(prompt):
    """Call Amazon Nova through the Bedrock Converse API and return the parsed decision."""
    print(f"Invoking Bedrock model: {BEDROCK_MODEL_ID}")
    logger.info("Invoking Bedrock model: %s", BEDROCK_MODEL_ID)

    response = bedrock.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 512, "temperature": 0.1},
    )
    raw_text = response["output"]["message"]["content"][0]["text"]
    print(f"Bedrock output text: {raw_text}")
    logger.info("Bedrock output text: %s", raw_text)

    return parse_decision(raw_text)


def handler(event, context):
    print(f"Coverage Lambda invoked. Event keys: {list(event.keys())}")
    logger.info(
        "Coverage Lambda event: %s",
        json.dumps(
            {
                k: v if k not in ("claim_text", "policy_text") else f"<{len(v)} chars>"
                for k, v in event.items()
            }
        ),
    )

    job_id = event.get("job_id")
    policy_number = event.get("policy_number")
    claim_text = event["claim_text"]
    policy_text = event["policy_text"]

    prompt = build_prompt(claim_text, policy_text)
    result = invoke_bedrock(prompt)

    output = {
        "job_id": job_id,
        "policy_number": policy_number,
        "decision": result["decision"],
        "reason": result["reason"],
    }
    print(f"Coverage decision: {output['decision']}")
    logger.info(
        "Coverage complete. job_id=%s policy_number=%s decision=%s",
        job_id,
        policy_number,
        output["decision"],
    )
    return output
