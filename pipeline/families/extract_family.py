#!/usr/bin/env python3
"""Phase 1 — per-family extraction (pilot: Nucleotide, GPCRdb ``001_006``).

Pure projection: every field is copied from the already-built normalized artefacts. The
script performs no fetching and makes no scientific decision, so a family folder can always
be regenerated from the universe without touching the network.

    python3 pipeline/families/extract_family.py --family 001_006
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))

from common.canonical import write_json, content_sha256, PARSER_VERSION   # noqa: E402
from common.http import utc_now                                    # noqa: E402

CFG = json.loads((ROOT / "config/source_endpoints.json").read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="001_006")
    args = ap.parse_args()
    fam = args.family
    out = ROOT / "data/normalized/families" / fam
    out.mkdir(parents=True, exist_ok=True)

    tax = json.loads((ROOT / "data/normalized/class_a_taxonomy.json").read_text(encoding="utf-8"))
    uni = json.loads((ROOT / "data/normalized/class_a_structure_universe.json")
                     .read_text(encoding="utf-8"))
    node = next(n for n in tax["nodes"] if n["source_id"] == fam)
    subfams = [n for n in tax["nodes"] if n.get("parent_source_id") == fam]

    receptors = [r for r in tax["receptors"] if r["major_family_source_id"] == fam]
    structures = [s for s in uni["structures"] if s["major_family_id"] == fam]
    struct_by_entry: dict[str, list[str]] = {}
    for s in structures:
        struct_by_entry.setdefault(s["receptor_entry"], []).append(s["pdb_id"])

    rec_payload = {
        "schema": "receptor.schema.json", "schema_version": "1.0.0",
        "parser_version": PARSER_VERSION, "generated_at": utc_now(),
        "family_source_id": fam, "family_name": node["name"],
        "receptor_families": [{"source_id": n["source_id"], "name": n["name"],
                               "project_slug": n["project_slug"]} for n in subfams],
        "counts": {
            "receptor_records_all_species": len(receptors),
            "human_receptors": sum(1 for r in receptors if r["species"] == "Homo sapiens"),
            "species": len({r["species"] for r in receptors}),
            "receptors_with_structure": len(struct_by_entry),
            "receptor_families": len(subfams),
        },
        "receptors": [dict(r, structure_pdb_ids=sorted(struct_by_entry.get(
            r["receptor_entry_name"], []))) for r in receptors],
    }

    st_payload = {
        "schema": "structure.schema.json", "schema_version": "1.0.0",
        "parser_version": PARSER_VERSION, "generated_at": utc_now(),
        "family_source_id": fam, "family_name": node["name"],
        "counts": {
            "structures": len(structures),
            "flagged": sum(1 for s in structures if s["qc_flags"] != ["ok"]),
            "unresolved": sum(1 for s in structures if s["unresolved"]),
            "distinct_receptors": len(struct_by_entry),
            "distinct_species": len({s["species"] for s in structures}),
        },
        "structures": structures,
    }

    unres = [{"pdb_id": s["pdb_id"], "receptor_entry": s["receptor_entry"],
              "qc_flags": s["qc_flags"]} for s in structures if s["unresolved"]]
    inv_path = out / "component_inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8")) if inv_path.exists() else {}
    for s in inv.get("structures", []):
        if s["qc_flags"] != ["ok"]:
            unres.append({"pdb_id": s["pdb_id"], "receptor_entry": s["receptor_entry"],
                          "qc_flags": s["qc_flags"], "stage": "component_inventory"})

    unres_payload = {
        "schema": "unresolved_record.schema.json", "schema_version": "1.0.0",
        "parser_version": PARSER_VERSION, "generated_at": utc_now(),
        "family_source_id": fam,
        "policy": "A flagged record stays in the raw universe; a flag is a description, "
                  "not an exclusion. Production inclusion is a separate, explicit decision.",
        "counts": {"records": len(unres)},
        "records": unres,
    }

    man_payload = {
        "schema": "source_manifest.schema.json", "schema_version": "1.0.0",
        "parser_version": PARSER_VERSION, "generated_at": utc_now(),
        "family_source_id": fam, "family_name": node["name"],
        "sources": [
            {"provider": "GPCRdb", "role": "taxonomy, receptor records, structure list",
             "base": CFG["gpcrdb"]["base"],
             "license": CFG["gpcrdb"]["terms"], "license_page": CFG["gpcrdb"]["license_page"]},
            {"provider": "RCSB PDB", "role": "entry metadata, entity inventory",
             "base": CFG["rcsb"]["base"],
             "license": CFG["rcsb"]["terms"], "license_page": CFG["rcsb"]["license_page"]},
        ],
        "not_used": CFG.get("not_used_in_phase_1"),
        # Hashes are recomputed from the loaded objects, so a manifest can never claim a
        # provenance chain that its inputs do not actually have.
        "upstream_artifacts": {
            "class_a_taxonomy.json": {"content_sha256": content_sha256(tax)},
            "class_a_structure_universe.json": {"content_sha256": content_sha256(uni)},
        },
        "derivation": [
            "receptors.json  <- class_a_taxonomy.json filtered on major_family_source_id",
            "structures.json <- class_a_structure_universe.json filtered on major_family_id",
            "component_inventory.json <- RCSB entity endpoints, one request per entity id",
        ],
    }

    arts = {
        "receptors.json": write_json(out / "receptors.json", rec_payload),
        "structures.json": write_json(out / "structures.json", st_payload),
        "unresolved_records.json": write_json(out / "unresolved_records.json", unres_payload),
        "source_manifest.json": write_json(out / "source_manifest.json", man_payload),
    }
    print(json.dumps({"family": fam, "name": node["name"],
                      "receptors": rec_payload["counts"], "structures": st_payload["counts"],
                      "unresolved": len(unres), "artifacts": arts}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
