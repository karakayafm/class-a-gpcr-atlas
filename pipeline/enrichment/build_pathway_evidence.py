#!/usr/bin/env python3
"""E2: build separate structural (A) and curated functional (B) evidence."""
from __future__ import annotations

import collections
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSIGNMENTS = ROOT / "data/intermediate/enrichment/transducer_assignments.jsonl"
UNIVERSE = ROOT / "data/normalized/class_a_structure_universe.json"
CURATION = ROOT / "curation/pathway_evidence/pathway_evidence.csv"
TIERS = ROOT / "config/enrichment/evidence_tiers.json"
ENTRY_MAP = ROOT / "config/enrichment/transducer_entry_map.json"
SCHEMA = ROOT / "schemas/enrichment/pathway_evidence.schema.json"
OUTPUT = ROOT / "data/intermediate/enrichment/pathway_evidence.jsonl"
REPORT = ROOT / "reports/enrichment_pathway.md"

PATHWAY_MAP = {"Gi": "Gi/o", "beta_arrestin": "arrestin"}
PANEL_FOR_PATHWAY = {
    "Gs": "Gs", "Gi/o": "Gi/o", "Gq/11": "Gq/11", "G12/13": "G12/13",
    "arrestin": "arrestin", "no_transducer": "transducer_free",
}
# Family wording, used when the deposited chain has no standard display name of its own.
FAMILY_LABEL = {
    "Gs": "Gs", "Gi/o": "Gi/o", "Gq/11": "Gq/11", "G12/13": "G12/13", "arrestin": "arrestin",
}


def presence_rationale(panel: str, entry_names, entry_map) -> tuple[str, str]:
    """Name the subunit actually deposited in the structure rather than listing the whole family.

    Only the standard names carry a `display` value in the entry map; transducin, gustducin, Gz,
    Golf and visual arrestin deliberately have none, and those structures fall back to the family
    label. Falling back is not a loss: the exact chain stays in `transducer_assignments.jsonl`
    and in the entry map with its UniProt accession.
    """
    labels, complete = [], True
    for name in entry_names or []:
        info = entry_map.get(name) or {}
        if not info.get("determines_panel"):
            continue
        display = info.get("display")
        if not display:
            complete = False
            break
        if display not in labels:
            labels.append(display)
    if complete and labels:
        label = " + ".join(labels)
        return (f"yapıda {label} ileticisi var", f"the structure contains a {label} transducer")
    # Say "from the X family" rather than naming a subunit we chose not to display — writing
    # "Gαs" for a Gαolf chain would be wrong, and the fallback must not imply a wrong identity.
    family = FAMILY_LABEL[panel]
    return (f"yapıda {family} ailesinden bir iletici var",
            f"the structure contains a transducer from the {family} family")


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def type_matches(value: object, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "string": isinstance(value, str),
        "null": value is None,
        "boolean": isinstance(value, bool),
    }.get(expected, True)


def validate_record(record: dict, schema: dict, context: str) -> None:
    """Validate the JSON-Schema subset used by the E2 row contracts."""
    missing = [name for name in schema.get("required", []) if name not in record]
    if missing:
        raise ValueError(f"{context}: missing required fields {missing}")
    properties = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = sorted(set(record) - set(properties))
        if extra:
            raise ValueError(f"{context}: unexpected fields {extra}")
    for name, rule in properties.items():
        if name not in record:
            continue
        value = record[name]
        expected = rule.get("type")
        if expected:
            options = expected if isinstance(expected, list) else [expected]
            if not any(type_matches(value, option) for option in options):
                raise ValueError(f"{context}.{name}: invalid type")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"{context}.{name}: {value!r} not in enum")
        if "const" in rule and value != rule["const"]:
            raise ValueError(f"{context}.{name}: expected {rule['const']!r}")
        if isinstance(value, str) and len(value) < rule.get("minLength", 0):
            raise ValueError(f"{context}.{name}: string is too short")
        if isinstance(value, str) and rule.get("pattern") and not re.search(rule["pattern"], value):
            raise ValueError(f"{context}.{name}: does not match {rule['pattern']}")
        if isinstance(value, dict) and rule.get("properties"):
            validate_record(value, rule, f"{context}.{name}")


def validate_output(record: dict, schema: dict, context: str) -> None:
    validate_record(record, schema, context)
    if record["tier"] == "A":
        if record["functional_evidence"] is not None or not record["assignment_evidence"]:
            raise ValueError(f"{context}: tier A must have assignment evidence only")
    elif record["tier"] == "B":
        if not isinstance(record["functional_evidence"], dict) or record["assignment_evidence"] is not None:
            raise ValueError(f"{context}: tier B must have functional evidence only")


def ligand_ids(structure: dict) -> set[str]:
    return {
        ligand["PDB"].upper()
        for ligand in ((structure.get("gpcrdb_structure_record") or {})
                       .get("raw_ligand_annotation") or [])
        if ligand.get("PDB")
    }


