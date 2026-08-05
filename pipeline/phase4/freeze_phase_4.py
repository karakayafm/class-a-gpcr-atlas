#!/usr/bin/env python3
"""Phase 4 freeze."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.canonical import canonical_dumps, content_sha256, write_json  # noqa: E402
from common.http import utc_now                                          # noqa: E402
P4,AGG=ROOT/"data/intermediate/phase4",ROOT/"data/aggregates"
def jl(p):
    rows=[json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"rows":len(rows),"content_sha256":content_sha256(rows)}
def agg(d): return hashlib.sha256(canonical_dumps(d).encode()).hexdigest()

def main()->int:
    inputs={n:{"content_sha256":content_sha256(json.loads((ROOT/p).read_text(encoding="utf-8")))}
            for n,p in [("phase1_freeze","data/freezes/phase_1/freeze.json"),
                        ("phase2_freeze","releases/phase2/freeze.json"),
                        ("phase3_output_manifest","releases/phase3/OUTPUT_MANIFEST.json")]}
    for n in ("structures.normalized.jsonl","structure_ligand_observations.jsonl",
              "receptor_instances.jsonl","entity_inventory.jsonl"):
        inputs[n]=jl(ROOT/"data/intermediate"/n)
    for n in ("receptor_residue_mapping.jsonl","contact_eligibility.jsonl"):
        inputs[n]=jl(ROOT/"data/intermediate/phase3"/n)
    outputs={n:jl(P4/n) for n in sorted([
        "canonical_review_universe.jsonl","evidence_adjudications.jsonl","mapping_remediation.jsonl",
        "site_class_remediation.jsonl","assembly_context_audit.jsonl","tethered_ligand_review.jsonl",
        "covalent_reconciliation.jsonl","annotated_not_observed.jsonl","motif_residues.jsonl",
        "motif_metrics.jsonl","aggregation_units.jsonl","coverage_records.jsonl",
        "structural_state_normalization.jsonl"])}
    outputs["contact_prevalence.jsonl"]=jl(AGG/"contact_prevalence.jsonl")
    outputs["motif_summary.jsonl"]=jl(AGG/"motif_summaries/motif_summary.jsonl")
    outputs["weighting.jsonl"]=jl(AGG/"weighting_sensitivity/weighting.jsonl")
    outputs["threshold.jsonl"]=jl(AGG/"threshold_sensitivity/threshold.jsonl")
    outputs["mutation_cohorts.jsonl"]=jl(AGG/"mutation_sensitivity/cohorts.jsonl")
    fam={}
    for d in sorted((AGG/"by_major_family").glob("*.jsonl")):
        rows=[json.loads(l) for l in d.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in rows: fam.setdefault(r["group_key"][0],[]).append(r)
    fam_h={k:content_sha256(v) for k,v in sorted(fam.items())}
    motif_h={}
    ms=[json.loads(l) for l in (AGG/"motif_summaries/motif_summary.jsonl")
        .read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in ms: motif_h.setdefault(r["motif_id"],[]).append(r)
    motif_h={k:content_sha256(v) for k,v in sorted(motif_h.items())}
    aggr_h={n:outputs[n]["content_sha256"] for n in
            ("contact_prevalence.jsonl","motif_summary.jsonl","weighting.jsonl",
             "threshold.jsonl","mutation_cohorts.jsonl")}
    named={
     "canonical_review_universe_sha":outputs["canonical_review_universe.jsonl"]["content_sha256"],
     "evidence_adjudications_sha":outputs["evidence_adjudications.jsonl"]["content_sha256"],
     "mapping_remediation_sha":outputs["mapping_remediation.jsonl"]["content_sha256"],
     "site_class_remediation_sha":outputs["site_class_remediation.jsonl"]["content_sha256"],
     "assembly_context_audit_sha":outputs["assembly_context_audit.jsonl"]["content_sha256"],
     "motif_residues_sha":outputs["motif_residues.jsonl"]["content_sha256"],
     "motif_metrics_sha":outputs["motif_metrics.jsonl"]["content_sha256"],
     "aggregation_units_sha":outputs["aggregation_units.jsonl"]["content_sha256"],
     "contact_prevalence_sha":outputs["contact_prevalence.jsonl"]["content_sha256"],
     "motif_summaries_sha":outputs["motif_summary.jsonl"]["content_sha256"],
     "coverage_records_sha":outputs["coverage_records.jsonl"]["content_sha256"],
     "weighting_sensitivity_sha":outputs["weighting.jsonl"]["content_sha256"],
     "threshold_sensitivity_sha":outputs["threshold.jsonl"]["content_sha256"],
     "mutation_sensitivity_sha":outputs["mutation_cohorts.jsonl"]["content_sha256"],
     "per_family_aggregate_sha":agg(fam_h),
     "global_phase4_manifest_sha":agg({"inputs":inputs,"outputs":outputs}),
    }
    val=json.loads((ROOT/"reports/phase4/validation_results.json").read_text(encoding="utf-8"))
    d=ROOT/"releases/phase4"; d.mkdir(parents=True,exist_ok=True)
    write_json(d/"INPUT_MANIFEST.json",{"generated_at":utc_now(),"inputs":inputs})
    write_json(d/"OUTPUT_MANIFEST.json",{"generated_at":utc_now(),"outputs":outputs})
    write_json(d/"SOURCE_VERSIONS.json",{"generated_at":utc_now(),"sources":{
      "GPCRdb":{"used_for":"generic numbering, structure state, ligand annotation",
                "retrieved":"2026-08-03/04","licence":"Data CC BY 4.0"},
      "RCSB PDB":{"used_for":"coordinates, entities, struct_conn, assemblies",
                  "retrieved":"2026-08-04","licence":"CC0 1.0"},
      "UniProt":{"used_for":"accessions relayed from RCSB","licence":"CC BY 4.0 (verified 2026-08-04)"},
      "GtoPdb":{"used":False,"licence_status":"owner_provided_official_verification"},
      "frozen aminergic dataset":{"used":"read-only regression reference","modified":False}}})
    write_json(d/"RULE_VERSIONS.json",{"generated_at":utc_now(),"rule_version":"phase4-rules-1.0.0",
      "float_serialisation":"round(x,6); display rounding is separate",
      "null_representation":"JSON null; absent source distinguished from null value",
      "row_ordering":"sorted by primary id","unicode":"source strings verbatim, NFC as received",
      "gzip_mtime":0,
      "configs":{p.name:content_sha256(json.loads(p.read_text(encoding="utf-8")))
                 for p in sorted((ROOT/"config/phase4").glob("*.json"))},
      "schemas":{p.name:content_sha256(json.loads(p.read_text(encoding="utf-8")))
                 for p in sorted((ROOT/"schemas/phase4").glob("*.json"))}})
    write_json(d/"FAMILY_HASHES.json",{"generated_at":utc_now(),"per_family":fam_h,
                                       "chain":agg(fam_h)})
    write_json(d/"MOTIF_HASHES.json",{"generated_at":utc_now(),"per_motif":motif_h,
                                      "chain":agg(motif_h)})
    write_json(d/"AGGREGATION_HASHES.json",{"generated_at":utc_now(),"per_table":aggr_h,
                                            "chain":agg(aggr_h)})
    (d/"NAMED_HASHES.txt").write_text("\n".join(f"{v}  {k}" for k,v in sorted(named.items()))+"\n",
                                      encoding="utf-8")
    (d/"VALIDATION_REPORT.md").write_text(
      f"# Phase 4 validation\n\n{val['total']} checks, {val['failed']} failed.\n\n"
      + "\n".join(f"- {c['group']} :: {c['name']} — {c['result']}" for c in val["checks"])+"\n",
      encoding="utf-8")
    lines=[]
    for base in (P4,AGG,ROOT/"config/phase4",ROOT/"schemas/phase4",d):
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.name!="checksums.sha256":
                lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT)}")
    (d/"checksums.sha256").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"named_hashes":len(named),"families":len(fam_h),"motifs":len(motif_h),
                      "files_checksummed":len(lines)},indent=1))
    return 0
if __name__=="__main__": raise SystemExit(main())
