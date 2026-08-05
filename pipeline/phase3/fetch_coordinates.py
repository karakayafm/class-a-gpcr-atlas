#!/usr/bin/env python3
"""Phase 3A — coordinate acquisition.

Downloads the official RCSB/wwPDB mmCIF for every Class A structure, validates each response
before it is allowed into the cache, and records a manifest row for **every** structure —
including the ones that have no coordinates, which are marked rather than dropped.

    python3 pipeline/phase3/fetch_coordinates.py [--workers 6] [--refresh]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402

CFG = json.loads((ROOT / "config/phase3/coordinate_policy.json").read_text(encoding="utf-8"))
TPL = CFG["primary_source"]["url_template"]
CACHE = ROOT / "data/cache/coordinates"
UA = "class-a-gpcr-atlas/3.0 (coordinate acquisition; contact via repository)"
PARSER_VERSION = "phase3-coordinates-1.0.0"


def fetch(pdb_id: str, timeout: float, retries: int, refresh: bool) -> dict:
    url = TPL.format(PDB_ID=pdb_id)
    path = CACHE / f"{pdb_id}.cif.gz"
    row = {"pdb_id": pdb_id, "requested_url": url, "parser_version": PARSER_VERSION,
           "retrieved_at": utc_now()}
    if path.exists() and not refresh:
        raw = path.read_bytes()
        try:
            dec = gzip.decompress(raw)
        except Exception as exc:
            path.unlink(missing_ok=True)
            row.update(coordinate_availability="cache_corrupt_removed",
                       failure_reason=f"{type(exc).__name__}", http_status=None)
            return row
        row.update(resolved_url=url, http_status=200, cache_hit=True,
                   compressed_bytes=len(raw), decompressed_bytes=len(dec),
                   compressed_sha256=hashlib.sha256(raw).hexdigest(),
                   decompressed_sha256=hashlib.sha256(dec).hexdigest(),
                   etag=None, last_modified=None,
                   coordinate_availability="available", failure_reason=None)
        return row

    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                raw = fh.read()
                status, resolved = fh.status, fh.url
                etag = fh.headers.get("ETag")
                lastmod = fh.headers.get("Last-Modified")
            # response validation before anything touches the cache
            dec = gzip.decompress(raw)
            if b"_atom_site." not in dec:
                raise ValueError("no _atom_site loop in response")
            head = dec[:4096].decode("utf-8", "replace")
            if not head.lstrip().lower().startswith(f"data_{pdb_id.lower()}"):
                raise ValueError("data_ block does not match the requested id")
            tmp = CACHE / f"{pdb_id}.cif.gz.part"
            tmp.write_bytes(raw)
            tmp.replace(CACHE / f"{pdb_id}.cif.gz")
            row.update(resolved_url=resolved, http_status=status, cache_hit=False,
                       compressed_bytes=len(raw), decompressed_bytes=len(dec),
                       compressed_sha256=hashlib.sha256(raw).hexdigest(),
                       decompressed_sha256=hashlib.sha256(dec).hexdigest(),
                       etag=etag, last_modified=lastmod, retry_count=attempt,
                       coordinate_availability="available", failure_reason=None)
            return row
        except urllib.error.HTTPError as exc:
            last = f"http_{exc.code}"
            if exc.code == 404:
                break                      # a 404 is an answer, not a transient failure
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(1.0 * (attempt + 1))
    (CACHE / f"{pdb_id}.cif.gz.part").unlink(missing_ok=True)
    row.update(resolved_url=None, http_status=None, cache_hit=False,
               compressed_bytes=None, decompressed_bytes=None,
               compressed_sha256=None, decompressed_sha256=None,
               etag=None, last_modified=None, retry_count=retries,
               coordinate_availability="coordinate_unavailable", failure_reason=last)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=CFG["download_behaviour"]["max_workers"])
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)

    S = [json.loads(l) for l in
         (ROOT / "data/intermediate/structures.normalized.jsonl").read_text(
             encoding="utf-8").splitlines() if l.strip()]
    Sd = {s["pdb_id"]: s for s in S}
    ids = sorted(Sd)

    rows = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(lambda p: fetch(
                p, CFG["download_behaviour"]["timeout_seconds"],
                CFG["download_behaviour"]["retries"], args.refresh), ids):
            s = Sd[r["pdb_id"]]
            r["obsolete_status"] = s["structure_status"]
            r["replacement_pdb_ids"] = None
            r["major_family_id"] = s["major_family_id"]
            r["metadata_completeness"] = s["metadata_completeness"]
            rows.append(r)
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(ids)}", file=sys.stderr)

    rows.sort(key=lambda r: r["pdb_id"])
    out = ROOT / "data/intermediate/phase3/coordinate_manifest.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(canonical_dumps(r) for r in rows) + "\n", encoding="utf-8")

    avail = sum(1 for r in rows if r["coordinate_availability"] == "available")
    total_mb = sum(r["compressed_bytes"] or 0 for r in rows) / 1e6
    summary = {"generated_at": utc_now(), "structures": len(rows), "available": avail,
               "unavailable": len(rows) - avail,
               "failures": sorted([{"pdb_id": r["pdb_id"], "reason": r["failure_reason"]}
                                   for r in rows if r["coordinate_availability"] != "available"],
                                  key=lambda x: x["pdb_id"]),
               "compressed_total_mb": round(total_mb, 1),
               "manifest_sha256": content_sha256(rows),
               "cache_directory": str(CACHE.relative_to(ROOT)),
               "excluded_from_production_payload": True}
    (ROOT / "data/intermediate/phase3/_coordinate_summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in
                      ("structures", "available", "unavailable", "compressed_total_mb",
                       "manifest_sha256")}, indent=1))
    if summary["failures"]:
        print("başarısız:", json.dumps(summary["failures"][:8], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
