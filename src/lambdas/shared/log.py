"""Structured logging: one JSON object per line, always carrying the claim id when known.

Lambda sends stdout to CloudWatch Logs, where these lines can be queried by field.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def log(event: str, **fields: Any) -> None:
    record = {"event": event, **fields}
    print(json.dumps(record, default=str, sort_keys=True), file=sys.stdout, flush=True)
