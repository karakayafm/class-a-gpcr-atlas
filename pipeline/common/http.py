"""Cached, provenance-recording HTTP client. Standard library only.

Rules enforced here, from the frozen scope:

- every response is cached verbatim before parsing;
- a failed response never overwrites a good cache entry;
- every request produces a provenance record (endpoint, status, checksum, timing);
- refresh is explicit, never implicit.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .canonical import bytes_sha256

USER_AGENT = ("class-a-gpcr-atlas/0.1 (Phase 1 universe build; "
              "contact via project repository)")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Fetcher:
    def __init__(self, cache_dir: Path, provider: str, timeout: float = 60.0,
                 retries: int = 3, delay: float = 0.0, refresh: bool = False):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self.refresh = refresh
        self.provenance: list[dict] = []

    def _cache_path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "_")
        return self.cache_dir / f"{safe}.json"

    def get_json(self, url: str, key: str, params: dict | None = None):
        cache = self._cache_path(key)
        if cache.exists() and not self.refresh:
            raw = cache.read_bytes()
            self.provenance.append({
                "provider": self.provider, "endpoint": url, "query_parameters": params or {},
                "retrieval_timestamp": utc_now(), "http_status": None,
                "response_content_type": "application/json", "response_sha256": bytes_sha256(raw),
                "cache_path": str(cache), "cache_hit": True, "success": True,
                "retry_count": 0, "error_message": None,
            })
            return json.loads(raw.decode("utf-8"))

        last_err, status, attempt = None, None, 0
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as fh:
                    raw = fh.read()
                    status = fh.status
                    ctype = fh.headers.get("Content-Type", "")
                # Only a successful body is allowed to touch the cache.
                cache.write_bytes(raw)
                self.provenance.append({
                    "provider": self.provider, "endpoint": url, "query_parameters": params or {},
                    "retrieval_timestamp": utc_now(), "http_status": status,
                    "response_content_type": ctype, "response_sha256": bytes_sha256(raw),
                    "cache_path": str(cache), "cache_hit": False, "success": True,
                    "retry_count": attempt, "error_message": None,
                })
                if self.delay:
                    time.sleep(self.delay)
                return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                status, last_err = exc.code, f"HTTP {exc.code}"
                if exc.code == 404:
                    break
            except Exception as exc:                       # network / timeout / decode
                last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5 * (attempt + 1))

        self.provenance.append({
            "provider": self.provider, "endpoint": url, "query_parameters": params or {},
            "retrieval_timestamp": utc_now(), "http_status": status,
            "response_content_type": None, "response_sha256": None,
            "cache_path": str(cache) if cache.exists() else None,
            "cache_hit": False, "success": False, "retry_count": attempt,
            "error_message": last_err,
        })
        return None
