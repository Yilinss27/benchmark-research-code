"""Common JSON extraction helpers for model responses."""

from __future__ import annotations

import json
import re
from typing import Any


CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _try_parse_json(text: str) -> dict[str, Any] | list[Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


def _extract_with_raw_decode(text: str) -> dict[str, Any] | list[Any] | None:
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed
    return None


def extract_json_from_response(response: str) -> dict[str, Any] | list[Any]:
    """Extract a JSON object or array from a raw model response."""
    parsed = _try_parse_json(response)
    if parsed is not None:
        return parsed

    code_block_match = CODE_BLOCK_RE.search(response)
    if code_block_match:
        parsed = _try_parse_json(code_block_match.group(1))
        if parsed is not None:
            return parsed

    parsed = _extract_with_raw_decode(response)
    if parsed is not None:
        return parsed

    raise ValueError("Could not extract valid JSON object or array from response")
