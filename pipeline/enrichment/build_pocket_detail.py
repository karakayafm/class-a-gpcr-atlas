#!/usr/bin/env python3
"""E5: build family-sharded, residue-level pocket detail payloads."""
from __future__ import annotations

import gzip
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.generic_numbers import display_generic_number  # noqa: E402

UNIVERSE = ROOT / "data/normalized/class_a_structure_universe.json"
STRUCTURES = ROOT / "data/intermediate/structures.normalized.jsonl"
CONTACTS = ROOT / "data/contacts/by_family"
OUTPUT = ROOT / "data/intermediate/enrichment/pocket_detail"
SCHEMA = ROOT / "schemas/enrichment/pocket_detail.schema.json"
REPORT = ROOT / "reports/enrichment_pocket_detail.md"
MAX_BYTES = 5 * 1024 * 1024

AA3_TO_1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "SEC": "U", "PYL": "O",
}


def band(distance: float) -> str:
    if distance <= 3.5:
        return "≤3.5"
    if distance <= 4.3:
        return "3.5–4.3"
    return "4.3–5.0"


def residue_key(row: dict) -> tuple[str, str, str]:
    return (row["receptor_auth_asym_id"], str(row["receptor_auth_seq_id"]),
            row.get("receptor_insertion_code") or "")


def segment_key(value: str | None) -> tuple[int, str]:
    if value and value.startswith("TM") and value[2:].isdigit():
        return int(value[2:]), value
    order = {"N-term": 0, "ICL1": 25, "ECL1": 35, "ICL2": 45,
             "ECL2": 55, "ICL3": 65, "ECL3": 75, "H8": 80, "C-term": 90}
    return order.get(value, 99), value or ""


