"""Canonical JSON and content hashing.

Content hashes must not move when a record is merely re-fetched, so volatile provenance
fields are stripped before hashing. Two hashes are produced for every artefact:

- ``content`` — scientific content only, volatile fields removed
- ``package`` — the artefact exactly as written, including provenance

Both are documented in the freeze manifest so a reader knows which one changed.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

PARSER_VERSION = "1.0.0"

# Fields whose value changes on every run without the science changing.
VOLATILE_KEYS = frozenset({
    "retrieved_at", "retrieval_timestamp", "generated_at", "queried_at",
    "cache_path", "elapsed_seconds", "retry_count", "response_sha256",
    "http_status", "response_content_type",
})


def canonical_dumps(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no gratuitous whitespace, UTF-8, non-ASCII kept."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: strip_volatile(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [strip_volatile(v) for v in obj]
    return obj


def content_sha256(obj: Any) -> str:
    """Hash of the scientific content, volatile provenance removed."""
    return hashlib.sha256(canonical_dumps(strip_volatile(obj)).encode("utf-8")).hexdigest()


def package_sha256(obj: Any) -> str:
    """Hash of the artefact as written, provenance included."""
    return hashlib.sha256(canonical_dumps(obj).encode("utf-8")).hexdigest()


def bytes_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path, obj) -> dict:
    """Write canonical JSON and return both hashes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "bytes": len(text.encode("utf-8")),
            "content_sha256": content_sha256(obj), "package_sha256": package_sha256(obj)}
