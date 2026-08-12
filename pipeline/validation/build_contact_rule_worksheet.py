#!/usr/bin/env python3
"""Pick the structures whose contact shell should be checked against the primary literature.

DD-07 is open because the contact rule was reference-tested in one cell — aminergic small
molecules in the canonical pocket — and carried everywhere else. Testing all 29 cells is not
the ask; testing the ones that are both populated and geometrically unlike the tested cell is.

Cells are ranked on two measured quantities, taken from the sensitivity analysis:

  * how many observations the cell carries, which is how much rests on it, and
  * how far its geometry sits from the cell that was tested, measured as the ratio of receptor
    residues to ligand residues — around 17 where the rule was validated, and near 1 where the
    ligand is a polymer chain.

Three structures are drawn per cell: sharpest, median and least sharp. That spans the range the
rule has to survive and it is reproducible — no sampling seed, no judgement.

The worksheet leaves one column empty. Filling it means reading each paper and writing the
residues it states as the binding site or interface. Nothing here infers those residues, and
nothing should: this project has already corrected one figure reference that an external tool
supplied wrongly.

    python3 pipeline/validation/build_contact_rule_worksheet.py [--cells 6]
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common import curated_copies  # noqa: E402

SENSITIVITY = ROOT / "reports/validation/contact_rule_sensitivity.json"
CONTACTS = ROOT / "data/contacts/by_family"
WEB = ROOT / "data/web/families"
WORKSHEET = ROOT / "curation/contact_rule_reference.csv"
PLAN = ROOT / "reports/validation/CONTACT_RULE_SAMPLE.md"
# The cell the rule was reference-tested in, from family_validation_status.json.
TESTED_RATIO = 17.0
PER_CELL = 3


def load_structures():
    rows, references = {}, {}
    for path in sorted(WEB.glob("*/structures.json")):
        slug = path.parent.name
        for row in json.loads(path.read_text(encoding="utf-8"))["structures"]:
            rows[row["pdb_id"]] = (slug, row)
        ref = path.parent / "references.json"
        if ref.is_file():
            for entry in json.loads(ref.read_text(encoding="utf-8")).get("structure_sources", []):
                references[entry["pdb_id"]] = entry
    return rows, references


def observations_by_cell():
    residues = collections.defaultdict(lambda: {"r5": set(), "ligand": set()})
    label = {}
    for path in sorted(CONTACTS.glob("*/residue_pair_contacts.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if not curated_copies.keeps(row.get("ligand_entity_id"),
                                            row.get("ligand_auth_asym_id"),
                                            row.get("ligand_auth_seq_id")):
                    continue
                key = row["structure_ligand_id"]
                label[key] = (row.get("binding_site_class") or "unknown", row["pdb_id"])
                residues[key]["r5"].add((row["receptor_auth_asym_id"],
                                         row["receptor_auth_seq_id"],
                                         row.get("receptor_residue_name"),
                                         row.get("receptor_generic_number")))
                residues[key]["ligand"].add((row["ligand_auth_asym_id"],
                                             row["ligand_auth_seq_id"]))
    return residues, label


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", type=int, default=6,
                    help="how many cells to draw from, highest priority first")
    args = ap.parse_args()

    if not SENSITIVITY.is_file():
        raise SystemExit("run analyse_contact_rule_sensitivity.py first")
    cells = [c for c in json.loads(SENSITIVITY.read_text(encoding="utf-8"))["cells"] if c["ranked"]]
    for cell in cells:
        distance = abs(cell["median_receptor_per_ligand_residue"] - TESTED_RATIO) / TESTED_RATIO
        cell["priority"] = round(cell["observations"] * (0.25 + distance), 1)
    cells.sort(key=lambda c: -c["priority"])
    chosen = cells[:args.cells]

    structures, references = load_structures()
    residues, label = observations_by_cell()
    families = {pdb: slug for pdb, (slug, _) in structures.items()}

    grouped = collections.defaultdict(list)
    for key, acc in residues.items():
        site_class, pdb_id = label[key]
        if pdb_id not in families:
            continue
        grouped[(site_class, families[pdb_id])].append((key, pdb_id, acc))

    rows = []
    for cell in chosen:
        members = grouped.get((cell["site_class"], cell["family"]), [])
        # Sharpest, median and least sharp. Structures without a resolution sort last so the
        # sample is never silently drawn from entries that cannot be compared on it.
        def sharpness(item):
            resolution = structures[item[1]][1].get("resolution")
            return (resolution is None, resolution if resolution is not None else 0.0, item[1])
        members.sort(key=sharpness)
        if not members:
            continue
        picks = [members[0], members[len(members) // 2], members[-1]][:PER_CELL]
        seen = set()
        for key, pdb_id, acc in picks:
            if key in seen:
                continue
            seen.add(key)
            record = structures[pdb_id][1]
            citation = (references.get(pdb_id) or {}).get("primary_citation") or {}
            listed = sorted(acc["r5"], key=lambda r: (r[0], int(r[1]) if str(r[1]).lstrip("-").isdigit() else 0))
            rows.append({
                "pdb_id": pdb_id,
                "family": cell["family"],
                "site_class": cell["site_class"],
                "receptor": record.get("receptor_name", ""),
                "resolution_A": record.get("resolution", ""),
                "method": record.get("experimental_method", ""),
                "doi": citation.get("doi", ""),
                "pubmed_id": citation.get("pubmed_id", ""),
                "atlas_residue_count": len(listed),
                "atlas_residues": " ".join(
                    f"{r[2] or '?'}{r[1]}" + (f"({r[3]})" if r[3] else "") for r in listed),
                "paper_residues": "",
                "paper_states_residues": "",
                "notes": "",
            })

    WORKSHEET.parent.mkdir(parents=True, exist_ok=True)
    with WORKSHEET.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    PLAN.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Contact rule reference sample",
        "",
        "Generated by `pipeline/validation/build_contact_rule_worksheet.py`.",
        "",
        "Cells ranked by how much rests on them and how far their geometry sits from the one",
        f"cell the rule was reference-tested in (receptor residues per ligand residue ≈ {TESTED_RATIO:.0f}).",
        f"{PER_CELL} structures per cell: sharpest, median, least sharp.",
        "",
        "| Rank | Site class | Family | Observations | Receptor per ligand residue | Priority |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for n, cell in enumerate(chosen, 1):
        lines.append(f"| {n} | {cell['site_class']} | {cell['family']} | {cell['observations']} |"
                     f" {cell['median_receptor_per_ligand_residue']} | {cell['priority']} |")
    lines += [
        "",
        f"Worksheet: `{WORKSHEET.relative_to(ROOT)}` — {len(rows)} structures.",
        "",
        "`paper_residues` is empty by design. It holds the residues the primary paper states as",
        "the binding site or interface, written by a reader, in the paper's own numbering. Leave",
        "`paper_states_residues` as `no` where a paper states none; that is a finding, not a gap,",
        "and the test counts those cells separately rather than scoring them.",
        "",
    ]
    PLAN.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"cells": len(chosen), "structures": len(rows),
                      "worksheet": str(WORKSHEET.relative_to(ROOT)),
                      "plan": str(PLAN.relative_to(ROOT))}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
