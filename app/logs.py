"""Structured logging that never writes phone numbers or transcripts."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

# Digit runs (optionally +, spaces, dashes) not glued to letters/hyphens, so UUIDs survive.
_PHONE = re.compile(r"(?<![\w-])\+?\d[\d\s\-]{7,}\d(?![\w-])")
_DENY = frozenset({
    "phone", "recipient_phone_number", "to_number", "from_number", "from_phone_number",
    "transcript", "text", "turns", "user_data", "recipient_data", "recording_url",
})

_logger = logging.getLogger("smriti")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return _PHONE.sub("[redacted-number]", value)
    if isinstance(value, dict):
        return {k: ("[redacted]" if k in _DENY else redact(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


def log(event: str, level: int = logging.INFO, **fields: Any) -> None:
    """One JSON line per event. Pass ids (session_id, execution_id), never personal data."""
    _logger.log(level, json.dumps({"event": event, **redact(fields)}, default=str, ensure_ascii=False))
