#!/usr/bin/env python3
"""Phase 2 — pilots: Nucleotide gold review, Peptide challenge, cross-family edge cases.

The gold-review table keeps automatic output and human decisions in **separate columns**: the
``auto_*`` columns are what the pipeline produced, the ``review_*`` columns are empty and are
for a curator to fill. A table that mixes the two cannot later be used to measure the pipeline.

    python3 pipeline/phase2/build_pilots.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402

IN = ROOT / "data/intermediate"
PIL = ROOT / "data/pilots"


def rd(name):
    return [json.loads(l) for l in (IN / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def jdump(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(canonical_dumps(r) for r in rows) + ("\n" if rows else ""),
                    encoding="utf-8")
    return {"rows": len(rows), "content_sha256": content_sha256(rows)}


PHARM = {"pharmacological_orthosteric_ligand", "pharmacological_allosteric_ligand",
         "pharmacological_bitopic_ligand", "pharmacological_covalent_ligand",
         "endogenous_polymer_ligand", "tethered_ligand", "pharmacological_co_ligand",
         "positive_allosteric_modulator", "negative_allosteric_modulator",
         "silent_allosteric_modulator"}
ENV = {"environment_ion", "membrane_lipid", "detergent", "buffer_or_crystallization_additive",
       "glycan_or_post_translational_component", "construct_stabilizer"}


def main() -> int:
    S = rd("structures.normalized.jsonl")
    I = rd("entity_inventory.jsonl")
    L = rd("ligand_candidates.jsonl")
    Q = rd("manual_review_queue.jsonl")
    by_pdb_inv = defaultdict(list)
    for i in I:
        by_pdb_inv[i["pdb_id"]].append(i)
    by_pdb_lig = defaultdict(list)
    for l in L:
        by_pdb_lig[l["pdb_id"]].append(l)
    review_pdbs = {q["pdb_id"] for q in Q}
    out = {}

    # ----------------------------------------------------------------- Nucleotide pilot
    nuc = [s for s in S if s["major_family_id"] == "001_006"]
    rows = []
    for s in sorted(nuc, key=lambda x: x["pdb_id"]):
        pid = s["pdb_id"]
        inv = by_pdb_inv[pid]
        lig = by_pdb_lig[pid]
        accepted = [l for l in lig if l["ligand_role"] in PHARM
                    and l["pharmacological_relevance"] == "relevant"]
        excluded = [i for i in inv if i.get("final_role") in ENV]
        cand = [i for i in inv if i["entity_form"] in ("nonpolymer_residue", "covalent_adduct")]
        rows.append({
            "pdb_id": pid, "receptor": s["receptor_name"],
            "receptor_entry_name": s["receptor_entry_name"], "species": s["species"],
            "receptor_chains": s["receptor_instances"],
            "auto_candidate_entities": sorted({i["nonpolymer_comp_id"] for i in cand
                                               if i["nonpolymer_comp_id"]}),
            "auto_accepted_pharmacological": [
                {"ligand_entity_id": l["ligand_entity_id"], "role": l["ligand_role"],
                 "form": l["entity_form"], "binding_mode": l["binding_mode"],
                 "binding_site_class": l["binding_site_class"],
                 "confidence": l["classification_confidence"],
                 "evidence": l["selection_evidence"]} for l in accepted],
            "auto_excluded_environment": sorted(Counter(
                i["nonpolymer_comp_id"] for i in excluded if i["nonpolymer_comp_id"]).items()),
            "auto_binding_site_class": sorted({l["binding_site_class"] for l in accepted}),
            "auto_ligand_status": s["ligand_status"], "auto_apo_status": s["apo_status"],
            "auto_confidence": sorted({l["classification_confidence"] for l in accepted}),
            "auto_manual_review_status": ("required" if pid in review_pdbs else "not_required"),
            # --- curator columns, deliberately empty ---
            "review_accepted_ligands": None, "review_binding_site_class": None,
            "review_agrees_with_auto": None, "review_notes": None, "reviewer": None,
            "review_date": None,
        })
    out["nucleotide"] = jdump(PIL / "nucleotide/gold_review_table.jsonl", rows)
    with (PIL / "nucleotide/gold_review_table.csv").open("w", newline="", encoding="utf-8") as fh:
        cols = ["pdb_id", "receptor", "species", "receptor_chains", "auto_candidate_entities",
                "auto_accepted_pharmacological_ids", "auto_accepted_roles",
                "auto_excluded_environment", "auto_binding_site_class", "auto_ligand_status",
                "auto_apo_status", "auto_confidence", "auto_manual_review_status",
                "review_accepted_ligands", "review_binding_site_class",
                "review_agrees_with_auto", "review_notes", "reviewer", "review_date"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({
                "pdb_id": r["pdb_id"], "receptor": r["receptor"], "species": r["species"],
                "receptor_chains": ";".join(r["receptor_chains"]),
                "auto_candidate_entities": ";".join(r["auto_candidate_entities"]),
                "auto_accepted_pharmacological_ids": ";".join(
                    a["ligand_entity_id"] for a in r["auto_accepted_pharmacological"]),
                "auto_accepted_roles": ";".join(
                    a["role"] for a in r["auto_accepted_pharmacological"]),
                "auto_excluded_environment": ";".join(
                    f"{c}x{n}" for c, n in r["auto_excluded_environment"]),
                "auto_binding_site_class": ";".join(r["auto_binding_site_class"]),
                "auto_ligand_status": r["auto_ligand_status"],
                "auto_apo_status": r["auto_apo_status"],
                "auto_confidence": ";".join(r["auto_confidence"]),
                "auto_manual_review_status": r["auto_manual_review_status"],
                "review_accepted_ligands": "", "review_binding_site_class": "",
                "review_agrees_with_auto": "", "review_notes": "", "reviewer": "",
                "review_date": ""})

    # ----------------------------------------------------------------- Peptide challenge
    pep = [s for s in S if s["major_family_id"] == "001_002"]
    prows = []
    for s in sorted(pep, key=lambda x: x["pdb_id"]):
        pid = s["pdb_id"]
        chains = [i for i in by_pdb_inv[pid] if i["entity_form"] == "polymer_chain"]
        lig = by_pdb_lig[pid]
        prows.append({
            "pdb_id": pid, "receptor": s["receptor_name"], "species": s["species"],
            "receptor_chains": s["receptor_instances"],
            "nonpolymer_entity_count": s["entity_counts"]["nonpolymer_entities"],
            "polymer_inventory": [
                {"entity_inventory_id": c["entity_inventory_id"],
                 "polymer_entity_id": c["polymer_entity_id"],
                 "description": c["entity_description"],
                 "sequence_length": c["sequence_length"],
                 "uniprot_ids": c["source_identifiers"].get("uniprot_ids"),
                 "provisional_chain_role": c["provisional_polymer_role"],
                 "final_chain_role": c["final_role"],
                 "role_basis": c["final_role_basis"]} for c in chains],
            "ligand_candidates": [
                {"ligand_entity_id": l["ligand_entity_id"], "form": l["entity_form"],
                 "role": l["ligand_role"], "confidence": l["classification_confidence"],
                 "ambiguity_flags": l["ambiguity_flags"]} for l in lig],
            "ligand_status": s["ligand_status"], "apo_status": s["apo_status"],
            "apo_assignment_basis": s["apo_assignment_basis"],
            "manual_review_status": "required" if pid in review_pdbs else "not_required",
        })
    out["peptide"] = jdump(PIL / "peptide/entity_challenge.jsonl", prows)

    # confusion audit — only over records a human could check, never over the whole set
    conf_rows = []
    for r in prows:
        for c in r["polymer_inventory"]:
            conf_rows.append({
                "pdb_id": r["pdb_id"], "entity_inventory_id": c["entity_inventory_id"],
                "description": c["description"], "sequence_length": c["sequence_length"],
                "auto_role": c["final_chain_role"], "auto_basis": c["role_basis"],
                "review_true_role": None, "review_outcome": None, "reviewer": None})
    out["peptide_confusion"] = jdump(PIL / "peptide/polymer_role_confusion_audit.jsonl", conf_rows)

    # ----------------------------------------------------------------- cross-family edge cases
    def pick(pred, why, n=4):
        hits = [s for s in S if pred(s)]
        return [{"pdb_id": h["pdb_id"], "family": h["major_family_name"],
                 "receptor": h["receptor_name"], "species": h["species"],
                 "selection_reason": why,
                 "ligand_status": h["ligand_status"], "apo_status": h["apo_status"],
                 "ligands": [{"id": l["ligand_entity_id"], "form": l["entity_form"],
                              "role": l["ligand_role"], "site": l["binding_site_class"],
                              "confidence": l["classification_confidence"]}
                             for l in by_pdb_lig[h["pdb_id"]]],
                 "chain_roles": sorted(Counter(
                     i["final_role"] for i in by_pdb_inv[h["pdb_id"]]
                     if i["entity_form"] == "polymer_chain").items())}
                for h in sorted(hits, key=lambda x: x["pdb_id"])[:n]]

    def has_role(s, role):
        return any(l["ligand_role"] == role for l in by_pdb_lig[s["pdb_id"]])
    def has_form(s, form):
        return any(l["entity_form"] == form for l in by_pdb_lig[s["pdb_id"]])

    edge = {
     "covalent_retinal_sensory": pick(
        lambda s: s["major_family_name"] == "Sensory receptors" and has_form(s, "covalent_adduct"),
        "opsin with a covalently bound chromophore: tests that covalency is recorded as bonding, "
        "not promoted to agonism"),
     "protein_family_protein_ligand": pick(
        lambda s: s["major_family_name"] == "Protein receptors" and has_form(s, "polymer_chain"),
        "protein ligand as a polymer chain: tests that a ligand need not be a HET component"),
     # Selected across the whole class, not within one family. The Phase 2 brief expected
     # chemokines in the Peptide family; GPCRdb in fact classifies every chemokine receptor
     # (CXCR4, CCR5, ACKR3, CX3CR1, CCR1-3, CXCR1/3) under Protein receptors, with the viral
     # US28 under Other. Constraining the selector by family returned an empty group, which is
     # how the misconception surfaced.
     "chemokine_ligand": pick(
        lambda s: any(
            k in (i["entity_description"] or "").lower()
            for i in by_pdb_inv[s["pdb_id"]]
            for k in ("chemokine", "fractalkine", "stromal cell-derived", "interleukin-8")),
        "chemokine ligand (found in Protein receptors, not Peptide receptors): tests protein "
        "ligand vs transducer vs antibody separation"),
     "lipid_family_lipid_ligand": pick(
        lambda s: s["major_family_name"] == "Lipid receptors" and s["ligand_status"] != "unresolved",
        "lipid receptor: tests that a lipid can be the ligand when a source says so, while the "
        "same chemistry stays environment elsewhere"),
     "intracellular_or_allosteric": pick(
        lambda s: has_role(s, "negative_allosteric_modulator")
        or has_role(s, "pharmacological_allosteric_ligand"),
        "allosteric modulator: tests that site class is not defaulted to the orthosteric pocket"),
     "multi_ligand": pick(
        lambda s: s["ligand_status"] == "multi_ligand_bound",
        "more than one pharmacological entity: tests that no single primary ligand is forced"),
     "positive_allosteric_modulator": pick(
        lambda s: has_role(s, "positive_allosteric_modulator"),
        "PAM alongside an orthosteric agonist: tests the layered pharmacology model"),
     "confirmed_apo": pick(
        lambda s: s["apo_status"] == "confirmed_apo",
        "apo assigned from positive source evidence rather than from a zero count"),
     "unresolved_apo": pick(
        lambda s: s["apo_status"] == "unresolved",
        "apo could not be decided: tests that unresolved is emitted rather than guessed"),
     "orphan_family": pick(
        lambda s: s["major_family_name"] == "Orphan receptors" and s["ligand_status"] != "unresolved",
        "orphan receptor with an annotated ligand: tests OD-10, the family is produced normally"),
     "non_human_ortholog": pick(
        lambda s: s["species"] != "Homo sapiens",
        "non-human structure: tests OD-04, species is mandatory and orthologues are not merged"),
     "chimeric_fusion_construct": pick(
        lambda s: s["construct_engineering_status"] == "chimeric_fusion",
        "receptor fused to a crystallisation partner: tests that the chimera stays one receptor "
        "instance and the fusion is construct metadata"),
     "rcsb_metadata_absent": pick(
        lambda s: s["metadata_completeness"] == "rcsb_metadata_absent",
        "GPCRdb lists the entry but RCSB does not serve it: tests that it is retained with an "
        "explicit completeness flag rather than dropped", n=2),
    }
    erows = [{"edge_case_group": k, "count": len(v), "structures": v} for k, v in edge.items()]
    out["edge_cases"] = jdump(PIL / "cross_family_edge_cases/edge_cases.jsonl", erows)

    summary = {"generated_at": utc_now(), "artifacts": out,
               "nucleotide_structures": len(rows), "peptide_structures": len(prows),
               "edge_case_groups": len(edge),
               "edge_case_structures": sum(len(v) for v in edge.values())}
    (PIL / "_pilot_summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                                             encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