def main() -> None:
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))["structures"]
    structure_meta = {row["pdb_id"]: row for row in
                      (json.loads(line) for line in STRUCTURES.read_text(encoding="utf-8").splitlines()
                       if line.strip())}
    family_by_pdb = {row["pdb_id"]: row["major_family_id"] for row in universe}
    structures_by_family = defaultdict(list)
    for pdb_id, family_id in family_by_pdb.items():
        structures_by_family[family_id].append(pdb_id)

    nearest = defaultdict(dict)
    source_rows = 0
    for path in sorted(CONTACTS.glob("*/residue_pair_contacts.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                source_rows += 1
                pdb_id = row["pdb_id"]
                key = residue_key(row)
                old = nearest[pdb_id].get(key)
                if old is None or row["min_distance_angstrom"] < old["min_distance_angstrom"]:
                    nearest[pdb_id][key] = row

    validator = jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8")))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output_index, built_records = {}, {}
    for family_id in sorted(structures_by_family):
        structures = []
        for pdb_id in sorted(structures_by_family[family_id]):
            groups = defaultdict(list)
            for row in nearest.get(pdb_id, {}).values():
                distance = row["min_distance_angstrom"]
                groups[row.get("receptor_segment")].append({
                    "chain": row["receptor_auth_asym_id"],
                    "auth_seq_id": str(row["receptor_auth_seq_id"]),
                    "insertion_code": row.get("receptor_insertion_code") or None,
                    "residue_name": row["receptor_residue_name"],
                    "aa": AA3_TO_1.get(row["receptor_residue_name"]),
                    "generic_number": display_generic_number(row.get("receptor_generic_number")),
                    "distance_angstrom": distance,
                    "distance_band": band(distance),
                    "binding_site_class": row.get("binding_site_class"),
                    "ligand_residue_name": row.get("ligand_residue_name"),
                    "closest_receptor_atom": row.get("closest_receptor_atom"),
                    "closest_ligand_atom": row.get("closest_ligand_atom"),
                })
            segments = []
            for segment in sorted(groups, key=segment_key):
                residues = sorted(groups[segment], key=lambda item: (
                    item["distance_angstrom"], item["chain"], item["auth_seq_id"]))
                segments.append({"segment": segment, "residues": residues})
            flat = [item for group in segments for item in group["residues"]]
            meta = structure_meta[pdb_id]
            empty_reason = None
            if not flat:
                if meta["apo_status"] == "confirmed_apo":
                    empty_reason = "confirmed_apo"
                elif meta["pharmacological_ligand_count"] > 0:
                    empty_reason = "ligand_present_no_contacts_upstream"
                else:
                    empty_reason = "apo_status_unresolved"
            record = {"pdb_id": pdb_id,
                      "ligand_status": meta["ligand_status"],
                      "pharmacological_ligand_count": meta["pharmacological_ligand_count"],
                      "empty_reason": empty_reason, "n_contacts": len(flat),
                      "n_mapped": sum(item["generic_number"] is not None for item in flat),
                      "segments": segments}
            structures.append(record)
            built_records[pdb_id] = record
        payload = {"family_id": family_id, "structures": structures}
        errors = list(validator.iter_errors(payload))
        if errors:
            raise RuntimeError(f"{family_id} pocket schema error: {errors[0].message}")
        path = OUTPUT / f"{family_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) + "\n", encoding="utf-8")
        size = path.stat().st_size
        if size > MAX_BYTES:
            raise RuntimeError(f"{path} exceeds 5 MiB: {size}")
        output_index[family_id] = {"file": path.name, "bytes": size,
                                   "structures": len(structures)}

    if len(built_records) != 1358:
        raise RuntimeError(f"expected 1358 structures, built {len(built_records)}")
    candidates = sorted(pdb_id for pdb_id, rows in nearest.items() if rows)
    sampled = random.Random(20260808).sample(candidates, 5)
    sample_results = []
    for pdb_id in sampled:
        expected = sorted((key, row["min_distance_angstrom"])
                          for key, row in nearest[pdb_id].items())
        actual = sorted(((item["chain"], item["auth_seq_id"], item["insertion_code"] or ""),
                         item["distance_angstrom"])
                        for group in built_records[pdb_id]["segments"]
                        for item in group["residues"])
        if expected != actual:
            raise RuntimeError(f"source/output residue mismatch for {pdb_id}")
        sample_results.append((pdb_id, len(actual)))

    largest_family, largest = max(output_index.items(), key=lambda item: item[1]["bytes"])
    empty = sum(record["n_contacts"] == 0 for record in built_records.values())
    empty_counts = {reason: sum(record["empty_reason"] == reason
                                for record in built_records.values())
                    for reason in ("confirmed_apo", "apo_status_unresolved",
                                   "ligand_present_no_contacts_upstream")}
    upstream_gaps = sorted((record for record in built_records.values()
                            if record["empty_reason"] == "ligand_present_no_contacts_upstream"),
                           key=lambda record: record["pdb_id"])
    report = ["# Enrichment pocket detail", "",
              f"Source pair-contact rows: {source_rows}.",
              f"Structure records: {len(built_records)}; with no eligible contact rows: {empty}.",
              f"Empty reasons: confirmed apo {empty_counts['confirmed_apo']}; apo status unresolved "
              f"{empty_counts['apo_status_unresolved']}; ligand present but no upstream contacts "
              f"{empty_counts['ligand_present_no_contacts_upstream']}.",
              f"Family shards: {len(output_index)}; largest: `{largest_family}.json` "
              f"({largest['bytes']} bytes, {largest['bytes'] / 1048576:.2f} MiB).", "",
              "## Family files", "", "| Family | Structures | Bytes |", "|---|---:|---:|"]
    for family_id, item in output_index.items():
        report.append(f"| `{family_id}` | {item['structures']} | {item['bytes']} |")
    report += ["", "## Deterministic five-structure source check", ""]
    report.extend(f"- `{pdb_id}`: {count} residue minima, exact source-distance match."
                  for pdb_id, count in sample_results)
    report += ["", "Generic-number display conversion uses the shared "
               "`pipeline/common/generic_numbers.py` helper (`3.28x28` → `3x28`).", ""]
    report += ["## Ligand-present structures with no upstream contact rows", "",
               "These are retained as explicit computation gaps; no Phase 3/4 contacts are invented.", "",
               "| PDB | ligand_status | pharmacological_ligand_count |", "|---|---|---:|"]
    report.extend(f"| `{record['pdb_id']}` | `{record['ligand_status']}` | "
                  f"{record['pharmacological_ligand_count']} |" for record in upstream_gaps)
    report.append("")
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"source_rows": source_rows, "structures": len(built_records),
                      "empty_structures": empty, "families": len(output_index),
                      "empty_reasons": empty_counts,
                      "largest_family": largest_family, "largest_bytes": largest["bytes"],
                      "sampled": sampled, "schema_errors": 0}, indent=2))


if __name__ == "__main__":
    main()
