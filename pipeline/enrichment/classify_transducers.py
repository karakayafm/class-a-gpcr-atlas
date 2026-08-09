#!/usr/bin/env python3
"""E1: classify deposited transducers without mixing in functional evidence."""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "data/normalized/class_a_structure_universe.json"
ENTRY_MAP = ROOT / "config/enrichment/transducer_entry_map.json"
CLASS_VOCAB = ROOT / "config/transducer_classes.json"
POLYMER_REFERENCE = ROOT / "config/polymer_role_reference.json"
RCSB_ENTITIES = ROOT / "data/raw/rcsb/entity_payload.json"
OUTPUT = ROOT / "data/intermediate/enrichment/transducer_assignments.jsonl"
REPORT = ROOT / "reports/enrichment_transducer.md"

EXPECTED_ANNOTATED = {
    # The plan's pre-run counted the two F6VL43 structures as beta/gamma-only.
    # Official UniProt resolution identifies F6VL43 as GNAI3, moving both to Gi/o.
    "Gi/o": 420,
    "Gs": 238,
    "Gq/11": 121,
    "arrestin": 12,
    "G12/13": 7,
}


def polymer_accessions(entity: dict) -> set[str]:
    identifiers = entity.get("rcsb_polymer_entity_container_identifiers") or {}
    accessions = set(identifiers.get("uniprot_ids") or [])
    for alignment in entity.get("rcsb_polymer_entity_align") or []:
        if alignment.get("reference_database_name") == "UniProt":
            accession = alignment.get("reference_database_accession")
            if accession:
                accessions.add(accession)
    for record in entity.get("uniprots") or []:
        if record.get("rcsb_id"):
            accessions.add(record["rcsb_id"])
    return accessions


def rcsb_transducer_components(
    pdb_id: str, entries: dict, accessions: dict, accession_classes: dict
) -> list[dict]:
    """Use the same curated accession table consumed by Phase 2 normalization."""
    if pdb_id not in entries:
        raise RuntimeError(f"RCSB polymer inventory is absent for {pdb_id}")
    components = []
    for entity in entries[pdb_id].get("polymer_entities") or []:
        matched = sorted(polymer_accessions(entity) & accessions.keys())
        if not matched:
            continue
        identifiers = entity.get("rcsb_polymer_entity_container_identifiers") or {}
        polymer = entity.get("rcsb_polymer_entity") or {}
        components.append({
            "entity_id": identifiers.get("entity_id"),
            "auth_asym_ids": identifiers.get("auth_asym_ids") or [],
            "description": polymer.get("pdbx_description"),
            "uniprot_accessions": matched,
            "identities": [accessions[a] for a in matched],
            "panel_classes": sorted({accession_classes[a] for a in matched
                                     if a in accession_classes}),
        })
    return components


