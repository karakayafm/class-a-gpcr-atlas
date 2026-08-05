#!/usr/bin/env python3
"""Phase 4C — motif summaries by family, receptor family, receptor and state."""
from __future__ import annotations
import json, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402
P4=ROOT/"data/intermediate/phase4"; AGG=ROOT/"data/aggregates"
def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def dump(p,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text("\n".join(canonical_dumps(r) for r in rows)+("\n" if rows else ""),encoding="utf-8")
    return {"rows":len(rows),"content_sha256":content_sha256(rows)}
def f(x): return None if x is None else round(x,6)

def main()->int:
    MR=rd(P4/"motif_residues.jsonl"); MM=rd(P4/"motif_metrics.jsonl")
    STATE={r["pdb_id"]:r["chosen_normalized_state"] for r in rd(P4/"structural_state_normalization.jsonl")}
    CFG=json.loads((ROOT/"config/phase4/motifs.core.json").read_text(encoding="utf-8"))
    motifs={m["id"]:m["generic_positions"] for m in CFG["motifs"]}
    metr_by=defaultdict(list)
    for m in MM:
        if m["metric_type"]=="distance" and m.get("value_used"):
            metr_by[(m["receptor_instance_id"],m["metric_name"])].append(
                m["primary_value_angstrom"] if m["value_used"]=="primary"
                else m["fallback_min_heavy_atom_angstrom"])
    rows=[]
    for level,keyfn in (("major_family",lambda r:(r["major_family_id"],)),
                        ("receptor_family",lambda r:(r["receptor_family_id"],)),
                        ("receptor",lambda r:(r["receptor_entry_name"],)),
                        ("structural_state",lambda r:(STATE.get(r["pdb_id"],"unknown"),))):
        grp=defaultdict(list)
        for r in MR: grp[keyfn(r)].append(r)
        for k,v in sorted(grp.items(),key=lambda kv:tuple(str(x) for x in kv[0])):
            insts={r["receptor_instance_id"] for r in v}
            for mid,pos in sorted(motifs.items()):
                sub=[r for r in v if r["generic_position"] in pos]
                st=Counter(r["observation_status"] for r in sub)
                mapped={r["receptor_instance_id"] for r in sub
                        if r["observation_status"].startswith("observed")}
                vals=[]
                for m in MM:
                    if (m["metric_type"]=="distance" and m.get("value_used")
                            and set(m["generic_positions"])<=set(pos)
                            and keyfn({"major_family_id":m["major_family_id"],
                                       "receptor_family_id":None,
                                       "receptor_entry_name":m["receptor_entry_name"],
                                       "pdb_id":m["pdb_id"]})==k if level in ("major_family","receptor") else False):
                        vals.append(m["primary_value_angstrom"] if m["value_used"]=="primary"
                                    else m["fallback_min_heavy_atom_angstrom"])
                vals=[x for x in vals if x is not None]
                rows.append({"level":level,"group_key":[str(x) for x in k],"motif_id":mid,
                    "generic_positions":pos,
                    "expected_structures":len(insts),
                    "mapped_structures":len(mapped),
                    "observed_structures":len(mapped),
                    "canonical_identity_count":st.get("observed_canonical_identity",0),
                    "noncanonical_identity_count":st.get("observed_noncanonical_identity",0),
                    "mutation_count":sum(1 for r in sub if r.get("mutation_flag")),
                    "coordinate_missing_count":st.get("coordinate_missing",0),
                    "generic_mapping_unresolved_count":st.get("generic_mapping_unresolved",0),
                    "expected_but_unresolved_count":st.get("expected_but_unresolved",0),
                    "metric_count":len(vals),
                    "median":f(statistics.median(vals)) if vals else None,
                    "iqr":f(statistics.quantiles(vals,n=4)[2]-statistics.quantiles(vals,n=4)[0])
                        if len(vals)>3 else None,
                    "range":[f(min(vals)),f(max(vals))] if vals else None,
                    "state_stratified":None,"transducer_stratified":None,
                    "site_class_stratified":None,
                    "coverage":f(len(mapped)/len(insts)) if insts else None,
                    "association_only":True})
    a=dump(AGG/"motif_summaries/motif_summary.jsonl",rows)
    (AGG/"motif_summaries/_manifest.json").write_text(json.dumps(
        {"generated_at":utc_now(),"rows":a["rows"],"motif_summaries_sha":a["content_sha256"],
         "interpretation":("motif differences are reported as associations between static "
                           "experimental structures and their source-annotated context; no "
                           "causal claim is made")},indent=1,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"rows":a["rows"],"levels":len({r['level'] for r in rows}),
                      "motifs":len(motifs)},indent=1))
    return 0
if __name__=="__main__": raise SystemExit(main())
