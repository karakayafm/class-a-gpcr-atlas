#!/usr/bin/env python3
"""Audit atlas PDB IDs against the RCSB removed-entry holdings service."""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "data/normalized/class_a_structure_universe.json"
CACHE = ROOT / "data/cache/rcsb_holdings"
OUTPUT = ROOT / "config/enrichment/superseded_structures.json"
LIST_URL = "https://data.rcsb.org/rest/v1/holdings/removed/entry_ids"
DETAIL_URL = "https://data.rcsb.org/rest/v1/holdings/removed/{id}"
USER_AGENT = "class-a-gpcr-atlas/5.0 (superseded structure audit; contact via repository)"


def fetch(url: str, path: Path) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return json.loads(raw)


def load_or_fetch(url: str, path: Path, refresh: bool) -> object:
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    return fetch(url, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true",
                        help="refresh the official RCSB removed list and matching details")
    args = parser.parse_args()
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))["structures"]
    atlas_ids = {row["pdb_id"].upper() for row in universe}
    removed = set(load_or_fetch(LIST_URL, CACHE / "removed_entry_ids.json", args.refresh))
    intersection = sorted(atlas_ids & {value.upper() for value in removed})
    records = {}
    for pdb_id in intersection:
        payload = load_or_fetch(DETAIL_URL.format(id=pdb_id.lower()),
                                CACHE / f"removed_{pdb_id}.json", args.refresh)
        item = payload["rcsb_repository_holdings_removed"]
        replacements = [value.upper() for value in item.get("id_codes_replaced_by", [])]
        records[pdb_id] = {
            "replaced_by": replacements,
            "replacement_in_atlas": bool(set(replacements) & atlas_ids),
            "remove_date": (item.get("remove_date") or "").split("T", 1)[0] or None,
            "details": item.get("details"),
            "title": item.get("title"),
            "source": DETAIL_URL.format(id=pdb_id.lower()),
        }
    output = {
        "checked": "2026-08-08",
        "removed_list_source": LIST_URL,
        "removed_list_count": len(removed),
        "atlas_structure_count": len(atlas_ids),
        "intersection_count": len(intersection),
        "structures": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    declared = {"7XOX", "8ZFJ"}
    new_matches = sorted(set(intersection) - declared)
    missing_declared = sorted(declared - set(intersection))
    print(json.dumps({"removed": len(removed), "atlas": len(atlas_ids),
                      "intersection": intersection, "new_matches": new_matches,
                      "missing_declared": missing_declared}, indent=2))
    if new_matches:
        print("WARNING: new removed atlas structures require curation: " + ", ".join(new_matches))
        return 2
    if missing_declared:
        print("WARNING: expected removed atlas structures disappeared from the live intersection: " +
              ", ".join(missing_declared))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
