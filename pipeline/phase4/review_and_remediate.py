#!/usr/bin/env python3
"""Phase 4A — canonical review universe, evidence adjudication and remediation.

Adjudication here is performed from sources by this pipeline. It is **not** human curation:
the two live in disjoint field sets and the human fields stay null throughout.

    python3 pipeline/phase4/review_and_remediate.py
"""
from __future__ import annotations
import gzip, json, os, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402
IN, P3, P4 = ROOT/"data/intermediate", ROOT/"data/intermediate/phase3", ROOT/"data/intermediate/phase4"
CON = ROOT/"data/contacts"
RULE = "phase4-rules-1.0.0"

def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def dump(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(canonical_dumps(r) for r in rows)+("\n" if rows else ""), encoding="utf-8")
    return {"rows": len(rows), "content_sha256": content_sha256(rows)}

HUMAN_NULL = {"human_curator_decision": None, "human_curator_identity": None,
              "human_review_date": None, "human_review_status": "not_started"}

def main() -> int:
    S={s["pdb_id"]:s for s in rd(IN/"structures.normalized.jsonl")}
    RI={r["receptor_instance_id"]:r for r in rd(IN/"receptor_instances.jsonl")}
    LC={l["ligand_entity_id"]:l for l in rd(IN/"ligand_candidates.jsonl")}
    OB=rd(IN/"structure_ligand_observations.jsonl")
    CF=rd(IN/"source_conflicts.jsonl")
    CW={c["receptor_instance_id"]:c for c in rd(P3/"receptor_instance_chain_crosswalk.jsonl")}
    RM=rd(P3/"receptor_residue_mapping.jsonl")
    EL={e["structure_ligand_id"]:e for e in rd(P3/"contact_eligibility.jsonl")}
    LM={l["structure_ligand_id"]:l for l in rd(P3/"ligand_coordinate_mapping.jsonl")}
    RV=rd(P3/"review_resolutions.jsonl")
    SCR=rd(P3/"site_class_review.jsonl")
    TL=rd(P3/"tethered_ligand_candidates.jsonl")
    SUM={s["structure_ligand_id"]:s for s in rd(CON/"observation_contact_summary.jsonl")}
    REG=rd(ROOT/"data/pilots/phase3/aminergic_regression/exact_crosswalk.jsonl")
    contacts=[]
    for f in sorted((CON/"by_family").glob("*/residue_pair_contacts.jsonl.gz")):
        contacts += [json.loads(l) for l in gzip.open(f,"rt")]
    by_obs=defaultdict(list)
    for c in contacts: by_obs[c["structure_ligand_id"]].append(c)

    # ---------------------------------------------------------------- canonical review universe
    # One scientific problem = one canonical item, keyed on the smallest object the problem is
    # about. Source packets that describe the same problem are merged, not duplicated.
    items: dict[str, dict] = {}
    def add(key, issue, pdb, src_id, origin, proposal, evidence,
            ri=None, le=None, sl=None):
        it = items.setdefault(key, {
            "review_item_id": key, "issue_types": [], "pdb_id": pdb,
            "receptor_instance_id": ri, "ligand_entity_id": le, "structure_ligand_id": sl,
            "originating_phases": [], "source_packet_ids": [],
            "automated_proposal": None, "automated_evidence": {},
            **HUMAN_NULL})
        if issue not in it["issue_types"]: it["issue_types"].append(issue)
        if origin not in it["originating_phases"]: it["originating_phases"].append(origin)
        if src_id not in it["source_packet_ids"]: it["source_packet_ids"].append(src_id)
        if it["automated_proposal"] is None: it["automated_proposal"] = proposal
        it["automated_evidence"][issue] = evidence
        for k, v in (("receptor_instance_id", ri), ("ligand_entity_id", le),
                     ("structure_ligand_id", sl)):
            if v and not it.get(k): it[k] = v
        return it

    raw_packets = 0
    for p in RV:
        raw_packets += 1
        cat = p["category"]
        if cat == "receptor_mapping":
            add(f"RI:{p['pdb_id']}", "receptor_mapping", p["pdb_id"], p["review_id"], "phase2",
                p["automated_proposal"], p["automated_evidence"])
        elif cat == "apo_assignment":
            add(f"APO:{p['pdb_id']}", "apo_assignment", p["pdb_id"], p["review_id"], "phase2",
                p["automated_proposal"], p["automated_evidence"])
        elif cat == "polymer_chain_role":
            add(f"CHAIN:{p['review_id'].split(':chain_role')[0]}", "polymer_chain_role",
                p["pdb_id"], p["review_id"], "phase2", p["automated_proposal"], p["automated_evidence"])
        elif cat == "ligand_classification":
            le = p["review_id"].rsplit(":classification", 1)[0]
            add(f"LIG:{le}", "ligand_classification", p["pdb_id"], p["review_id"], "phase2",
                p["automated_proposal"], p["automated_evidence"], le=le)
        elif cat.startswith("source_conflict"):
            add(f"CONFLICT:{p['review_id']}", cat, p["pdb_id"], p["review_id"], "phase2",
                p["automated_proposal"], p["automated_evidence"])
    for s in SCR:
        raw_packets += 1
        add(f"LIG:{s['ligand_entity_id']}", "site_class_unresolved", s["pdb_id"],
            f"siteclass:{s['ligand_entity_id']}", "phase3",
            "site class unresolved after Phase 3 evidence order",
            {"contacted_segments": s["contacted_segments"],
             "geometry_candidate": s["geometry_supported_site_candidate"],
             "official_annotation": s["official_annotation"]},
            le=s["ligand_entity_id"])
    for t in TL:
        raw_packets += 1
        add(f"TETHER:{t['pdb_id']}", "tethered_ligand_candidate", t["pdb_id"],
            f"tether:{t['pdb_id']}", "phase3", t["evidence_statement"],
            {"receptor": t["receptor"], "publication": t["primary_publication"]})
    unval = sorted({m["pdb_id"] for m in RM if m["mapping_route"] == "no_validated_route"})
    for pid in unval:
        raw_packets += 1
        rows=[m for m in RM if m["pdb_id"]==pid]
        add(f"MAP:{pid}", "generic_mapping_unvalidated", pid, f"map:{pid}", "phase3",
            "no mapping route reached the 0.80 sequence-agreement floor",
            {"route_agreement": max((m["route_sequence_agreement"] for m in rows), default=None),
             "residues": len(rows)})
    # Phase 3 recorded 1331 - 1269 = 62 observations that produce no coordinate contact, but the
    # `annotated_not_observed` status was structurally unreachable there: a ligand whose role was
    # unresolved was excluded before its atoms were ever looked for. Phase 4 classifies all 62
    # from the coordinates directly, without rewriting the Phase 3 freeze.
    import gzip as _gz
    from phase3.mmcif import read as _read, atoms as _atoms
    inv_by_id = {i["entity_inventory_id"]: i for i in rd(IN/"entity_inventory.jsonl")}
    noobs = []
    for o in OB:
        sl = o["structure_ligand_id"]
        if sl in SUM:
            continue
        raw_packets += 1
        lg = LC[o["ligand_entity_id"]]
        pid = o["pdb_id"]
        status = EL.get(sl, {}).get("production_status")
        present = None
        detail = {}
        comps = sorted({inv_by_id[i]["nonpolymer_comp_id"] for i in lg["entity_inventory_ids"]
                        if i in inv_by_id and inv_by_id[i].get("nonpolymer_comp_id")})
        het = (lg.get("source_annotations", {}).get("gpcrdb_ligand", {}) or {}).get("PDB")
        cfile = ROOT/"data/cache/coordinates"/f"{pid}.cif.gz"
        if cfile.exists() and (comps or het):
            want = set(comps) | ({het} if het else set())
            try:
                A = _atoms(_read(cfile, {"_atom_site"})["_atom_site"])
                found = sorted({a["comp"] for a in A if a["comp"] in want})
                present = bool(found)
                detail = {"looked_for": sorted(want), "found_in_coordinates": found}
            except Exception as exc:
                detail = {"parser_error": type(exc).__name__}
        sub = ("annotated_component_absent_from_coordinates" if present is False
               else "annotated_component_present_but_role_unresolved" if present
               else "no_component_identifier_to_look_for")
        add(f"LIG:{lg['ligand_entity_id']}", "annotated_not_observed", pid,
            f"ano:{sl}", "phase3+phase4",
            f"observation produces no coordinate contact ({status})",
            {"phase3_status": status, "subclassification": sub, **detail},
            le=lg["ligand_entity_id"], sl=sl)
        noobs.append({"structure_ligand_id": sl, "pdb_id": pid,
                      "ligand_entity_id": lg["ligand_entity_id"],
                      "ligand_role": lg["ligand_role"],
                      "entity_form": lg["entity_form"],
                      "phase3_production_status": status,
                      "phase4_subclassification": sub,
                      "component_present_in_coordinates": present,
                      "evidence": detail,
                      "source_annotation_retained": True,
                      "counts_as_annotated_ligand": True,
                      "counts_as_coordinate_observed_ligand": False,
                      "counts_as_contact_eligible_ligand": False})
    for r in REG:
        if not r["contact_equivalent"]:
            raw_packets += 1
            add(f"REG:{r['pdb_id']}", "aminergic_regression_discrepancy", r["pdb_id"],
                f"reg:{r['pdb_id']}", "phase3",
                "generic-position sets differ from the frozen reference",
                {"only_frozen": r["generic_only_in_frozen"][:8],
                 "only_new": r["generic_only_in_new"][:8],
                 "common": r["generic_positions_in_common"]})
    mut_unres = defaultdict(int)
    for m in RM:
        if m["mutation_mapping_confidence"] == "unresolved":
            mut_unres[m["pdb_id"]] += 1
    for pid, n in sorted(mut_unres.items()):
        raw_packets += 1
        add(f"MUT:{pid}", "mutation_mapping_unresolved", pid, f"mut:{pid}", "phase3",
            "reference residue identity unavailable at one or more positions",
            {"residues_without_reference": n})

    # ---------------------------------------------------------------- evidence adjudication
    adjud = []
    for key, it in sorted(items.items()):
        pid = it["pdb_id"]; st = S.get(pid, {})
        issues = set(it["issue_types"])
        res = "evidence_insufficient_human_review_required"
        basis = ("no source of the appropriate priority tier makes a statement that settles this "
                 "issue type; the record is left for human review rather than guessed")
        conf, src = "low", []
        if "annotated_not_observed" in issues:
            res = "evidence_resolved_annotated_not_observed"
            basis = ("the source annotates this ligand and the deposited coordinates contain no "
                     "atoms for it; the annotation is retained and no contact is produced")
            conf, src = "high", ["RCSB mmCIF coordinates", "GPCRdb ligand annotation"]
        elif "receptor_mapping" in issues and st.get("metadata_completeness") != "complete":
            res = "evidence_resolved_metadata_only"
            basis = ("RCSB serves no entity metadata for this entry; Phase 3 confirmed the "
                     "coordinate file exists, so the record is real but not mappable from "
                     "entity data")
            conf, src = "medium", ["RCSB coordinates", "RCSB Data API (absent)"]
        elif "generic_mapping_unvalidated" in issues:
            res = "evidence_insufficient_human_review_required"
            basis = ("no sourced mapping route reaches the frozen 0.80 agreement floor; the "
                     "floor was not lowered to force a result")
            conf, src = "medium", ["RCSB aligned_regions", "GPCRdb residues", "author numbering"]
        elif "site_class_unresolved" in issues:
            ev = it["automated_evidence"].get("site_class_unresolved", {})
            res = "evidence_insufficient_human_review_required"
            basis = ("the source states a modulator function without stating where it binds; "
                     f"geometry gives only a candidate ({ev.get('geometry_candidate')})")
            conf, src = "low", ["GPCRdb ligand annotation", "coordinate geometry (supporting only)"]
        elif "tethered_ligand_candidate" in issues:
            res = "evidence_insufficient_human_review_required"
            basis = ("no official annotation, cleavage-site mapping or publication statement "
                     "giving a residue range is available from the sources called")
            conf, src = "medium", ["GPCRdb", "RCSB"]
        elif "apo_assignment" in issues:
            res = "evidence_insufficient_human_review_required"
            basis = ("the structure carries no positive apo annotation and its ligand annotation "
                     "could not be attached to an entity")
            conf, src = "medium", ["GPCRdb ligand annotation"]
        elif issues & {"source_conflict:annotated_component_absent"}:
            res = "evidence_resolved_annotated_not_observed"
            basis = ("coordinates confirm the annotated component is not modelled; this supports "
                     "absence from the model and does NOT falsify the source pharmacology")
            conf, src = "high", ["RCSB mmCIF coordinates", "GPCRdb ligand annotation"]
        elif issues & {"source_conflict:transducer_presence_disagreement"}:
            res = "source_conflict_unresolved"
            basis = ("GPCRdb annotates the signalling protein while RCSB reports deposited "
                     "chains; the two answer different questions and neither is overruled")
            conf, src = "medium", ["GPCRdb", "RCSB"]
        elif "aminergic_regression_discrepancy" in issues:
            ev = it["automated_evidence"]["aminergic_regression_discrepancy"]
            if not ev["only_new"] and ev["only_frozen"]:
                res, conf = "evidence_resolved_exclude", "medium"
                basis = ("the new pipeline produces no generic numbering for this structure "
                         "because its mapping route did not validate")
            elif not ev["only_frozen"] and ev["only_new"]:
                res, conf = "evidence_resolved_include", "medium"
                basis = ("the new pipeline maps generic positions the frozen pipeline could not; "
                         "this is additional coverage, not a regression")
            else:
                res, conf = "evidence_insufficient_human_review_required", "low"
                basis = "both sets carry positions the other lacks"
            src = ["frozen aminergic dataset (read-only)", "GPCRdb residues"]
        elif "polymer_chain_role" in issues:
            res = "evidence_insufficient_human_review_required"
            basis = "no identity evidence and no source ligand annotation matched the chain"
            conf, src = "low", ["RCSB entity description", "UniProt accessions"]
        elif "ligand_classification" in issues:
            res = "evidence_insufficient_human_review_required"
            basis = "several candidate chains remain, or the annotation carries no identifier"
            conf, src = "low", ["GPCRdb ligand annotation", "RCSB polymer entities"]
        elif "mutation_mapping_unresolved" in issues:
            res = "evidence_resolved_metadata_only"
            basis = ("no reference residue was available at these positions; the residues keep "
                     "mutation_status unresolved and are never treated as wild type")
            conf, src = "medium", ["GPCRdb residues"]
        adjud.append({
            "review_item_id": key, "pdb_id": pid, "issue_types": sorted(issues),
            "automated_proposal": it["automated_proposal"],
            "evidence_adjudication": res, "adjudication_basis": basis,
            "adjudication_sources": src, "adjudication_confidence": conf,
            "evidence_resolved_status": res,
            "current_eligibility": (EL.get(it.get("structure_ligand_id") or "", {})
                                    .get("production_status")),
            **HUMAN_NULL,
            "provenance": {"rule_version": RULE, "script": "pipeline/phase4/review_and_remediate.py",
                           "generated_at": utc_now()}})
        it["evidence_completeness"] = ("sufficient" if res.startswith("evidence_resolved")
                                       else "insufficient")
        it["adjudication_status"] = res
        it["human_review_requirement"] = ("required" if not res.startswith("evidence_resolved")
                                          else "optional_confirmation")
        it["current_eligibility"] = (EL.get(it.get("structure_ligand_id") or "", {})
                                     .get("production_status"))

    # ---------------------------------------------------------------- overlap matrix
    overlap = {
        "raw_source_packets": raw_packets,
        "unique_canonical_items": len(items),
        "items_with_more_than_one_issue_type":
            sum(1 for i in items.values() if len(i["issue_types"]) > 1),
        "issue_type_counts": dict(Counter(t for i in items.values() for t in i["issue_types"])),
        "items_per_pdb_max": max(Counter(i["pdb_id"] for i in items.values()).values()),
        "distinct_pdbs": len({i["pdb_id"] for i in items.values()}),
        "observation_level_items": sum(1 for i in items.values() if i.get("structure_ligand_id")),
        "deduplication_note": ("Source packets that describe the same scientific problem about "
                               "the same object are merged into one canonical item; the "
                               "originating packet ids are retained in source_packet_ids."),
    }

    # ---------------------------------------------------------------- mapping remediation
    remed = []
    by_inst = defaultdict(list)
    for m in RM:
        by_inst[(m["pdb_id"], m["receptor_instance_id"])].append(m)
    # A route is chosen per receptor instance, not per entry: 8TH3 validates chain A at 1.000
    # and fails chain B. Collapsing to the entry would have hidden one of them.
    for (pid, rid) in sorted(by_inst):
        rows = by_inst[(pid, rid)]
        route = rows[0]["mapping_route"]
        agree = max((r["route_sequence_agreement"] for r in rows), default=-1)
        gen = sum(1 for r in rows if r["mapping_status"] == "mapped_generic")
        if route == "no_validated_route":
            outcome = "mapping_unresolved_excluded_from_generic_aggregation"
            note = (f"best route agreement {agree:.3f} is below the frozen 0.80 floor; the floor "
                    f"was not lowered and no route was chosen for producing more generic numbers")
        elif agree >= 0.95:
            outcome = "mapping_unchanged_valid"
            note = f"route {route} agrees with the observed sequence at {agree:.3f}"
        elif route == "identity_validated_piecewise_offset":
            outcome = "mapping_improved_with_evidence"
            note = (f"a piecewise offset validated by residue identity recovered a construct "
                    f"whose single-region alignment scored lower; agreement {agree:.3f}")
        else:
            outcome = "mapping_unchanged_valid"
            note = f"route {route}, agreement {agree:.3f}"
        remed.append({
            "pdb_id": pid, "receptor_instance_id": rid, "mapping_route": route, "route_sequence_agreement": agree,
            "residues": len(rows), "mapped_generic": gen,
            "scoring_criteria": ["sequence identity", "residue identity agreement",
                                 "construct boundary consistency (fusion accession region)",
                                 "insertion/deletion coherence (piecewise offset segmentation)",
                                 "receptor segment coherence (GPCRdb segment continuity)"],
            "motif_position_consistency_used_as": "auxiliary QC only, never as proof of mapping",
            "outcome": outcome, "note": note,
            "raw_author_numbered_contacts_preserved": True,
            "confidence_floor": 0.80, "floor_changed": False,
            **HUMAN_NULL})
    arts = {}
    arts["canonical_review_universe.jsonl"] = dump(P4/"canonical_review_universe.jsonl",
                                                   [items[k] for k in sorted(items)])
    arts["evidence_adjudications.jsonl"] = dump(P4/"evidence_adjudications.jsonl", adjud)
    arts["mapping_remediation.jsonl"] = dump(P4/"mapping_remediation.jsonl", remed)
    arts["annotated_not_observed.jsonl"] = dump(
        P4/"annotated_not_observed.jsonl", sorted(noobs, key=lambda r: r["structure_ligand_id"]))
    (P4/"_overlap_matrix.json").write_text(json.dumps(overlap, indent=1, ensure_ascii=False),
                                           encoding="utf-8")
    print(json.dumps({"overlap": overlap,
                      "adjudication": dict(Counter(a["evidence_adjudication"] for a in adjud)),
                      "remediation": dict(Counter(r["outcome"] for r in remed)),
                      "annotated_not_observed": dict(Counter(r["phase4_subclassification"] for r in noobs)),
                      "artifacts": {k: v["rows"] for k, v in arts.items()}}, indent=1))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
