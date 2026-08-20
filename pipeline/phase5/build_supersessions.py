#!/usr/bin/env python3
"""Withdrawn PDB entries and what replaced them, as a side file the search can answer from.

A structure withdrawn from the PDB is kept out of the search index deliberately: leading a reader
to a retracted entry is worse than not finding it. Where its replacement is in the atlas that costs
nothing, because the replacement carries the old identifier as an alias and the search resolves it.

Where the replacement is *not* in the atlas there is nothing to attach the alias to, and both
identifiers return "no matching structure found" — the atlas knowing perfectly well that one
withdrew the other. That is the silence this file removes. It is small enough to be an afterthought
in bytes and is fetched only when a search finds nothing.

    python3 pipeline/phase5/build_supersessions.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--families", type=Path, default=ROOT / "site/data/web/families")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "site/data/web/global/supersessions.json")
    args = parser.parse_args()

    in_atlas, records, family_of = set(), {}, {}
    for path in sorted(args.families.glob("*/structures.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        slug = data.get("family_slug") or ("ca-" + str(data.get("family_id", "")).replace("_", "-"))
        for record in data["structures"]:
            in_atlas.add(record["pdb_id"])
            family_of[record["pdb_id"]] = record.get("family_slug") or slug
            superseded = record.get("superseded")
            if superseded:
                records[record["pdb_id"]] = superseded

    entries = []
    for pdb in sorted(records):
        s = records[pdb]
        replaced_by = [r.upper() for r in (s.get("replaced_by") or [])]
        entries.append({
            "pdb_id": pdb,
            "remove_date": s.get("remove_date"),
            "replaced_by": replaced_by,
            # Whether the reader can go and look at the replacement here, or has to leave.
            "replacement_in_atlas": bool(s.get("replacement_in_atlas")),
            # The withdrawn entry itself is still in the atlas — scored, and shown with its notice
            # — it is only kept out of the search. Said explicitly so the search can offer it.
            "withdrawn_in_atlas": pdb in in_atlas,
            "details": s.get("details"),
            "source": s.get("source"),
            # Where to send a reader for whichever of the two this atlas carries.
            "family_slug": family_of.get(pdb),
            "replacement_family_slug": next((family_of[r] for r in replaced_by
                                             if r in family_of), None),
        })

    payload = {
        "schema": "supersessions",
        "schema_version": "1.0.0",
        "note": ("PDB entries withdrawn after this release was assembled, and what replaced them. "
                 "`withdrawn_in_atlas` is whether the withdrawn entry is still carried here; "
                 "`replacement_in_atlas` is whether its replacement is."),
        "counts": {
            "withdrawn": len(entries),
            "replacement_here": sum(1 for e in entries if e["replacement_in_atlas"]),
            "replacement_elsewhere": sum(1 for e in entries if not e["replacement_in_atlas"]),
        },
        "entries": entries,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["counts"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