def main() -> int:
    assignments = load_jsonl(ASSIGNMENTS)
    structures = json.loads(UNIVERSE.read_text(encoding="utf-8"))["structures"]
    structure_by_pdb = {structure["pdb_id"]: structure for structure in structures}
    tiers = json.loads(TIERS.read_text(encoding="utf-8"))["tiers"]
    entry_map_doc = json.loads(ENTRY_MAP.read_text(encoding="utf-8"))
    entry_map = entry_map_doc.get("entries", entry_map_doc)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    rows = []
    for assignment in assignments:
        pdb_id = assignment["pdb_id"]
        structure = structure_by_pdb[pdb_id]
        receptor = (structure.get("gene_symbol") or structure["receptor_entry"]).upper()
        for panel in assignment["panels"]:
            if panel == "transducer_free":
                pathway = "no_transducer"
                result = "structural_absence"
                rationale_tr = "yapıda iletici yok — çökeltilmiş polimer envanterinde G proteini veya arrestin bulunmuyor"
                rationale_en = "no transducer in the structure — the deposited polymer inventory contains no G protein or arrestin"
            else:
                pathway = panel
                result = "structural_presence"
                rationale_tr, rationale_en = presence_rationale(
                    pathway, assignment.get("entry_names"), entry_map)
            row = {
                "evidence_id": f"A:{pdb_id}:{pathway}",
                "pdb_id": pdb_id,
                "receptor": receptor,
                "canonical_ligand_id": None,
                "pathway": pathway,
                "panel": PANEL_FOR_PATHWAY[pathway],
                "tier": "A",
                "tier_label_tr": tiers["A"]["label_tr"],
                "tier_label_en": tiers["A"]["label_en"],
                "result": result,
                "rationale_tr": rationale_tr,
                "rationale_en": rationale_en,
                "source": {
                    "provider": "RCSB PDB" if assignment["assignment_evidence"] == "rcsb_polymer_inventory" else "GPCRdb / RCSB PDB",
                    "url": f"https://www.rcsb.org/structure/{pdb_id}",
                    "reference_id": None,
                },
                "panel_membership": True,
                "assignment_evidence": assignment["assignment_evidence"],
                "functional_evidence": None,
            }
            validate_output(row, schema, row["evidence_id"])
            rows.append(row)

    atlas_index = collections.defaultdict(set)
    for structure in structures:
        receptor = (structure.get("gene_symbol") or "").upper()
        for ligand_id in ligand_ids(structure):
            atlas_index[(receptor, ligand_id)].add(structure["pdb_id"])

    with CURATION.open(newline="", encoding="utf-8") as handle:
        curated_rows = list(csv.DictReader(handle))
    if len(curated_rows) != 22:
        raise RuntimeError(f"expected the 22 source curation rows, found {len(curated_rows)}")

    unmatched = []
    b_matches = collections.Counter()
    for index, curated in enumerate(curated_rows, start=1):
        validate_record(curated, schema["$defs"]["curation_row"], f"CSV row {index}")
        receptor = curated["receptor"].upper()
        ligand_id = curated["canonical_ligand_id"].upper()
        pathway = PATHWAY_MAP.get(curated["pathway"], curated["pathway"])
        candidates = set(atlas_index[(receptor, ligand_id)])
        if curated["pdb_id"]:
            candidates &= {curated["pdb_id"].upper()}
        if not candidates:
            unmatched.append(index)
            continue
        for pdb_id in sorted(candidates):
            result = curated["result"]
            row = {
                "evidence_id": stable_id("B", str(index), pdb_id, receptor, ligand_id, pathway, result),
                "pdb_id": pdb_id,
                "receptor": receptor,
                "canonical_ligand_id": ligand_id,
                "pathway": pathway,
                "panel": PANEL_FOR_PATHWAY[pathway],
                "tier": "B",
                "tier_label_tr": tiers["B"]["label_tr"],
                "tier_label_en": tiers["B"]["label_en"],
                "result": result,
                "rationale_tr": curated["assay_or_evidence"],
                "rationale_en": curated["assay_or_evidence"],
                "source": {
                    "provider": "curated literature",
                    "url": curated["source_url"],
                    "reference_id": curated["reference_id"],
                },
                "panel_membership": result != "negative",
                "assignment_evidence": None,
                "functional_evidence": dict(curated),
            }
            validate_output(row, schema, row["evidence_id"])
            rows.append(row)
            b_matches[pdb_id] += 1

    if unmatched:
        raise RuntimeError(f"curation rows did not match the atlas: {unmatched}")
    a_pdbs = {row["pdb_id"] for row in rows if row["tier"] == "A"}
    if a_pdbs != set(structure_by_pdb):
        raise RuntimeError(f"tier-A coverage mismatch: {len(a_pdbs)} of {len(structure_by_pdb)}")
    if len(b_matches) < 3 or "6MXT" not in b_matches:
        raise RuntimeError(f"insufficient tier-B atlas coverage: {sorted(b_matches)}")
    if not any(row["tier"] == "B" and row["result"] == "negative"
               and not row["panel_membership"] for row in rows):
        raise RuntimeError("negative tier-B evidence is missing or grants panel membership")

    rows.sort(key=lambda row: (row["pdb_id"], row["tier"], row["pathway"], row["evidence_id"]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
                for row in rows),
        encoding="utf-8",
    )
    tier_counts = collections.Counter(row["tier"] for row in rows)
    result_counts = collections.Counter(row["result"] for row in rows if row["tier"] == "B")
    REPORT.write_text("\n".join([
        "# Enrichment pathway evidence", "",
        f"Tier A contains {tier_counts['A']} records and covers all {len(a_pdbs)} structures. "
        f"Tier B contains {tier_counts['B']} expanded structure-level records from exactly "
        f"{len(curated_rows)} source-linked curation rows and reaches {len(b_matches)} atlas structures.", "",
        "## Tier-B results", "", "| Result | Records |", "|---|---:|",
        *[f"| `{name}` | {result_counts[name]} |" for name in sorted(result_counts)],
        "", "Negative results remain in the evidence output with `panel_membership: false`. "
        "No functional evidence was inferred for uncovered receptor-ligand pairs.", "",
        "## Matched structures", "", ", ".join(f"`{pdb}`" for pdb in sorted(b_matches)), "",
    ]), encoding="utf-8")
    print(json.dumps({
        "records": len(rows), "tier_counts": dict(tier_counts),
        "curation_rows": len(curated_rows), "tier_b_structures": len(b_matches),
        "tier_b_results": dict(result_counts),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
