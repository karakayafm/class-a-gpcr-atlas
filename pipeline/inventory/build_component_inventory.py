#!/usr/bin/env python3
"""Phase 1 — raw component / polymer inventory.

Two levels, deliberately:

- **Global availability** across the whole Class A universe: for every structure, whether the
  entity identifiers needed for a later inventory are actually retrievable. No chemistry is
  interpreted at this level.
- **Full inventory** for the pilot family only (Nucleotide, GPCRdb ``001_006``): every polymer,
  non-polymer and branched entity is fetched and recorded verbatim.

What this script deliberately does NOT do: decide which component is "the ligand", assign a
pharmacology class, assign a binding-site type, or normalise transducer names. Entities are
typed against ``config/entity_types.json`` only where the source states the fact; anything
requiring judgement is left ``null`` and flagged.

    python3 pipeline/inventory/build_component_inventory.py [--family 001_006] [--refresh]
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))

from common.canonical import write_json, PARSER_VERSION            # noqa: E402
from common.http import Fetcher, utc_now                           # noqa: E402

CFG = json.loads((ROOT / "config/source_endpoints.json").read_text(encoding="utf-8"))
C = CFG["rcsb"]

# Components that are present in almost every deposited structure for reasons that have
# nothing to do with receptor pharmacology. Recorded, never silently dropped.
CRYSTALLISATION_WATER = {"HOH", "DOD"}


def classify_entity(kind: str, rec: dict) -> tuple[str, list[str]]:
    """Map a source record onto config/entity_types.json. Only source-stated facts."""
    flags: list[str] = []
    if kind == "polymer":
        poly = rec.get("entity_poly") or {}
        ptype = (poly.get("rcsb_entity_polymer_type") or "").lower()
        n_res = (rec.get("rcsb_polymer_entity") or {}).get(
            "formula_weight")  # not a length; kept only as a size hint
        if ptype == "protein":
            return "polymer_chain", flags
        if ptype in {"dna", "rna", "na-hybrid"}:
            return "polymer_chain", flags + ["polymer_is_nucleic_acid"]
        flags.append("polymer_type_unrecognised")
        return "unknown", flags
    if kind == "branched":
        return "nonpolymer", flags + ["branched_entity_glycan"]
    comp = (rec.get("rcsb_nonpolymer_entity_container_identifiers") or {})
    ids = comp.get("chem_ref_def_id") or comp.get("nonpolymer_comp_id")
    cid = (ids if isinstance(ids, str) else (ids or [None])[0]) or ""
    if cid.upper() in CRYSTALLISATION_WATER:
        return "nonpolymer", flags + ["component_is_water"]
    return "nonpolymer", flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="001_006", help="pilot major family source id")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    uni = json.loads((ROOT / "data/normalized/class_a_structure_universe.json")
                     .read_text(encoding="utf-8"))
    structures = uni["structures"]

    # ---- level 1: global availability -------------------------------------------------
    availability = []
    for s in structures:
        inv = s["inventory_availability"]
        resolved = "rcsb_unresolved" not in s["qc_flags"]
        availability.append({
            "pdb_id": s["pdb_id"],
            "major_family_id": s["major_family_id"],
            "major_family_name": s["major_family_name"],
            "entity_ids_retrievable": resolved,
            "n_polymer_entities": inv["n_polymer_entities"],
            "n_non_polymer_entities": inv["n_non_polymer_entities"],
            "n_branched_entities": inv["n_branched_entities"],
            "full_inventory_fetched": False,
            "qc_flags": ([] if resolved else ["rcsb_unresolved"])
                        + ([] if inv["n_non_polymer_entities"] else ["no_nonpolymer_component"]),
        })

    # ---- level 2: full inventory for the pilot family ---------------------------------
    pilot = [s for s in structures if s["major_family_id"] == args.family
             and "rcsb_unresolved" not in s["qc_flags"]]
    pilot_skipped = [s["pdb_id"] for s in structures if s["major_family_id"] == args.family
                     and "rcsb_unresolved" in s["qc_flags"]]

    rf = Fetcher(ROOT / "data/cache/rcsb", "RCSB PDB",
                 timeout=C["rate"]["timeout_seconds"], retries=C["rate"]["retries"],
                 delay=0.0, refresh=args.refresh)

    jobs = []
    for s in pilot:
        inv = s["inventory_availability"]
        for eid in inv["polymer_entity_ids"]:
            jobs.append((s["pdb_id"], "polymer", eid))
        for eid in inv["non_polymer_entity_ids"]:
            jobs.append((s["pdb_id"], "nonpolymer", eid))
        for eid in inv["branched_entity_ids"]:
            jobs.append((s["pdb_id"], "branched", eid))

    ep = {"polymer": "polymer_entity", "nonpolymer": "nonpolymer_entity",
          "branched": "branched_entity"}

    def fetch(job):
        pid, kind, eid = job
        url = C["base"] + C["endpoints"][ep[kind]].format(pdb_id=pid, entity_id=eid)
        return job, rf.get_json(url, f"{ep[kind]}_{pid}_{eid}"), url

    fetched: dict[str, list] = {}
    failed = []
    with ThreadPoolExecutor(max_workers=C["rate"]["max_workers"]) as pool:
        for (pid, kind, eid), data, url in pool.map(fetch, jobs):
            if data is None:
                failed.append({"pdb_id": pid, "entity_kind": kind, "entity_id": eid,
                               "url": url, "reason": "entity_not_retrieved"})
                continue
            etype, flags = classify_entity(kind, data)
            if kind == "polymer":
                poly = data.get("entity_poly") or {}
                names = (data.get("rcsb_polymer_entity") or {}).get("pdbx_description")
                ids = (data.get("rcsb_polymer_entity_container_identifiers") or {})
                rec = {
                    "entity_kind": "polymer", "entity_id": str(eid),
                    "entity_type_id": etype,
                    "description": names,
                    "polymer_type": poly.get("rcsb_entity_polymer_type"),
                    "sequence_length": (data.get("entity_poly") or {}).get(
                        "rcsb_sample_sequence_length"),
                    "auth_asym_ids": ids.get("auth_asym_ids") or [],
                    "asym_ids": ids.get("asym_ids") or [],
                    "uniprot_ids": ids.get("uniprot_ids") or [],
                    "component_category": None,
                    "binding_site_type": None,
                    "transducer_class": None,
                    "qc_flags": flags or ["ok"],
                    "source_url": url,
                }
            elif kind == "nonpolymer":
                ids = (data.get("rcsb_nonpolymer_entity_container_identifiers") or {})
                np = (data.get("rcsb_nonpolymer_entity") or {})
                comp = ids.get("nonpolymer_comp_id")
                rec = {
                    "entity_kind": "nonpolymer", "entity_id": str(eid),
                    "entity_type_id": etype,
                    "description": np.get("pdbx_description"),
                    "chem_comp_id": comp if isinstance(comp, str) else (comp or [None])[0],
                    "formula_weight": np.get("formula_weight"),
                    "auth_asym_ids": ids.get("auth_asym_ids") or [],
                    "asym_ids": ids.get("asym_ids") or [],
                    "copies": np.get("pdbx_number_of_molecules"),
                    "component_category": None,
                    "binding_site_type": None,
                    "qc_flags": flags or ["ok"],
                    "source_url": url,
                }
            else:
                ids = (data.get("rcsb_branched_entity_container_identifiers") or {})
                be = (data.get("rcsb_branched_entity") or {})
                rec = {
                    "entity_kind": "branched", "entity_id": str(eid),
                    "entity_type_id": etype,
                    "description": be.get("pdbx_description"),
                    "auth_asym_ids": ids.get("auth_asym_ids") or [],
                    "asym_ids": ids.get("asym_ids") or [],
                    "component_category": None,
                    "binding_site_type": None,
                    "qc_flags": flags or ["ok"],
                    "source_url": url,
                }
            fetched.setdefault(pid, []).append(rec)

    done = set(fetched)
    for a in availability:
        if a["pdb_id"] in done:
            a["full_inventory_fetched"] = True

    pilot_records = []
    for s in pilot:
        ents = sorted(fetched.get(s["pdb_id"], []),
                      key=lambda r: (r["entity_kind"], r["entity_id"]))
        flags = []
        if not ents:
            flags.append("entity_inventory_empty")
        if not [e for e in ents if e["entity_kind"] == "nonpolymer"
                and "component_is_water" not in e["qc_flags"]]:
            flags.append("no_nonpolymer_component")
        pilot_records.append({
            "pdb_id": s["pdb_id"],
            "receptor_entry": s["receptor_entry"],
            "receptor_display_name": s["receptor_display_name"],
            "receptor_family_id": s["receptor_family_id"],
            "species": s["species"],
            "receptor_chain": s["receptor_chain"],
            "entities": ents,
            "n_entities": len(ents),
            "primary_ligand_id": None,          # Phase 2 decision, not made here
            "qc_flags": flags or ["ok"],
        })

    payload_global = {
        "schema": "component_inventory.schema.json", "schema_version": "1.0.0",
        "parser_version": PARSER_VERSION, "generated_at": utc_now(),
        "level": "global_availability",
        "counts": {
            "structures": len(availability),
            "entity_ids_retrievable": sum(1 for a in availability if a["entity_ids_retrievable"]),
            "with_nonpolymer_entity": sum(1 for a in availability
                                          if a["n_non_polymer_entities"] > 0),
            "with_branched_entity": sum(1 for a in availability if a["n_branched_entities"] > 0),
            "full_inventory_fetched": sum(1 for a in availability if a["full_inventory_fetched"]),
        },
        "structures": availability,
    }
    payload_pilot = {
        "schema": "component_inventory.schema.json", "schema_version": "1.0.0",
        "parser_version": PARSER_VERSION, "generated_at": utc_now(),
        "level": "full_inventory", "family_source_id": args.family,
        "counts": {
            "structures": len(pilot_records),
            "structures_skipped_unresolved": len(pilot_skipped),
            "entities": sum(r["n_entities"] for r in pilot_records),
            "polymer": sum(1 for r in pilot_records for e in r["entities"]
                           if e["entity_kind"] == "polymer"),
            "nonpolymer": sum(1 for r in pilot_records for e in r["entities"]
                              if e["entity_kind"] == "nonpolymer"),
            "branched": sum(1 for r in pilot_records for e in r["entities"]
                            if e["entity_kind"] == "branched"),
            "entity_fetch_failures": len(failed),
        },
        "skipped_structures": pilot_skipped,
        "entity_fetch_failures": failed,
        "structures": pilot_records,
    }
    a1 = write_json(ROOT / "data/normalized/component_inventory_availability.json", payload_global)
    a2 = write_json(ROOT / f"data/normalized/families/{args.family}/component_inventory.json",
                    payload_pilot)
    print(json.dumps({"global": payload_global["counts"], "pilot": payload_pilot["counts"],
                      "artifacts": [a1, a2]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
