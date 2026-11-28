"""The PDS documents the precheck knows about, and when each one applies.

A policy is assessed against the PDS that was current when it started or was
last renewed (CLA-MOTOR-2026, front page). This table lets code confirm the
register's pds_id is real, matches the product, and was current at the
policy's start date. It moves to the PDS knowledge store once that exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PdsVersion:
    pds_id: str
    product: str
    effective_from: date
    superseded_on: date | None = None

    def current_on(self, day: date) -> bool:
        return self.effective_from <= day and (self.superseded_on is None or day < self.superseded_on)


CATALOG: dict[str, PdsVersion] = {
    pds.pds_id: pds
    for pds in (
        PdsVersion("CLA-HOME-2024", "home", date(2024, 7, 1)),
        PdsVersion("CLA-MOTOR-2024", "motor", date(2024, 7, 1), superseded_on=date(2026, 1, 1)),
        PdsVersion("CLA-MOTOR-2026", "motor", date(2026, 1, 1)),
    )
}
