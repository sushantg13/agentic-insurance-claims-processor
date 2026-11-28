"""Shape checks for a claim submission.

Intake runs them before anything is stored; precheck runs them again on the
stored evidence copy rather than trusting intake. They check that the payload
is well formed and safe to store. They do not judge the claim: dates against
the policy term and routing rules belong to the precheck.
"""

from __future__ import annotations

import posixpath
import re
from datetime import datetime
from typing import Any

EVENT_TYPES = frozenset(
    {
        "collision",
        "theft",
        "storm",
        "fire",
        "flood",
        "water_damage",
        "accidental_damage",
        "liability",
        "glass_only",
        "earthquake",
    }
)

# Identifiers become S3 key segments and DynamoDB keys, so keep them to a safe alphabet.
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

MAX_NARRATIVE_CHARS = 20_000
MAX_ATTACHMENTS = 20


def validate_claim(doc: Any) -> list[str]:
    """Return a list of problems. An empty list means the claim is well formed."""
    if not isinstance(doc, dict):
        return ["claim must be a JSON object"]

    errors: list[str] = []

    for field in ("claim_id", "policyholder_id", "policy_id"):
        value = doc.get(field)
        if not isinstance(value, str) or not ID_PATTERN.match(value):
            errors.append(f"{field} must be 1-64 letters, digits, '-' or '_'")

    errors.extend(_validate_incident(doc.get("incident")))

    refs = doc.get("reference_numbers", {})
    if not isinstance(refs, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in refs.items()
    ):
        errors.append("reference_numbers must be an object of text values")

    if "claimed_amount_aud" in doc and doc["claimed_amount_aud"] is not None:
        amount = doc["claimed_amount_aud"]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            errors.append("claimed_amount_aud must be a number of zero or more")

    narrative = doc.get("narrative")
    if not isinstance(narrative, str) or not narrative.strip():
        errors.append("narrative must be non-empty text")
    elif len(narrative) > MAX_NARRATIVE_CHARS:
        errors.append(f"narrative must be at most {MAX_NARRATIVE_CHARS} characters")

    errors.extend(_validate_attachments(doc.get("attachments", [])))
    return errors


def _validate_incident(incident: Any) -> list[str]:
    if not isinstance(incident, dict):
        return ["incident must be an object"]

    errors: list[str] = []
    if incident.get("event_type") not in EVENT_TYPES:
        errors.append(f"incident.event_type must be one of {sorted(EVENT_TYPES)}")

    when = incident.get("date_time")
    if not isinstance(when, str):
        errors.append("incident.date_time must be an ISO 8601 timestamp")
    else:
        try:
            parsed = datetime.fromisoformat(when)
        except ValueError:
            errors.append("incident.date_time must be an ISO 8601 timestamp")
        else:
            if parsed.tzinfo is None:
                errors.append("incident.date_time must include a UTC offset")

    location = incident.get("location")
    if not isinstance(location, str) or not location.strip():
        errors.append("incident.location must be non-empty text")

    for flag in ("injuries", "emergency_services"):
        if not isinstance(incident.get(flag), bool):
            errors.append(f"incident.{flag} must be true or false")
    return errors


def _validate_attachments(attachments: Any) -> list[str]:
    if not isinstance(attachments, list):
        return ["attachments must be a list"]
    if len(attachments) > MAX_ATTACHMENTS:
        return [f"at most {MAX_ATTACHMENTS} attachments are allowed"]

    errors: list[str] = []
    seen: set[str] = set()
    for i, attachment in enumerate(attachments):
        if not isinstance(attachment, dict):
            errors.append(f"attachments[{i}] must be an object")
            continue
        for field in ("type", "summary"):
            if not isinstance(attachment.get(field), str):
                errors.append(f"attachments[{i}].{field} must be text")
        file = attachment.get("file")
        if not is_safe_relative_path(file):
            errors.append(f"attachments[{i}].file must be a relative path inside the claim folder")
        elif file in seen:
            errors.append(f"attachments[{i}].file is listed twice")
        else:
            seen.add(file)
    return errors


def is_safe_relative_path(path: Any) -> bool:
    """True for paths like 'docs/photo-1.txt'; false for anything that could escape the folder."""
    if not isinstance(path, str) or not path or "\\" in path:
        return False
    if path.startswith("/") or posixpath.normpath(path) != path:
        return False
    return not any(part in ("", ".", "..") for part in path.split("/"))
