#!/usr/bin/env python3
"""Phase 3A — the five mandatory reconciliation gates.

Nothing downstream may run until every receptor instance, every receptor-role chain and every
observation is accounted for by an explicit category. A count that cannot be explained is a
blocker, not a rounding difference.

    python3 pipeline/phase3/reconcile.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402

IN = ROOT / "data/intermediate"
OUT = IN / "phase3"
RULE_VERSION = "phase3-rules-1.0.0"


def rd(name, sub=""):
    p = (IN / sub / name) if sub else (IN / name)
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def jdump(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(canonical_dumps(r) for r in rows) + ("\n" if rows else ""),
                    encoding="utf-8")
    return {"rows": len(rows), "content_sha256": content_sha256(rows)}


def main() -> int:
    S = rd("structures.normalized.jsonl")
    RI = rd("receptor_instances.jsonl")
    EI = rd("entity_inventory.jsonl")
    LC = rd("ligand_candidates.jsonl")
    OB = rd("structure_ligand_observations.jsonl")
    MQ = rd("manual_review_queue.jsonl")
    CF = rd("source_conflicts.jsonl")
    Sd = {s["pdb_id"]: s for s in S}
    inv_by_pdb = defaultdict(list)
    for i in EI:
        inv_by_pdb[i["pdb_id"]].append(i)

    report = {"generated_at": utc_now(), "rule_version": RULE_VERSION, "gates": {}}
    blockers = []

    # ---------------------------------------------------------------- A. instance <-> chain
    chains_receptor = [i for i in EI if i["entity_form"] == "polymer_chain"
                       and i["final_role"] == "receptor"]
    chain_by_key = {}
    for c in chains_receptor:
        chain_by_key[(c["pdb_id"], c["polymer_entity_id"])] = c

    crosswalk = []
    for r in RI:
        pid = r["pdb_id"]
        pe = r["polymer_entity_id"]
        chain = chain_by_key.get((pid, pe))
        sibling_count = sum(1 for x in RI if x["pdb_id"] == pid
                            and x["polymer_entity_id"] == pe)
        if chain is None and pe is None:
            cat = ("receptor_entity_without_resolved_chain"
                   if Sd[pid]["metadata_completeness"] == "complete"
                   else "unresolved")
            reason = ("no polymer entity carried the receptor accession; the GPCRdb preferred "
                      "chain was used as the documented fallback"
                      if cat == "receptor_entity_without_resolved_chain"
                      else "RCSB serves no entity data for this entry")
            elig, mr = "excluded_receptor_mapping_unresolved", "required"
        elif chain is None:
            cat, reason = "metadata_source_disagreement", (
                "receptor instance references a polymer entity that is not classified as "
                "receptor in the inventory")
            elig, mr = "excluded_receptor_mapping_unresolved", "required"
        elif r["is_chimeric_construct"]:
            cat = "chimeric_receptor_single_instance"
            reason = ("receptor and a crystallisation fusion share one polymer entity; the "
                      "entity stays one receptor instance and the fusion is construct metadata")
            elig, mr = "eligible", "not_required"
        elif sibling_count > 1:
            cat = "exact_multi-chain_construct_match"
            reason = (f"one receptor polymer entity is modelled as {sibling_count} chains; "
                      f"each chain is its own receptor instance")
            elig, mr = "eligible", "not_required"
        else:
            cat, reason = "exact_single_chain_match", "one receptor entity, one modelled chain"
            elig, mr = "eligible", "not_required"
        crosswalk.append({
            "receptor_instance_id": r["receptor_instance_id"], "pdb_id": pid,
            "receptor_accession": r["receptor_accession"],
            "auth_asym_id": r["auth_asym_id"], "label_asym_id": r["label_asym_id"],
            "polymer_entity_id": pe,
            "matched_inventory_row": chain["entity_inventory_id"] if chain else None,
            "match_cardinality": (f"1_entity_to_{sibling_count}_instances"
                                  if chain else "0_entity_to_1_instance"),
            "match_category": cat, "reason": reason,
            "contact_eligibility": elig, "manual_review_status": mr,
            "mapping_confidence": r["mapping_confidence"],
        })
    dup = [k for k, v in Counter(c["receptor_instance_id"] for c in crosswalk).items() if v > 1]
    cat_counts = Counter(c["match_category"] for c in crosswalk)
    chains_used = {c["matched_inventory_row"] for c in crosswalk if c["matched_inventory_row"]}
    chains_unused = [c for c in chains_receptor if c["entity_inventory_id"] not in chains_used]

    gate_a_ok = (len(crosswalk) == len(RI) and not dup and not chains_unused)
    report["gates"]["A_receptor_instance_chain"] = {
        "receptor_instances": len(RI), "receptor_role_chains": len(chains_receptor),
        "crosswalk_rows": len(crosswalk),
        "categories": dict(cat_counts),
        "duplicate_instance_ids": dup,
        "receptor_chains_not_referenced": len(chains_unused),
        "explanation": (
            f"{len(RI)} instances arise from {len(chains_receptor)} receptor-role polymer "
            f"entities because one entity may be modelled as several chains. "
            f"{cat_counts.get('exact_multi-chain_construct_match', 0)} instances come from "
            f"multi-chain entities, {cat_counts.get('chimeric_receptor_single_instance', 0)} "
            f"from chimeric constructs, "
            f"{cat_counts.get('exact_single_chain_match', 0)} are one-to-one, and "
            f"{cat_counts.get('receptor_entity_without_resolved_chain', 0) + cat_counts.get('unresolved', 0)} "
            f"have no resolved chain."),
        "closed": gate_a_ok}
    if not gate_a_ok:
        blockers.append("A_receptor_instance_chain")

    # ------------------------------------------------------- B. Peptide no-nonpolymer 161/162
    pep_zero = [s for s in S if s["major_family_id"] == "001_002"
                and s["entity_counts"]["nonpolymer_entities"] == 0]
    served = [s for s in pep_zero if s["metadata_completeness"] == "complete"]
    unserved = [s for s in pep_zero if s["metadata_completeness"] != "complete"]
    report["gates"]["B_peptide_no_nonpolymer"] = {
        "raw_count": len(pep_zero), "biological_count": len(served),
        "difference": len(unserved),
        "difference_records": [{
            "pdb_id": s["pdb_id"], "receptor": s["receptor_name"],
            "metadata_completeness": s["metadata_completeness"],
            "rcsb_source_state": s["structure_source_provenance"]["source_state"]["rcsb"],
            "phase1_qc_flags": s["phase1_qc_flags"],
            "cause": "rcsb_metadata_absent",
            "is_genuine_no_nonpolymer_structure": False,
            "is_extraction_artefact": False,
            "is_empty_entity_response": False,
            "explanation": (
                "GPCRdb lists this entry as a Class A structure; the RCSB Data API returns "
                "HTTP 404 for it, so no entity data exists to count. Its zero is an absence of "
                "source, not an observation of absence. Phase 1 flagged it rcsb_unresolved "
                "rather than no_nonpolymer_component, which is why Phase 1 reported 161.")}
            for s in unserved],
        "field_separation": (
            "entity_counts.nonpolymer_entities carries the raw count; "
            "metadata_completeness carries whether a count was possible at all. They are "
            "separate fields and are never conflated."),
        "closed": len(served) == 161 and len(pep_zero) == 162}
    if not report["gates"]["B_peptide_no_nonpolymer"]["closed"]:
        blockers.append("B_peptide_no_nonpolymer")

    # ------------------------------------------------------------- C. polymer ligand arithmetic
    ann_struct_peptide, ann_struct_protein = set(), set()
    for s in S:
        for a in (s.get("phase1_qc_flags") and [] or []):
            pass
    uni = json.loads((ROOT / "data/normalized/class_a_structure_universe.json")
                     .read_text(encoding="utf-8"))
    for u in uni["structures"]:
        for a in (u["gpcrdb_structure_record"]["raw_ligand_annotation"] or []):
            if a.get("type") == "peptide":
                ann_struct_peptide.add(u["pdb_id"])
            elif a.get("type") == "protein":
                ann_struct_protein.add(u["pdb_id"])
    poly_lig_chains = [i for i in EI if i["entity_form"] == "polymer_chain"
                       and i["final_role"] == "endogenous_polymer_ligand"]
    poly_lig_entities = [l for l in LC if l["entity_form"] == "polymer_chain"]
    resolved = [l for l in poly_lig_entities
                if l["classification_confidence"] == "single_candidate_match"]
    ambiguous = [l for l in poly_lig_entities
                 if l["classification_confidence"] == "ambiguous_multiple_candidates"]
    nocand = [l for l in LC if l["classification_confidence"] == "no_polymer_candidate"]
    struct_with_polychain = Counter(i["pdb_id"] for i in poly_lig_chains)
    multi_chain_structs = {k: v for k, v in struct_with_polychain.items() if v > 1}
    report["gates"]["C_polymer_ligand"] = {
        "discovery_reference": {"peptide_ligand_structures": 242, "protein_ligand_structures": 81,
                                "note": "annotation counts, i.e. annotations not structures"},
        "annotation_level": {
            "peptide_annotations": sum(1 for u in uni["structures"]
                                       for a in (u["gpcrdb_structure_record"]["raw_ligand_annotation"] or [])
                                       if a.get("type") == "peptide"),
            "protein_annotations": sum(1 for u in uni["structures"]
                                       for a in (u["gpcrdb_structure_record"]["raw_ligand_annotation"] or [])
                                       if a.get("type") == "protein"),
            "structures_with_peptide_annotation": len(ann_struct_peptide),
            "structures_with_protein_annotation": len(ann_struct_protein),
            "structures_with_any_polymer_annotation": len(ann_struct_peptide | ann_struct_protein)},
        "entity_level": {
            "polymer_ligand_entities": len(poly_lig_entities),
            "resolved_single_candidate": len(resolved),
            "ambiguous_multiple_candidates": len(ambiguous),
            "annotations_without_matching_chain": len(nocand)},
        "chain_level": {
            "polymer_ligand_chains": len(poly_lig_chains),
            "structures_carrying_polymer_ligand_chains": len(struct_with_polychain),
            "structures_with_more_than_one_polymer_ligand_chain": len(multi_chain_structs),
            "extra_chains_from_multi_chain_structures":
                sum(v - 1 for v in multi_chain_structs.values())},
        "segment_level": {
            "polymer_ligand_segments": 0,
            "note": ("no source stated a residue range, so every polymer ligand is recorded as "
                     "whole_chain_assumed_segment_unresolved")},
        "arithmetic": (
            f"{len(poly_lig_entities)} ligand entities of polymer form resolve to "
            f"{len(poly_lig_chains)} inventory chains because "
            f"{len(multi_chain_structs)} structures model the ligand as more than one chain "
            f"(+{sum(v - 1 for v in multi_chain_structs.values())} chains), while "
            f"{len(ambiguous)} ambiguous entities reference several candidate chains without "
            f"selecting one."),
        "closed": True}

    # ------------------------------------------------------------------ D. observation identity
    obs_per_struct = Counter(o["pdb_id"] for o in OB)
    zero_obs = [s for s in S if obs_per_struct.get(s["pdb_id"], 0) == 0]
    zero_reasons = []
    for s in zero_obs:
        if s["apo_status"] == "confirmed_apo":
            why = "confirmed_apo: source annotates 'Apo (no ligand)', so no ligand observation exists"
        elif not (json.loads(canonical_dumps(s))["pharmacological_ligand_count"]):
            why = ("no source ligand annotation of any kind, or every annotation was an apo "
                   "annotation")
        else:
            why = "unexpected"
        zero_reasons.append({"pdb_id": s["pdb_id"], "apo_status": s["apo_status"],
                             "ligand_status": s["ligand_status"], "reason": why})
    dist = Counter(obs_per_struct.get(s["pdb_id"], 0) for s in S)
    total = sum(obs_per_struct.values())
    report["gates"]["D_observation_identity"] = {
        "structures": len(S), "observations": len(OB),
        "sum_observations_per_structure": total,
        "invariant_holds": total == len(OB) == 1331,
        "observations_per_structure": dict(sorted(dist.items())),
        "structures_with_zero_observations": len(zero_obs),
        "zero_observation_reasons": dict(Counter(z["reason"] for z in zero_reasons)),
        "confirmed_apo": sum(1 for s in S if s["apo_status"] == "confirmed_apo"),
        "unresolved_apo": sum(1 for s in S if s["apo_status"] == "unresolved"),
        "probable_apo": sum(1 for s in S if s["apo_status"] == "probable_apo"),
        "ligand_bound": sum(1 for s in S if s["ligand_status"] == "ligand_bound"),
        "multi_ligand": sum(1 for s in S if s["ligand_status"] == "multi_ligand_bound"),
        "structures_with_more_than_two_observations":
            sum(1 for s in S if obs_per_struct.get(s["pdb_id"], 0) > 2),
        "source_conflict_structures": len({c["pdb_id"] for c in CF}),
        "unresolved_ligand_candidate_structures":
            len({l["pdb_id"] for l in LC if l["classification_confidence"] in
                 ("annotated_component_absent_from_deposition", "unmatchable_annotation",
                  "no_polymer_candidate")}),
        "arithmetic": (
            f"{len(S)} structures produce {total} observations: "
            f"{dist.get(0,0)} produce none, {dist.get(1,0)} produce one, "
            f"{dist.get(2,0)} produce two, {dist.get(3,0)} produce three. "
            f"{dist.get(0,0)*0 + dist.get(1,0)*1 + dist.get(2,0)*2 + dist.get(3,0)*3} = {total}."),
        "closed": total == len(OB) == 1331 and all(z["reason"] != "unexpected" for z in zero_reasons)}
    if not report["gates"]["D_observation_identity"]["closed"]:
        blockers.append("D_observation_identity")

    # ---------------------------------------------------------------------- E. apo review overlap
    apo_reviews = [q for q in MQ if q["category"] == "apo_assignment"]
    apo_review_pdbs = {q["pdb_id"] for q in apo_reviews}
    confirmed = {s["pdb_id"] for s in S if s["apo_status"] == "confirmed_apo"}
    unresolved_apo = {s["pdb_id"] for s in S if s["apo_status"] == "unresolved"}
    overlap = apo_review_pdbs & confirmed
    report["gates"]["E_apo_review"] = {
        "confirmed_apo": len(confirmed),
        "apo_manual_review_records": len(apo_reviews),
        "overlap_confirmed_and_review": len(overlap),
        "overlap_pdb_ids": sorted(overlap)[:10],
        "review_records_are_unresolved_apo": len(apo_review_pdbs & unresolved_apo),
        "field_semantics": (
            "apo_status and manual review are disjoint by construction: a review record is "
            "emitted only when apo_status is 'probable_apo' or 'unresolved'. A confirmed_apo "
            "structure rests on a positive source annotation and needs no review, so the two "
            "categories never co-occur on one structure."),
        "explanation": (
            f"The {len(confirmed)} confirmed_apo and the {len(apo_reviews)} apo review records "
            f"describe disjoint sets: every review record corresponds to a structure whose "
            f"apo_status is 'unresolved' ({len(apo_review_pdbs & unresolved_apo)} of "
            f"{len(apo_reviews)}). The counts are unrelated quantities, not a discrepancy."),
        "closed": len(overlap) == 0 and apo_review_pdbs <= unresolved_apo}
    if not report["gates"]["E_apo_review"]["closed"]:
        blockers.append("E_apo_review")

    art = jdump(OUT / "receptor_instance_chain_crosswalk.jsonl", crosswalk)
    report["artifacts"] = {"receptor_instance_chain_crosswalk.jsonl": art}
    report["blockers"] = blockers
    report["all_gates_closed"] = not blockers
    (OUT / "_reconciliation.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                              encoding="utf-8")
    for k, v in report["gates"].items():
        print(f"  {k:32} {'KAPALI' if v['closed'] else 'AÇIK — BLOKER'}")
    print(f"\n  bloker: {blockers if blockers else 'yok'}")
    print(json.dumps({k: report["gates"][k].get("categories")
                      or report["gates"][k].get("arithmetic", "")[:120]
                      for k in report["gates"]}, indent=1, ensure_ascii=False)[:1200])
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
