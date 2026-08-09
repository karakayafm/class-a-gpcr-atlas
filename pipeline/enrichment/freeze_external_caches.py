#!/usr/bin/env python3
"""Freeze the external-resource caches with retrieval dates and checksums.

The normal build never calls an external API — it reads these caches. That only holds if the
caches are pinned: a manifest records what was retrieved, when, and with which checksum, so a
rebuild can prove it used the same bytes and a silent refresh cannot pass unnoticed.

This matters most for GtoPdb, whose REST service is announced to require an API key from the
end of August 2026. A build that depended on the live service would stop working; a build that
depends on a frozen cache does not.

Refreshing a cache is a separate, deliberate act — the fetchers take `--refresh`. This script
only records what is already on disk.

    python3 pipeline/enrichment/freeze_external_caches.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/cache"
OUT = ROOT / "data/cache/external_cache_manifest.json"

# Cache directories the enrichment stage reads, with the resource each one mirrors.
SOURCES = {
    "gtopdb": "IUPHAR/BPS Guide to Pharmacology web services",
    "chembl": "ChEMBL REST API",
    "pubchem": "PubChem PUG REST",
    "unichem": "EBI UniChem",
    "rcsb_chemcomp": "RCSB PDB Data API, chemical components",
    "rcsb": "RCSB PDB Data API, entries",
    "ncbi": "NCBI E-utilities",
}


def digest_directory(path: Path) -> tuple[int, int, str]:
    """File count, total bytes and one checksum over the whole directory.

    The checksum folds in each file's relative path as well as its content, so a renamed or
    removed file changes the result even when the remaining bytes are identical.
    """
    files = sorted(p for p in path.rglob("*") if p.is_file())
    running = hashlib.sha256()
    total = 0
    for item in files:
        running.update(str(item.relative_to(path)).encode("utf-8"))
        data = item.read_bytes()
        running.update(hashlib.sha256(data).digest())
        total += len(data)
    return len(files), total, running.hexdigest()


def main() -> int:
    existing = {}
    if OUT.exists():
        existing = {s["directory"]: s for s in
                    json.loads(OUT.read_text(encoding="utf-8")).get("sources", [])}

    today = dt.date.today().isoformat()
    sources = []
    for name, resource in sorted(SOURCES.items()):
        path = CACHE / name
        if not path.is_dir():
            continue
        count, total, checksum = digest_directory(path)
        previous = existing.get(name)
        # The retrieval date is the day the bytes last changed, not the day this ran, so
        # re-freezing an untouched cache does not make it look freshly downloaded.
        if previous and previous.get("checksum") == checksum:
            retrieved = previous.get("frozen_on", today)
        else:
            retrieved = today
        sources.append({"directory": name, "resource": resource, "files": count,
                        "bytes": total, "checksum": checksum, "frozen_on": retrieved})

    payload = {
        "schema": "external_cache_manifest",
        "schema_version": "1.0.0",
        "note": ("The normal build reads these caches and makes no network call. Refreshing is a "
                 "separate, deliberate action; see the --refresh flag on the fetchers."),
        "sources": sources,
    }
    OUT.write_text(json.dumps(payload, sort_keys=True, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    for source in sources:
        print(f"{source['directory']:16s} {source['files']:5d} files "
              f"{source['bytes']:10d} bytes  frozen {source['frozen_on']}  "
              f"{source['checksum'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
