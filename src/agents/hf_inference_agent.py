"""Direct Hugging Face Inference agent for single-turn benchmark calls."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


SYSTEM_INSTRUCTION = (
    "你是一个严格遵循输出格式的金融 benchmark 答题模型。"
    "请只输出题目要求的 JSON，不要输出额外解释。"
)


def _build_inputs(prompt: str) -> str:
    """Build a single-turn text prompt for Hugging Face Inference."""
    return f"System: {SYSTEM_INSTRUCTION}\n\nUser:\n{prompt}"


def _parse_hf_response(payload: Any) -> str:
    """Normalize common Hugging Face Inference response formats into text."""
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict) and isinstance(first.get("generated_text"), str):
            return first["generated_text"]
    if isinstance(payload, dict):
        if isinstance(payload.get("generated_text"), str):
            return payload["generated_text"]
        if "error" in payload:
            raise RuntimeError(f"Hugging Face Inference error: {payload['error']}")
    raise RuntimeError("Unexpected Hugging Face Inference response format")


def hf_inference_agent(
    prompt: str,
    record: dict[str, Any],
    model: str = "Qwen/Qwen3-8B",
    api_key: str = "",
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout_seconds: float = 60.0,
) -> str:
    """Call Hugging Face Inference and return the raw generated text."""
    del record

    if not api_key:
        raise RuntimeError("Missing Hugging Face API key")

    url = f"https://api-inference.huggingface.co/models/{model}"
    body = {
        "inputs": _build_inputs(prompt),
        "parameters": {
            "temperature": temperature,
            "max_new_tokens": max_tokens,
            "return_full_text": False,
        },
    }
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8")
            error_json = json.loads(error_body)
            if isinstance(error_json, dict) and "error" in error_json:
                raise RuntimeError(f"Hugging Face Inference error: {error_json['error']}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        raise RuntimeError(f"Hugging Face Inference HTTP error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Hugging Face Inference request failed: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"Hugging Face Inference request failed: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Hugging Face Inference returned non-JSON response") from exc

    text = _parse_hf_response(payload)
    if not text.strip():
        raise RuntimeError("Hugging Face Inference returned empty response")
    return text
