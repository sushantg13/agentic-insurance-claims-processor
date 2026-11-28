"""Stage 0: the yes/no checks that need no model.

Input is the claim as stored in the evidence bucket and the policy as held in
the policies table. Neither is assumed to be well formed. Every check is
recorded with its result, so the audit record shows what was checked, not
only what failed.

Outcomes:
- ELIGIBLE: the claim goes on to the assessment, with any flags attached.
- INELIGIBLE: the incident falls outside the policy term. The assessment stops.
- NEEDS_REVIEW: the data itself is wrong (evidence altered, policy missing or
  malformed, unknown PDS). A person must look before anything else runs.

Flags never stop a claim. Those marked always_route send it to an assessor at
the end, whatever the assessment's confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from precheck.pds_catalog import CATALOG
from shared.validation import validate_claim

HIGH_VALUE_THRESHOLD_AUD = Decimal(50_000)
ENVIRONMENTAL_EVENTS = frozenset({"storm", "flood", "earthquake"})
PRODUCTS = frozenset({"home", "motor"})
# Event types a claimant can pick that only make sense for one product.
EVENTS_ONLY_FOR = {"collision": "motor"}


class Outcome(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Result(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNCERTAIN = "UNCERTAIN"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True)
class Check:
    name: str
    result: Result
    detail: str


@dataclass(frozen=True)
class Flag:
    code: str
    detail: str
    always_route: bool


@dataclass
class Precheck:
    outcome: Outcome
    checks: list[Check] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)

    def to_item(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "checks": [{"name": c.name, "result": c.result.value, "detail": c.detail} for c in self.checks],
            "flags": [{"code": f.code, "detail": f.detail, "always_route": f.always_route} for f in self.flags],
        }


def run_checks(claim: Any, policy: dict | None) -> Precheck:
    """Run every check that applies. Data problems stop early; everything else is recorded."""
    pre = Precheck(Outcome.ELIGIBLE)

    errors = validate_claim(claim)
    if errors:
        return _review(pre, "claim_well_formed", "; ".join(errors))
    pre.checks.append(Check("claim_well_formed", Result.PASS, "stored claim passes the shape checks"))

    if policy is None:
        return _review(pre, "policy_found", f"{claim['policy_id']} is not in the policies table")
    pre.checks.append(Check("policy_found", Result.PASS, claim["policy_id"]))

    if policy.get("policyholder_id") != claim["policyholder_id"]:
        return _review(pre, "policy_belongs_to_claimant", "policy is held by a different policyholder")
    pre.checks.append(Check("policy_belongs_to_claimant", Result.PASS, claim["policyholder_id"]))

    start, expiry, problems = _policy_record(policy)
    if problems:
        return _review(pre, "policy_record_valid", "; ".join(problems))
    pre.checks.append(Check("policy_record_valid", Result.PASS, f"{policy['product']} policy, {start} to {expiry}"))

    pds_problem = _pds_problem(policy, start)
    if pds_problem:
        return _review(pre, "pds_applies", pds_problem)
    pre.checks.append(Check("pds_applies", Result.PASS, f"{policy['pds_id']} was current when the policy started"))

    _check_term(pre, claim, start, expiry)
    _check_event_fits_product(pre, claim, policy["product"])
    pre.checks.append(
        Check(
            "waiting_period",
            Result.DEFERRED,
            "set per Insured Event, so it is checked once the assessment identifies the cover",
        )
    )
    _add_flags(pre, claim, policy)
    return pre


def _review(pre: Precheck, name: str, detail: str) -> Precheck:
    pre.outcome = Outcome.NEEDS_REVIEW
    pre.checks.append(Check(name, Result.FAIL, detail))
    return pre


def _policy_record(policy: dict) -> tuple[date | None, date | None, list[str]]:
    problems = []
    if policy.get("product") not in PRODUCTS:
        problems.append(f"product must be one of {sorted(PRODUCTS)}")
    if not isinstance(policy.get("pds_id"), str) or not policy["pds_id"]:
        problems.append("pds_id is missing")
    start = _parse_date(policy.get("start_date"))
    expiry = _parse_date(policy.get("expiry_date"))
    if start is None:
        problems.append("start_date must be a YYYY-MM-DD date")
    if expiry is None:
        problems.append("expiry_date must be a YYYY-MM-DD date")
    if start and expiry and start >= expiry:
        problems.append("start_date must be before expiry_date")
    sum_insured = policy.get("sum_insured_aud")
    if sum_insured is not None and (isinstance(sum_insured, bool) or not isinstance(sum_insured, (int, float, Decimal))):
        problems.append("sum_insured_aud must be a number")
    return start, expiry, problems


def _pds_problem(policy: dict, start: date) -> str | None:
    pds = CATALOG.get(policy["pds_id"])
    if pds is None:
        return f"{policy['pds_id']} is not a known PDS"
    if pds.product != policy["product"]:
        return f"{pds.pds_id} is a {pds.product} PDS but the policy is {policy['product']}"
    if not pds.current_on(start):
        return f"{pds.pds_id} was not current on the policy start date {start}"
    return None


def _check_term(pre: Precheck, claim: dict, start: date, expiry: date) -> None:
    # The register holds dates without a time of day, so compare the incident's
    # own local date. On the first or last day the answer depends on the hour
    # cover starts and ends, which the register does not say.
    incident_day = datetime.fromisoformat(claim["incident"]["date_time"]).date()
    if start < incident_day < expiry:
        pre.checks.append(Check("incident_in_term", Result.PASS, f"{incident_day} is within {start} to {expiry}"))
    elif incident_day in (start, expiry):
        detail = f"{incident_day} is the policy's {'first' if incident_day == start else 'last'} day"
        pre.checks.append(Check("incident_in_term", Result.UNCERTAIN, detail))
        pre.flags.append(Flag("incident_on_term_boundary", detail, always_route=False))
    else:
        pre.outcome = Outcome.INELIGIBLE
        pre.checks.append(Check("incident_in_term", Result.FAIL, f"{incident_day} is outside {start} to {expiry}"))


def _check_event_fits_product(pre: Precheck, claim: dict, product: str) -> None:
    event_type = claim["incident"]["event_type"]
    only_for = EVENTS_ONLY_FOR.get(event_type)
    if only_for and only_for != product:
        detail = f"event type '{event_type}' is unusual for a {product} policy"
        pre.checks.append(Check("event_fits_product", Result.UNCERTAIN, detail))
        pre.flags.append(Flag("event_type_unusual_for_product", detail, always_route=False))
    else:
        pre.checks.append(Check("event_fits_product", Result.PASS, f"'{event_type}' on a {product} policy"))


def _add_flags(pre: Precheck, claim: dict, policy: dict) -> None:
    event_type = claim["incident"]["event_type"]
    if event_type in ENVIRONMENTAL_EVENTS:
        pre.flags.append(
            Flag("environmental_event", f"claimant reports a {event_type}; always routed", always_route=True)
        )

    amount = claim.get("claimed_amount_aud")
    if amount is None:
        pre.flags.append(
            Flag(
                "claim_value_unknown",
                "no claimed amount; the assessment must establish the value before routing",
                always_route=False,
            )
        )
        return
    amount = Decimal(str(amount))
    if amount > HIGH_VALUE_THRESHOLD_AUD:
        pre.flags.append(
            Flag("high_value", f"claimed ${amount} is over ${HIGH_VALUE_THRESHOLD_AUD}; always routed", always_route=True)
        )
    sum_insured = policy.get("sum_insured_aud")
    if sum_insured is not None and amount > Decimal(str(sum_insured)):
        pre.flags.append(
            Flag(
                "claimed_exceeds_sum_insured",
                f"claimed ${amount} is over the sum insured ${sum_insured}; any payout is capped later",
                always_route=False,
            )
        )


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
