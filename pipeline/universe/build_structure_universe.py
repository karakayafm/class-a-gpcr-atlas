#!/usr/bin/env python3
"""Phase 1 — Class A structure universe.

Two official sources, joined and audited, never silently reconciled:

- GPCRdb ``/services/structure/`` gives the receptor mapping, preferred chain, state and the
  raw signalling-protein annotation.
- RCSB Data API ``/core/entry/{id}`` gives method, resolution, dates, entity identifiers and
  the current/obsolete status.

Nothing is excluded here. Records that fail a check are kept and flagged; production
inclusion is a later, explicit decision.

    python3 pipeline/universe/build_structure_universe.py [--refresh] [--limit N]
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
G, C = CFG["gpcrdb"], CFG["rcsb"]

EXPERIMENTAL_METHODS = {
    "X-RAY DIFFRACTION", "ELECTRON MICROSCOPY", "SOLUTION NMR", "SOLID-STATE NMR",
    "ELECTRON CRYSTALLOGRAPHY", "NEUTRON DIFFRACTION", "FIBER DIFFRACTION",
    "POWDER DIFFRACTION", "SOLUTION SCATTERING",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    tax = json.loads((ROOT / "data/normalized/class_a_taxonomy.json").read_text(encoding="utf-8"))
    by_entry = {r["receptor_entry_name"]: r for r in tax["receptors"]}
    major_name = {n["source_id"]: n["name"] for n in tax["nodes"] if n["level"] == "major_family"}
    rfam_name = {n["source_id"]: n["name"] for n in tax["nodes"] if n["level"] == "receptor_family"}

    gf = Fetcher(ROOT / "data/cache/gpcrdb", "GPCRdb",
                 timeout=G["rate"]["timeout_seconds"], retries=G["rate"]["retries"],
                 delay=0.0, refresh=args.refresh)
    structures = gf.get_json(G["base"] + G["endpoints"]["structure_list"], "structure_list")
    if structures is None:
        print("FATAL: GPCRdb structure list unavailable", file=sys.stderr)
        return 2

    class_a = [s for s in structures if s.get("class") == "Class A (Rhodopsin)"]
    if args.limit:
        class_a = class_a[: args.limit]
    pdb_ids = sorted({str(s["pdb_code"]).upper() for s in class_a})

    rf = Fetcher(ROOT / "data/cache/rcsb", "RCSB PDB",
                 timeout=C["rate"]["timeout_seconds"], retries=C["rate"]["retries"],
                 delay=0.0, refresh=args.refresh)

    def fetch(pid):
        return pid, rf.get_json(C["base"] + C["endpoints"]["entry"].format(pdb_id=pid), f"entry_{pid}")

    entries = {}
    with ThreadPoolExecutor(max_workers=C["rate"]["max_workers"]) as pool:
        for pid, data in pool.map(fetch, pdb_ids):
            entries[pid] = data

    records, unresolved = [], []
    for s in class_a:
        pid = str(s["pdb_code"]).upper()
        e = entries.get(pid)
        entry_name = s.get("protein")
        rec = by_entry.get(entry_name)
        fam_path = str(rec["source_family_path"]) if rec else None
        major = rec["major_family_source_id"] if rec else None
        rfam = rec["receptor_family_source_id"] if rec else None

        flags = []
        if rec is None:
            flags.append("no_receptor_mapping")
        if major is None:
            flags.append("no_family_mapping")
        chain = (s.get("preferred_chain") or "").strip()
        if not chain:
            flags.append("no_receptor_chain")
        if not s.get("species"):
            flags.append("no_species")

        if e is None:
            flags.append("rcsb_unresolved")
            unresolved.append({"pdb_id": pid, "reason": "rcsb_entry_not_retrieved",
                               "gpcrdb_receptor": entry_name})
            method = resolution = dep = rel = None
            method_abbrev = None
            method_full = []
            status = replaced_by = None
            poly_ids = nonpoly_ids = branch_ids = []
            chain_ids = []
            cite_avail = False
        else:
            ei = e.get("rcsb_entry_info") or {}
            acc = e.get("rcsb_accession_info") or {}
            ids = e.get("rcsb_entry_container_identifiers") or {}
            # rcsb_entry_info.experimental_method is an abbreviation ("EM", "X-ray");
            # exptl[].method carries the full controlled vocabulary. Keep both.
            method_full = [m.get("method") for m in (e.get("exptl") or []) if m.get("method")]
            method = (method_full[0].upper() if method_full
                      else ((ei.get("experimental_method") or "").upper() or None))
            method_abbrev = ei.get("experimental_method")
            resolution = (ei.get("resolution_combined") or [None])[0]
            dep, rel = acc.get("deposit_date"), acc.get("initial_release_date")
            st = e.get("pdbx_database_status") or {}
            status = (st.get("status_code") or "").upper() or "REL"
            obs = e.get("pdbx_database_pdb_obs_spr") or []
            replaced_by = [o.get("replace_pdb_id") for o in obs if o.get("replace_pdb_id")] or None
            poly_ids = ids.get("polymer_entity_ids") or []
            nonpoly_ids = ids.get("non_polymer_entity_ids") or []
            branch_ids = ids.get("branched_entity_ids") or []
            chain_ids = ids.get("polymer_entity_ids") or []
            cite_avail = bool([c for c in (e.get("citation") or [])
                               if str(c.get("id", "")).lower() == "primary"])
            if status in {"OBS", "WDRN"}:
                flags.append("pdb_obsolete")
            if method and method not in EXPERIMENTAL_METHODS:
                flags.append("method_not_experimental")
            if not nonpoly_ids:
                flags.append("no_nonpolymer_component")

        records.append({
            "pdb_id": pid,
            "gpcrdb_structure_record": {
                "protein": entry_name, "family_path": fam_path, "species": s.get("species"),
                "preferred_chain": chain or None, "resolution": s.get("resolution"),
                "type": s.get("type"), "state": s.get("state"),
                "publication": s.get("publication"),
                "raw_signalling_protein_annotation": s.get("signalling_protein"),
                "raw_ligand_annotation": s.get("ligands"),
            },
            "receptor_entry": entry_name,
            "receptor_display_name": rec["receptor_display_name"] if rec else None,
            "gene_symbol": rec["gene_symbol"] if rec else None,
            "receptor_family_id": rfam,
            "receptor_family_name": rfam_name.get(rfam),
            "major_family_id": major,
            "major_family_name": major_name.get(major),
            "species": s.get("species"),
            "receptor_chain": chain or None,
            "chain_candidates": chain_ids,
            "experimental_method": method,
            "experimental_method_abbrev": method_abbrev,
            "experimental_methods_all": method_full,
            "nominal_resolution": resolution,
            "deposition_date": dep,
            "release_date": rel,
            "primary_citation_available": cite_avail,
            "transducer_observed_in_structure_raw": s.get("signalling_protein"),
            "functional_pathway_evidence": None,
            "inventory_availability": {
                "polymer_entity_ids": poly_ids,
                "non_polymer_entity_ids": nonpoly_ids,
                "branched_entity_ids": branch_ids,
                "n_polymer_entities": len(poly_ids),
                "n_non_polymer_entities": len(nonpoly_ids),
                "n_branched_entities": len(branch_ids),
            },
            "construct_metadata_available": bool(e and e.get("struct")),
            "pdb_status": status,
            "replacement_pdb_ids": replaced_by,
            "source_urls": {
                "gpcrdb": G["base"] + G["endpoints"]["structure_list"],
                "rcsb": C["base"] + C["endpoints"]["entry"].format(pdb_id=pid),
            },
            "qc_flags": flags or ["ok"],
            "unresolved": bool({"no_receptor_mapping", "no_family_mapping",
                                "rcsb_unresolved", "no_receptor_chain"} & set(flags)),
        })

    universe = {
        "schema": "structure_universe.schema.json", "schema_version": "1.0.0",
        "parser_version": PARSER_VERSION,
        "generated_at": utc_now(),
        "sources": [
            {"provider": "GPCRdb", "endpoint": G["base"] + G["endpoints"]["structure_list"],
             "license": G["terms"], "license_page": G["license_page"]},
            {"provider": "RCSB PDB", "endpoint": C["base"] + "entry/{pdb_id}",
             "license": C["terms"], "license_page": C["license_page"]},
        ],
        "counts": {
            "gpcrdb_class_a_records": len(class_a),
            "distinct_pdb_ids": len(pdb_ids),
            "rcsb_resolved": sum(1 for r in records if "rcsb_unresolved" not in r["qc_flags"]),
            "rcsb_unresolved": sum(1 for r in records if "rcsb_unresolved" in r["qc_flags"]),
            "obsolete": sum(1 for r in records if "pdb_obsolete" in r["qc_flags"]),
            "flagged": sum(1 for r in records if r["qc_flags"] != ["ok"]),
        },
        "structures": records,
    }
    out = write_json(ROOT / "data/normalized/class_a_structure_universe.json", universe)
    write_json(ROOT / "data/normalized/unresolved_records.json",
               {"generated_at": utc_now(), "records": unresolved})
    write_json(ROOT / "data/raw/rcsb/universe_provenance.json",
               {"generated_at": utc_now(),
                "gpcrdb": gf.provenance, "rcsb_request_count": len(rf.provenance),
                "rcsb_failures": [p for p in rf.provenance if not p["success"]]})
    print(json.dumps({"counts": universe["counts"], "artifact": out}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
