"""Content-addressed cache helpers for official public evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OFFICIAL_CACHE = Path("data/cache/official")


def sha256_text(content: str) -> str:
    """Return the SHA-256 digest of UTF-8 text."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_provenance(
    cache_key: str,
    *,
    source_url: str,
    content: str,
    parser_version: str,
    metadata: dict[str, Any] | None = None,
    cache_dir: Path | str = DEFAULT_OFFICIAL_CACHE,
) -> dict[str, Any]:
    """Persist source content and an auditable provenance sidecar."""
    root = Path(cache_dir)
    safe_key = cache_key.replace("/", "_").replace(":", "_")
    content_hash = sha256_text(content)
    fetched_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "cache_key": cache_key,
        "source_url": source_url,
        "fetched_at": fetched_at,
        "content_sha256": content_hash,
        "parser_version": parser_version,
        **(metadata or {}),
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{safe_key}.source").write_text(content, encoding="utf-8")
    (root / f"{safe_key}.provenance.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def read_provenance(
    cache_key: str,
    *,
    cache_dir: Path | str = DEFAULT_OFFICIAL_CACHE,
) -> tuple[str, dict[str, Any]] | None:
    """Load cached source and verify its stored content hash."""
    root = Path(cache_dir)
    safe_key = cache_key.replace("/", "_").replace(":", "_")
    source_path = root / f"{safe_key}.source"
    metadata_path = root / f"{safe_key}.provenance.json"
    if not source_path.exists() or not metadata_path.exists():
        return None
    content = source_path.read_text(encoding="utf-8")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("content_sha256") != sha256_text(content):
        return None
    return content, metadata
