#!/usr/bin/env python3
"""Phase 5A — preflight: verify Phase 4 values from artefacts and reconcile the open counts."""
from __future__ import annotations
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402
IN,P3,P4=ROOT/"data/intermediate",ROOT/"data/intermediate/phase3",ROOT/"data/intermediate/phase4"
AGG=ROOT/"data/aggregates"; OUT=ROOT/"data/intermediate/phase5"
def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def dump(p,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text("\n".join(canonical_dumps(r) for r in rows)+("\n" if rows else ""),encoding="utf-8")
    return {"rows":len(rows),"content_sha256":content_sha256(rows)}

def main()->int:
    S=rd(IN/"structures.normalized.jsonl"); RI=rd(IN/"receptor_instances.jsonl")
    U=rd(P4/"aggregation_units.jsonl"); PREV=rd(AGG/"contact_prevalence.jsonl")
    UNIV=rd(P4/"canonical_review_universe.jsonl"); REMED=rd(P4/"mapping_remediation.jsonl")
    ASM=rd(P4/"assembly_context_audit.jsonl"); CVR=rd(P4/"coverage_records.jsonl")
    MR=rd(P4/"motif_residues.jsonl"); SUM=rd(ROOT/"data/contacts/observation_contact_summary.jsonl")
    RM=rd(P3/"receptor_residue_mapping.jsonl")
    core=json.loads((ROOT/"config/phase4/motifs.core.json").read_text(encoding="utf-8"))
    site=Counter(u["binding_site_class"] for u in U); state=Counter(u["normalized_structural_state"] for u in U)
    hr=sum(1 for u in UNIV if u["human_review_requirement"]=="required")
    checks={
      "structures":(len(S),1358),"major_families":(len({s['major_family_id'] for s in S}),11),
      "canonical_review_records":(len(UNIV),726),"human_review_required":(hr,178),
      "aggregation_units":(len(U),727),
      "small_molecule_core_pocket_units":(site["canonical_7tm_pocket"],560),
      "polymer_interface_units":(site["extracellular_polymer_interface"],152),
      "covalent_units":(site["covalent_core_site"],15),
      "active_units":(state["active"],490),"inactive_units":(state["inactive"],220),
      "intermediate_units":(state["intermediate"],16),"unknown_state_units":(state["unknown"],1),
      "aggregate_records":(len(PREV),183984),
      "unresolved_site_class_observations":(sum(1 for s in SUM if s["binding_site_class"]=="unresolved"),51),
      "motif_count":(len(core["motifs"]),8),"motif_generic_positions":(len(core["all_positions"]),21),
    }
    bad=[(k,e,a) for k,(a,e) in checks.items() if a!=e]
    arith={"560+152+15=727":(site["canonical_7tm_pocket"]+site["extracellular_polymer_interface"]
                             +site["covalent_core_site"],727),
           "490+220+16+1=727":(state["active"]+state["inactive"]+state["intermediate"]
                               +state["unknown"],727)}
    arith_bad=[(k,e,a) for k,(a,e) in arith.items() if a!=e]

    # ---- A. 1516 vs 1517 receptor instances ------------------------------------------------
    rem_ids={r["receptor_instance_id"] for r in REMED}
    ri_ids={r["receptor_instance_id"] for r in RI}
    missing=sorted(ri_ids-rem_ids); extra=sorted(rem_ids-ri_ids)
    rows=[]
    rm_ids={m["receptor_instance_id"] for m in RM}
    for rid in sorted(ri_ids):
        r=next(x for x in RI if x["receptor_instance_id"]==rid)
        st=next(x for x in S if x["pdb_id"]==r["pdb_id"])
        if rid in rem_ids:
            reason="exact_mapping_remediation_row"; detail="a Phase 4 remediation row exists"
        elif rid not in rm_ids:
            reason="receptor_instance_intentionally_out_of_remediation_scope"
            detail=("no receptor residue was mapped for this instance, so no mapping route was "
                    "scored and no remediation row could exist; the instance is retained")
        else:
            reason="unresolved_data_loss"; detail="present in Phase 3 but absent from Phase 4 with no stated cause"
        rows.append({"receptor_instance_id":rid,"pdb_id":r["pdb_id"],
                     "auth_asym_id":r["auth_asym_id"],"polymer_entity_id":r["polymer_entity_id"],
                     "metadata_completeness":st["metadata_completeness"],
                     "has_residue_mapping":rid in rm_ids,
                     "has_remediation_row":rid in rem_ids,
                     "reason":reason,"detail":detail})
    a_cw=dump(OUT/"receptor_instance_preflight_crosswalk.jsonl",rows)
    unexplained=[r for r in rows if r["reason"]=="unresolved_data_loss"]

    # ---- B. assembly audit real counts ------------------------------------------------------
    asm_counts=dict(Counter(a["outcome"] for a in ASM))
    asm_total=sum(asm_counts.values())
    asm_ok=asm_total==len(ASM)
    asm_warn={a["pdb_id"]:a["outcome"] for a in ASM
              if a["outcome"] in ("ambiguous_human_review_required","biological_assembly_required")}

    report={"generated_at":utc_now(),
      "value_checks":{k:{"expected":e,"actual":a,"match":a==e} for k,(a,e) in checks.items()},
      "value_mismatches":bad,
      "arithmetic":{k:{"expected":e,"actual":a,"match":a==e} for k,(a,e) in arith.items()},
      "arithmetic_mismatches":arith_bad,
      "A_receptor_instance_reconciliation":{
        "phase3_receptor_instances":len(RI),"phase4_remediation_rows":len(REMED),
        "difference":len(RI)-len(REMED),
        "reasons":dict(Counter(r["reason"] for r in rows)),
        "instances_without_remediation":[{k:r[k] for k in
            ("receptor_instance_id","pdb_id","metadata_completeness","has_residue_mapping","reason")}
            for r in rows if not r["has_remediation_row"]],
        "unexplained":len(unexplained),
        "extra_rows_not_in_phase3":extra},
      "B_assembly_audit":{"rows":len(ASM),"outcome_counts":asm_counts,
        "sum_matches_rows":asm_ok,
        "structures_with_warning":asm_warn,
        "note":("categories recounted from data/intermediate/phase4/assembly_context_audit.jsonl, "
                "not from any prose summary")},
      "C_state_count_semantics":{"values":{k:state[k] for k in ("active","inactive","intermediate","unknown")},
        "unit_of_count":"aggregation_unit",
        "must_not_be_labelled":"structures",
        "structures_total":len(S)},
      "D_review_count_semantics":{"human_review_required":hr,
        "unit_of_count":"canonical_review_item",
        "distinct_pdbs_affected":len({u["pdb_id"] for u in UNIV if u["human_review_requirement"]=="required"}),
        "must_not_be_labelled":"unverified structures",
        "ui_label":"Human-review-required evidence items"},
      "low_n_warning_families":[c["major_family_id"] for c in CVR if c["warnings"]],
      "family_coverage_range":{"generic_contact_coverage":[min(c["generic_contact_coverage"] for c in CVR),
                                                            max(c["generic_contact_coverage"] for c in CVR)]},
      "unresolved_generic_mapping":{
        "structures":len({m["pdb_id"] for m in RM if m["mapping_route"]=="no_validated_route"}),
        "receptor_instances":sum(1 for r in REMED
            if r["outcome"]=="mapping_unresolved_excluded_from_generic_aggregation")},
      "artifacts":{"receptor_instance_preflight_crosswalk.jsonl":a_cw},
      "blocked":bool(bad or arith_bad or unexplained)}
    (OUT/"_preflight.json").write_text(json.dumps(report,indent=1,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"value_mismatches":bad,"arithmetic_mismatches":arith_bad,
      "A_difference":report["A_receptor_instance_reconciliation"]["difference"],
      "A_reasons":report["A_receptor_instance_reconciliation"]["reasons"],
      "A_unexplained":len(unexplained),
      "B_assembly":asm_counts,"B_sum_ok":asm_ok,
      "low_n_families":report["low_n_warning_families"],
      "coverage_range":report["family_coverage_range"],
      "blocked":report["blocked"]},indent=1,ensure_ascii=False))
    return 1 if report["blocked"] else 0

if __name__=="__main__": raise SystemExit(main())