def main() -> int:
    structures = json.loads(UNIVERSE.read_text(encoding="utf-8"))["structures"]
    entry_map = json.loads(ENTRY_MAP.read_text(encoding="utf-8"))
    vocabulary = set(json.loads(CLASS_VOCAB.read_text(encoding="utf-8"))["transducer_classes"])
    polymer_reference = json.loads(POLYMER_REFERENCE.read_text(encoding="utf-8"))
    transducer_accessions = polymer_reference["uniprot_accessions"]["transducer_component"]
    accession_classes = {
        mapping["uniprot"]: mapping["class"] for mapping in entry_map.values()
        if mapping["determines_panel"]
    }
    rcsb_entries = json.loads(RCSB_ENTITIES.read_text(encoding="utf-8"))["entries"]

    observed_names = {
        item.get("entry_name")
        for structure in structures
        for item in (((structure.get("gpcrdb_structure_record") or {})
                      .get("raw_signalling_protein_annotation") or {}).get("data") or {}).values()
    }
    observed_names.discard(None)
    missing_map = sorted(observed_names - entry_map.keys())
    extra_map = sorted(entry_map.keys() - observed_names)
    if missing_map or extra_map:
        raise RuntimeError(f"entry map mismatch; missing={missing_map}, extra={extra_map}")
    if len(entry_map) != 30:
        raise RuntimeError(f"expected 30 mapped entry names, found {len(entry_map)}")
    for name, mapping in entry_map.items():
        if mapping["determines_panel"] and mapping["class"] not in vocabulary:
            raise RuntimeError(f"{name} maps outside configured vocabulary: {mapping['class']}")
        if not mapping.get("uniprot") or not mapping.get("verified"):
            raise RuntimeError(f"{name} lacks UniProt verification metadata")

    rows = []
    annotated_counts = collections.Counter()
    missing_inventory = []
    conflicts = []
    for structure in sorted(structures, key=lambda value: value["pdb_id"]):
        pdb_id = structure["pdb_id"]
        annotation = ((structure.get("gpcrdb_structure_record") or {})
                      .get("raw_signalling_protein_annotation"))
        row = {
            "pdb_id": pdb_id,
            "transducer_class": None,
            "panels": [],
            "entry_names": [],
            "components": [],
            "assignment_evidence": None,
            "source_conflicts": [],
        }
        if annotation:
            row["entry_names"] = sorted({
                item["entry_name"] for item in (annotation.get("data") or {}).values()
            })
            determining = sorted({
                entry_map[name]["class"] for name in row["entry_names"]
                if entry_map[name]["determines_panel"]
            })
            if not determining:
                assigned = "other_g_protein"
                panels = [assigned]
            elif len(determining) == 1:
                assigned = determining[0]
                panels = determining
            else:
                assigned = "multiple"
                panels = determining
            row.update({
                "transducer_class": assigned,
                "panels": panels,
                "assignment_evidence": "gpcrdb_structural_annotation",
                "annotation_type": annotation.get("type"),
            })
            expected_type = "Arrestin" if set(determining) == {"arrestin"} else "G protein"
            if annotation.get("type") != expected_type:
                conflict = {
                    "code": "gpcrdb_transducer_type_mismatch",
                    "reported_type": annotation.get("type"),
                    "mapped_classes": determining,
                }
                row["source_conflicts"].append(conflict)
                conflicts.append((pdb_id, conflict))
            annotated_counts[assigned] += 1
        else:
            components = rcsb_transducer_components(
                pdb_id, rcsb_entries, transducer_accessions, accession_classes
            )
            row["components"] = components
            row["assignment_evidence"] = "rcsb_polymer_inventory"
            if components:
                determining = sorted({panel for component in components
                                      for panel in component["panel_classes"]})
                if len(determining) == 1:
                    row["transducer_class"] = determining[0]
                    row["panels"] = determining
                elif len(determining) > 1:
                    row["transducer_class"] = "multiple"
                    row["panels"] = determining
                else:
                    row["transducer_class"] = "other_g_protein"
                    row["panels"] = ["other_g_protein"]
                conflict = {"code": "gpcrdb_missing_transducer_annotation"}
                row["source_conflicts"].append(conflict)
                conflicts.append((pdb_id, conflict))
                missing_inventory.append(pdb_id)
            else:
                row["transducer_class"] = "transducer_free"
                row["panels"] = ["transducer_free"]
        rows.append(row)

    if dict(annotated_counts) != EXPECTED_ANNOTATED:
        raise RuntimeError(
            f"annotated distribution differs from plan: actual={dict(annotated_counts)}, "
            f"expected={EXPECTED_ANNOTATED}"
        )
    if sum(1 for row in rows if row["transducer_class"] == "multiple") != 0:
        raise RuntimeError("the plan expects zero multiple-panel structures")
    if len(rows) != 1358:
        raise RuntimeError(f"expected 1358 assignments, found {len(rows)}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                for row in rows),
        encoding="utf-8",
    )
    final_counts = collections.Counter(row["transducer_class"] for row in rows)
    report_lines = [
        "# Enrichment transducer classification", "",
        "## Distribution", "",
        "| Class | Structures |", "|---|---:|",
    ]
    for name in ("Gi/o", "Gs", "Gq/11", "arrestin", "G12/13",
                 "other_g_protein", "transducer_free", "unknown", "multiple"):
        report_lines.append(f"| `{name}` | {final_counts.get(name, 0)} |")
    report_lines += [
        "", "## P1.3 GPCRdb annotation gaps", "",
        f"Of 560 structures without a GPCRdb signalling-protein annotation, "
        f"{final_counts['transducer_free']} contain no polymer with a curated transducer "
        f"UniProt accession and are assigned `transducer_free`; {len(missing_inventory)} "
        "contain a single unambiguous G-alpha class and are assigned from the RCSB "
        "polymer inventory while retaining "
        "`gpcrdb_missing_transducer_annotation`.", "",
    ]
    for pdb_id in missing_inventory:
        row = next(item for item in rows if item["pdb_id"] == pdb_id)
        identities = "; ".join(
            f"{component['description']} ({', '.join(component['uniprot_accessions'])})"
            for component in row["components"]
        )
        report_lines.append(f"- `{pdb_id}`: {identities}")
    report_lines += [
        "", "## UniProt resolution", "",
        "`f6vl43_macmu` was verified as UniProt accession F6VL43, G protein subunit "
        "alpha i3 (GNAI3) from *Macaca mulatta*, and is mapped to `Gi/o`.", "",
        "This resolution changes the plan's pre-run target: structures `8K9K` and "
        "`8K9L` each contain F6VL43 together with GNB1/GNG2, so they are not "
        "beta/gamma-only. Consequently, the scientifically resolved annotated counts are "
        "`Gi/o = 420` and `other_g_protein = 0`, rather than 418 and 2.", "",
        "## Source conflicts", "",
        f"Recorded conflicts: {len(conflicts)} (including the {len(missing_inventory)} "
        "missing-GPCRdb-annotation conflicts listed above).", "",
    ]
    REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    print(json.dumps({
        "rows": len(rows),
        "annotated_distribution": dict(annotated_counts),
        "final_distribution": dict(final_counts),
        "p1_3_rcsb_assigned": missing_inventory,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
