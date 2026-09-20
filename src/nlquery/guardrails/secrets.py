"""Prevent known credentials and credential-shaped input from entering artifacts."""

import json
import re
from typing import Any

from nlquery.exceptions import PolicyViolation

_PATTERN = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://[^\s/]+:[^\s/@]+@|\b(?:api[_-]?key|password|passwd|token|secret)\s*[:=]\s*[^\s,;]+|\bsk-[A-Za-z0-9_-]{12,})",
    re.I,
)


def ensure_safe(value: Any, secrets: list[str] | None = None) -> None:
    """Reject rather than serialize sensitive data. Does not claim arbitrary secret detection."""
    text = json.dumps(value, default=str)
    if _PATTERN.search(text) or any(s and s in text for s in (secrets or [])):
        raise PolicyViolation("Sensitive material is not permitted in query context or artifacts")
