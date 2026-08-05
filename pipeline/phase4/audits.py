#!/usr/bin/env python3
"""Phase 4A — site-class remediation, stratified assembly audit, covalent and mutation
reconciliation, tethered-ligand evidence review."""
from __future__ import annotations
import gzip, json, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from phase3.mmcif import read, atoms                          # noqa: E402
from common.canonical import canonical_dumps, content_sha256  # noqa: E402
from common.http import utc_now                               # noqa: E402
IN, P3, P4 = ROOT/"data/intermediate", ROOT/"data/intermediate/phase3", ROOT/"data/intermediate/phase4"
CON = ROOT/"data/contacts"
HUMAN_NULL = {"human_curator_decision": None, "human_curator_identity": None,
              "human_review_date": None, "human_review_status": "not_started"}

def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def dump(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(canonical_dumps(r) for r in rows)+("\n" if rows else ""), encoding="utf-8")
    return {"rows": len(rows), "content_sha256": content_sha256(rows)}

def main() -> int:
    S={s["pdb_id"]:s for s in rd(IN/"structures.normalized.jsonl")}
    RI=rd(IN/"receptor_instances.jsonl")
    EI=rd(IN/"entity_inventory.jsonl")
    LC={l["ligand_entity_id"]:l for l in rd(IN/"ligand_candidates.jsonl")}
    OB=rd(IN/"structure_ligand_observations.jsonl")
    RM=rd(P3/"receptor_residue_mapping.jsonl")
    SCR=rd(P3/"site_class_review.jsonl")
    TL=rd(P3/"tethered_ligand_candidates.jsonl")
    SUM={s["structure_ligand_id"]:s for s in rd(CON/"observation_contact_summary.jsonl")}
    EL={e["structure_ligand_id"]:e for e in rd(P3/"contact_eligibility.jsonl")}
    contacts=[]
    for f in sorted((CON/"by_family").glob("*/residue_pair_contacts.jsonl.gz")):
        contacts += [json.loads(l) for l in gzip.open(f,"rt")]
    by_obs=defaultdict(list)
    for c in contacts: by_obs[c["structure_ligand_id"]].append(c)
    arts={}

    # ------------------------------------------------------------- site-class remediation
    rows=[]
    for s in SCR:
        le=s["ligand_entity_id"]; lg=LC[le]
        sl=f"{le}::{lg['receptor_instance_id']}"
        produced = sl in SUM
        segs=s["contacted_segments"]
        tm=sum(v for k,v in segs.items() if str(k).startswith("TM"))
        tot=sum(segs.values())
        phase4 = "unresolved_human_review_required"
        basis = ("the source states a modulator function without stating where it binds; "
                 "geometry alone cannot separate an allosteric site from the orthosteric "
                 "pocket when both contact the same helices")
        if not produced:
            phase4="metadata_only_no_coordinate_observation"
            basis=("this observation produces no coordinate contact, so no geometric evidence "
                   "exists; the source annotation is retained as metadata")
        rows.append({"ligand_entity_id":le,"pdb_id":s["pdb_id"],"structure_ligand_id":sl,
            "ligand_role":lg["ligand_role"],"binding_mode":lg["binding_mode"],
            "phase2_site_class":"unresolved",
            "phase3_outcome":("unresolved_with_geometry_candidate" if produced else
                              "no_coordinate_observation"),
            "phase3_geometry_candidate":s["geometry_supported_site_candidate"],
            "contacted_segments":segs,
            "tm_contact_fraction":round(tm/tot,4) if tot else None,
            "phase4_outcome":phase4,"adjudication_basis":basis,
            "final_binding_site_class":"unresolved",
            "enters_pooled_aggregation":False,
            "auto_merge_into_other_class":False,
            **HUMAN_NULL})
    arts["site_class_remediation.jsonl"]=dump(P4/"site_class_remediation.jsonl",
        sorted(rows,key=lambda r:r["ligand_entity_id"]))
    site_summary={"phase3_start_items":len(SCR),
        "resolved_in_phase3":0,
        "unresolved_after_phase3":sum(1 for r in rows if r["phase3_outcome"]=="unresolved_with_geometry_candidate"),
        "no_coordinate_observation":sum(1 for r in rows if r["phase3_outcome"]=="no_coordinate_observation"),
        "resolved_in_phase4":sum(1 for r in rows if r["phase4_outcome"].startswith("resolved")),
        "human_review_required":sum(1 for r in rows if r["phase4_outcome"]=="unresolved_human_review_required"),
        "metadata_only":sum(1 for r in rows if r["phase4_outcome"]=="metadata_only_no_coordinate_observation")}

    # --------------------------------------------------------- stratified assembly audit
    inst_per_pdb=Counter(r["pdb_id"] for r in RI)
    poly_lig_chains=defaultdict(set)
    for i in EI:
        if i["entity_form"]=="polymer_chain" and i["final_role"]=="endogenous_polymer_ligand":
            poly_lig_chains[i["pdb_id"]] |= set(i["auth_asym_ids"])
    ab_pdbs={i["pdb_id"] for i in EI if i["entity_form"]=="polymer_chain"
             and i["final_role"]=="antibody_or_nanobody"}
    strata={
      "multiple_receptor_instances":[p for p,n in inst_per_pdb.items() if n>1],
      "multiple_polymer_ligand_chains":[p for p,c in poly_lig_chains.items() if len(c)>1],
      "polymer_interface_with_antibody":[s["pdb_id"] for s in SUM.values()
            if s["is_polymer_interface"] and s["pdb_id"] in ab_pdbs],
      "multi_ligand_structures":[p for p,s in S.items() if s["ligand_status"]=="multi_ligand_bound"],
      "chemokine_protein_ligand":[s["pdb_id"] for s in SUM.values()
            if s["major_family_id"]=="001_003" and s["is_polymer_interface"]],
      "polymer_interface_general":[s["pdb_id"] for s in SUM.values() if s["is_polymer_interface"]],
    }
    audit=[]
    seen=set()
    for stratum, pdbs in strata.items():
        for pid in sorted(set(pdbs))[:12]:
            if (stratum,pid) in seen: continue
            seen.add((stratum,pid))
            cif=ROOT/"data/cache/coordinates"/f"{pid}.cif.gz"
            asm=read(cif,{"_pdbx_struct_assembly","_pdbx_struct_assembly_gen"})
            n_asm=len(asm["_pdbx_struct_assembly"])
            gens=asm["_pdbx_struct_assembly_gen"]
            ops={g.get("oper_expression") for g in gens}
            identity_only=ops<= {"1",""} or not ops
            obs=[s for s in SUM.values() if s["pdb_id"]==pid]
            dup=0
            for o in obs:
                rows_o=by_obs[o["structure_ligand_id"]]
                key=Counter((c["receptor_auth_seq_id"],c["ligand_auth_seq_id"],
                             round(c["min_distance_angstrom"],3)) for c in rows_o)
                dup+=sum(v-1 for v in key.values() if v>1)
            if n_asm<=1 and identity_only:
                outcome="asymmetric_unit_confirmed"
                note=("a single author-defined assembly generated by the identity operator only; "
                      "the deposited coordinates already are the biological unit")
            elif identity_only:
                outcome="assembly_context_equivalent"
                note=(f"{n_asm} assemblies declared but all generated by the identity operator; "
                      "no symmetry copy is required to place the ligand")
            else:
                outcome="ambiguous_human_review_required"
                note=(f"assembly generation uses operators {sorted(ops)}; whether the biological "
                      "interface differs from the deposited one needs review")
            audit.append({"pdb_id":pid,"stratum":stratum,
                "receptor_instances":inst_per_pdb[pid],
                "polymer_ligand_chains":len(poly_lig_chains.get(pid,())),
                "assemblies_declared":n_asm,
                "assembly_operators":sorted(o for o in ops if o),
                "identity_operator_only":identity_only,
                "observations":len(obs),
                "duplicate_contact_rows":dup,
                "outcome":outcome,"note":note,
                "max_contact_heuristic_used":False,
                **HUMAN_NULL})
    arts["assembly_context_audit.jsonl"]=dump(P4/"assembly_context_audit.jsonl",
        sorted(audit,key=lambda r:(r["stratum"],r["pdb_id"])))

    # ------------------------------------------------------------ covalent reconciliation
    cov_obs=[s for s in SUM.values() if s["binding_site_class"]=="covalent_core_site"]
    cov_rows=[]
    for o in sorted(cov_obs,key=lambda x:x["structure_ligand_id"]):
        rows_o=by_obs[o["structure_ligand_id"]]
        n_cov=sum(1 for c in rows_o if c["covalent_connection"])
        pid=o["pdb_id"]
        sc=read(ROOT/"data/cache/coordinates"/f"{pid}.cif.gz",{"_struct_conn"})["_struct_conn"]
        covale=[c for c in sc if (c.get("conn_type_id") or "").lower()=="covale"]
        lig_names={c["ligand_residue_name"] for c in rows_o}
        rel=[c for c in covale if (c.get("ptnr1_label_comp_id") in lig_names
                                   or c.get("ptnr2_label_comp_id") in lig_names)]
        # Is the bond partner the receptor chain, or another ligand component? A covalent bond
        # that joins two non-polymer components to each other is real chemistry but is not a
        # receptor-ligand link, and must not be reported as a missing one.
        rec_chains = {r["auth_asym_id"] for r in RI if r["pdb_id"] == pid}
        lig_instances = {(c["ligand_auth_asym_id"], c["ligand_auth_seq_id"]) for c in rows_o}
        all_np = {(i["auth_asym_ids"][0], str(i["auth_seq_id"]))
                  for i in EI if i["pdb_id"] == pid
                  and i["entity_form"] in ("nonpolymer_residue", "covalent_adduct")
                  and i["auth_asym_ids"]}
        def is_receptor_side(c, n):
            comp = c.get(f"ptnr{n}_label_comp_id")
            ch = c.get(f"ptnr{n}_auth_asym_id"); sq = c.get(f"ptnr{n}_auth_seq_id")
            return ch in rec_chains and (ch, sq) not in all_np
        rel_to_receptor = [c for c in rel if is_receptor_side(c, 1) or is_receptor_side(c, 2)]
        if n_cov>0:
            reason=None; status="covalent_contact_present"
        elif not covale:
            reason="source annotation covalent, struct_conn absent"; status="no_struct_conn_record"
        elif not rel:
            reason="non_receptor_covalent_bond"; status="covalent_bond_not_to_this_ligand"
        elif not rel_to_receptor:
            reason=("non_receptor_covalent_bond: the covalent record joins two non-polymer "
                    "components to each other, not the ligand to the receptor")
            status="ligand_internal_covalent_bond"
        else:
            reason="ligand mapped but bonded atom pair not within the contact set"
            status="bonded_atom_missing"
        cov_rows.append({"structure_ligand_id":o["structure_ligand_id"],"pdb_id":pid,
            "ligand_entity_id":o["structure_ligand_id"].split("::")[0],
            "ligand_components":sorted(lig_names),
            "struct_conn_covale_records":len(covale),
            "covale_records_involving_ligand":len(rel),
            "receptor_bonded_residues":sorted(
                ({c.get("ptnr1_label_comp_id") for c in rel}
                 | {c.get("ptnr2_label_comp_id") for c in rel}) - {None}),
            "contact_rows_with_covalent_flag":n_cov,
            "status":status,"missing_covalent_link_reason":reason,
            "covale_records_to_receptor":len(rel_to_receptor),
            "site_class_review_suggested":(status=="ligand_internal_covalent_bond"),
            "site_class_review_note":(
                "the entity carries a covalent linkage flag but the bond is internal to the "
                "ligand; whether covalent_core_site is the right class is a curator question"
                if status=="ligand_internal_covalent_bond" else None),
            "ligand_remains_ligand":True,
            **HUMAN_NULL})
    arts["covalent_reconciliation.jsonl"]=dump(P4/"covalent_reconciliation.jsonl",cov_rows)
    cov_summary={"covalent_core_site_observations":len(cov_obs),
        "observations_with_covalent_contact":sum(1 for r in cov_rows if r["contact_rows_with_covalent_flag"]>0),
        "observations_without":sum(1 for r in cov_rows if r["contact_rows_with_covalent_flag"]==0),
        "total_covalent_contact_rows":sum(r["contact_rows_with_covalent_flag"] for r in cov_rows),
        "reasons":dict(Counter(r["missing_covalent_link_reason"] for r in cov_rows if r["missing_covalent_link_reason"]))}

    # ------------------------------------------------------------ mutation reconciliation
    declared=sum(r["mutation_count"] for r in RI)
    obs_diff=sum(1 for m in RM if m["residue_identity_matches_wild_type"] is False)
    no_ref=sum(1 for m in RM if m["wild_type_identity_available"] is False)
    fusion=sum(1 for m in RM if m["mapping_status"]=="construct_or_fusion_region")
    unres=sum(1 for m in RM if m["mapping_status"]=="unresolved")
    decl_pairs=Counter()
    for r in RI:
        for mu in r["mutation_list"]:
            decl_pairs[(r["pdb_id"],mu)]+=1
    dup_decl=sum(v-1 for v in decl_pairs.values() if v>1)
    mapped_generic_diff=sum(1 for m in RM if m["residue_identity_matches_wild_type"] is False
                            and m["mapping_status"]=="mapped_generic")
    mut_rec={
      "phase2_depositor_reported_mutations":declared,
      "distinct_declared_mutation_strings":len(decl_pairs),
      "duplicate_declarations_across_instances":dup_decl,
      "phase3_coordinate_residue_differences":obs_diff,
      "differences_on_generic_mapped_residues":mapped_generic_diff,
      "residues_without_reference_identity":no_ref,
      "residues_in_fusion_or_construct_region":fusion,
      "residues_with_unresolved_mapping":unres,
      "explanation":(
        "The two figures count different objects and are not comparable directly. "
        f"{declared} is the number of mutation strings declared by depositors across "
        f"{len(RI)} receptor instances, including duplicates where one entity is modelled as "
        f"several chains ({dup_decl} duplicate declarations). "
        f"{obs_diff} is the number of MODELLED residues whose identity differs from the GPCRdb "
        "reference. A declared mutation contributes no coordinate difference when the residue "
        "lies outside the modelled region, in a deleted or truncated segment, in a fusion "
        f"region ({fusion} residues), or where the mapping is unresolved ({unres} residues) or "
        f"no reference residue exists ({no_ref} residues)."),
      "aggregation_rule":("mutation-aware aggregation uses only differences on residues that map "
                          "to a generic position with a validated route: "
                          f"{mapped_generic_diff} residues"),
      "unresolved_never_wild_type":True}
    (P4/"mutation_reconciliation.jsonl").write_text(canonical_dumps(mut_rec)+"\n",encoding="utf-8")
    arts["mutation_reconciliation.jsonl"]={"rows":1,"content_sha256":content_sha256([mut_rec])}

    # ------------------------------------------------------------ tethered ligand review
    teth=[]
    for t in TL:
        pid=t["pdb_id"]
        chains={r["auth_asym_id"] for r in RI if r["pdb_id"]==pid}
        teth.append({"pdb_id":pid,"receptor":t["receptor"],
            "receptor_entry_name":t["receptor_entry_name"],
            "receptor_chains":sorted(c for c in chains if c),
            "possible_segment":None,"cleavage_site":None,
            "construct_sequence_available":True,
            "deposited_annotation":None,
            "gpcrdb_annotation":"structure ligand annotation carries no receptor-segment record",
            "gtopdb_annotation":"not retrievable from this environment",
            "primary_publication":t["primary_publication"],
            "segment_coordinates":None,
            "evidence_status":"insufficient",
            "outcome":"unresolved_human_review_required",
            "basis":("no source available to Phase 4 states a cleavage site or an activating "
                     "segment range for this entry; a tethered ligand is not assigned from "
                     "receptor identity, sequence pattern or proximity"),
            "binding_site_class":None,"contact_eligibility":"excluded",
            **HUMAN_NULL})
    arts["tethered_ligand_review.jsonl"]=dump(P4/"tethered_ligand_review.jsonl",teth)

    summary={"generated_at":utc_now(),"site_class":site_summary,
             "assembly_audit":{"structures_examined":len({a['pdb_id'] for a in audit}),
                               "rows":len(audit),
                               "outcomes":dict(Counter(a["outcome"] for a in audit)),
                               "duplicate_contact_rows_found":sum(a["duplicate_contact_rows"] for a in audit)},
             "covalent":cov_summary,"mutation":mut_rec,
             "tethered":{"candidates":len(teth),
                         "outcomes":dict(Counter(t["outcome"] for t in teth))},
             "artifacts":arts}
    (P4/"_audits_summary.json").write_text(json.dumps(summary,indent=1,ensure_ascii=False),
                                           encoding="utf-8")
    print(json.dumps({k:summary[k] for k in ("site_class","assembly_audit","covalent","tethered")},
                     indent=1))
    print(json.dumps({k:mut_rec[k] for k in ("phase2_depositor_reported_mutations",
        "duplicate_declarations_across_instances","phase3_coordinate_residue_differences",
        "differences_on_generic_mapped_residues","residues_without_reference_identity",
        "residues_in_fusion_or_construct_region")},indent=1))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
