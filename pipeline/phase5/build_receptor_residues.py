#!/usr/bin/env python3
"""Per-structure receptor residue table: every generic-numbered residue, not only the pocket.

The viewer bundle carries two residue lists — the ligand's contacts and the twenty-one microswitch
positions — because those were the two questions the viewer was built to answer. Both are subsets
of the binding site's neighbourhood, so a reader who asks about a position outside it, say a run
along TM3, can name it in the motif panel and then has nothing to click in the viewer.

The coordinates were never the limit. The bundled `viewer.cif` holds the whole receptor chain; what
was missing was the table saying which residue in it carries which generic number. That table
already exists inside the pipeline, as the residue mapping Phase 3 builds from
mmCIF -> RCSB alignment -> GPCRdb. This writes the part of it the viewer needs, per structure.

It is written beside the payload tree rather than into `viewer_meta.json` for two reasons: the
Phase 5 tree is frozen, and the bundle is fetched every time a structure is opened while this is
wanted only when a reader asks for the whole receptor. Loaded on demand, it costs nothing until
then.

Only residues that are both generic-numbered and actually resolved in the coordinates are written.
A button for a residue with no atoms would select nothing and say nothing about why.

    python3 pipeline/phase5/build_receptor_residues.py \
        --mapping   ../class_a_gpcr_atlas/data/intermediate/phase3/receptor_residue_mapping.jsonl \
        --structures site/data/web/structures \
        --out       site/data/web/overlay/structures
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The seven helices are the shape the reader asked for, one column each. H8 and the loops are kept
# — dropping resolved, numbered residues to make the table tidier would be a different payload
# than the one this claims to be — and the panel groups them separately.
HELICES = ["TM1", "TM2", "TM3", "TM4", "TM5", "TM6", "TM7"]
SEGMENT_ORDER = ["N-term", "TM1", "ICL1", "TM2", "ECL1", "TM3", "ICL2", "TM4", "ECL2",
                 "TM5", "ICL3", "TM6", "ECL3", "TM7", "H8", "C-term"]

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
    "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
    "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}


def short(generic: str | None) -> str | None:
    """GPCRdb's combined form `5.42x43` carries both schemes; the atlas keys on the second."""
    if not generic:
        return None
    m = re.match(r"^(\d+)(?:\.\d+)?x(\d+[a-z]?)$", str(generic))
    return m.group(1) + "x" + m.group(2) if m else None


def position_sort_key(position: str):
    m = re.match(r"^(\d+)x(\d+)([a-z]?)$", position)
    return (int(m.group(1)), int(m.group(2)), m.group(3)) if m else (99, 9999, "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mapping", type=Path,
                        default=ROOT.parent / "class_a_gpcr_atlas/data/intermediate/phase3/"
                                              "receptor_residue_mapping.jsonl")
    parser.add_argument("--structures", type=Path, default=ROOT / "site/data/web/structures")
    parser.add_argument("--out", type=Path, default=ROOT / "site/data/web/overlay/structures")
    parser.add_argument("--limit", type=int, default=0, help="write only the first N structures")
    parser.add_argument("--dry-run", action="store_true", help="report sizes, write nothing")
    args = parser.parse_args()

    if not args.mapping.is_file():
        print("residue mapping not found: %s" % args.mapping, file=sys.stderr)
        return 2

    have = {p.name for p in args.structures.iterdir() if p.is_dir()} \
        if args.structures.is_dir() else set()
    if not have:
        print("no bundled structures under %s" % args.structures, file=sys.stderr)
        return 2

    by_pdb: dict[str, list[dict]] = collections.defaultdict(list)
    rows_read = skipped_unresolved = skipped_ungeneric = 0
    with args.mapping.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            pdb = d["pdb_id"]
            if pdb not in have:
                continue
            rows_read += 1
            position = short(d.get("canonical_generic_number"))
            if not position:
                skipped_ungeneric += 1
                continue
            # An unresolved residue has coordinates nowhere to draw. Counted, not written.
            if not d.get("observed_atom_count"):
                skipped_unresolved += 1
                continue
            by_pdb[pdb].append({
                "p": position,
                "c": d["auth_asym_id"],
                "n": str(d["auth_seq_id"]) + (d.get("insertion_code") or ""),
                # What the coordinates hold. Where the construct carries a mutation this is the
                # mutant, and `w` says what the wild type was — the same distinction the motif
                # panel makes, so the two never disagree about the same residue.
                "a": THREE_TO_ONE.get(str(d.get("residue_name", "")).upper(), "X"),
                "s": d.get("protein_segment") or "",
                **({"w": d["wild_type_residue"]} if d.get("depositor_reported_mutation")
                   or d.get("residue_identity_matches_wild_type") is False else {}),
            })

    written = total_bytes = 0
    segment_hist: collections.Counter = collections.Counter()
    per_structure_counts = []
    for pdb in sorted(by_pdb):
        residues = by_pdb[pdb]
        # One receptor copy can appear on several chains. The viewer draws one chain at a time, so
        # the table keeps them all and the panel picks the chain it is showing.
        residues.sort(key=lambda r: (r["c"], position_sort_key(r["p"])))
        for r in residues:
            segment_hist[r["s"]] += 1
        payload = {
            "schema": "receptor_residues",
            "schema_version": "1.0.0",
            "pdb_id": pdb,
            "note": ("Every residue of the receptor chain that carries a GPCRdb generic number and "
                     "is resolved in the deposited coordinates. `p` generic position, `c` chain, "
                     "`n` auth_seq_id, `a` the residue in the coordinates, `s` protein segment, "
                     "`w` the wild-type residue where the construct was mutated."),
            "segments": [s for s in SEGMENT_ORDER if any(r["s"] == s for r in residues)],
            "helices": HELICES,
            "counts": {
                "residues": len(residues),
                "chains": len({r["c"] for r in residues}),
                "helix_residues": sum(1 for r in residues if r["s"] in HELICES),
                "mutated": sum(1 for r in residues if "w" in r),
            },
            "residues": residues,
        }
        per_structure_counts.append(len(residues))
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        total_bytes += len(text.encode("utf-8"))
        written += 1
        if not args.dry_run:
            d = args.out / pdb
            d.mkdir(parents=True, exist_ok=True)
            (d / "receptor_residues.json").write_text(text, encoding="utf-8")
        if args.limit and written >= args.limit:
            break

    counts = sorted(per_structure_counts)
    print(json.dumps({
        "structures_bundled": len(have),
        "structures_written": written,
        "mapping_rows_for_bundled": rows_read,
        "skipped_no_generic_number": skipped_ungeneric,
        "skipped_unresolved": skipped_unresolved,
        "residues_written": sum(per_structure_counts),
        "residues_per_structure": {
            "min": counts[0] if counts else 0,
            "median": counts[len(counts) // 2] if counts else 0,
            "max": counts[-1] if counts else 0,
        },
        "bytes_total": total_bytes,
        "bytes_per_structure_median": total_bytes // written if written else 0,
        "by_segment": dict(segment_hist.most_common()),
        "dry_run": bool(args.dry_run),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
