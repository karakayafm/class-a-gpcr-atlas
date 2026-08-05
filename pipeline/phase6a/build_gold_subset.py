#!/usr/bin/env python3
"""Phase 6A-3 — stratified gold-review subset plan. A sampling plan only; it contains no decisions."""
from __future__ import annotations
import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
P4=ROOT/"data/intermediate/phase4"; IN=ROOT/"data/intermediate"; CUR=ROOT/"curation"
def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def main()->int:
    items=[]
    with (CUR/"review_items.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r["issue_types"]=r["issue_types"].split(";"); items.append(r)
    S={s["pdb_id"]:s for s in rd(IN/"structures.normalized.jsonl")}
    LC={l["ligand_entity_id"]:l for l in rd(IN/"ligand_candidates.jsonl")}
    ANO={a["pdb_id"] for a in rd(P4/"annotated_not_observed.jsonl")}
    ASM={a["pdb_id"]:a for a in rd(P4/"assembly_context_audit.jsonl")}
    fams=sorted({s["major_family_id"] for s in S.values()})
    def strata(it):
        out=set(); pid=it["pdb_id"]; st=S.get(pid,{})
        out.add("family:"+(it["major_family_id"] or "?"))
        lg=LC.get(it["ligand_entity_id"] or "",{})
        sc=lg.get("binding_site_class")
        if sc=="canonical_7tm_pocket": out.add("small_molecule_pocket")
        if sc in ("extracellular_polymer_interface","tethered_ligand_interface"): out.add("polymer_interface")
        if sc=="covalent_core_site": out.add("covalent_ligand")
        if sc=="unresolved": out.add("unresolved_site_class")
        if st.get("ligand_status")=="multi_ligand_bound": out.add("multi_ligand")
        if st.get("apo_status")=="confirmed_apo": out.add("apo")
        if pid in ANO: out.add("annotated_not_observed")
        if "generic_mapping_unvalidated" in it["issue_types"] or "receptor_mapping" in it["issue_types"]:
            out.add("unresolved_mapping")
        if ASM.get(pid,{}).get("outcome")=="ambiguous_human_review_required": out.add("assembly_ambiguity")
        if "tethered_ligand_candidate" in it["issue_types"]: out.add("tethered_ligand_candidate")
        if any(t.startswith("source_conflict") for t in it["issue_types"]): out.add("source_conflict")
        if st.get("construct_engineering_status") in ("chimeric_fusion","mutations_reported"):
            out.add("mutation_or_construct_complexity")
        return out
    need=["small_molecule_pocket","polymer_interface","covalent_ligand","multi_ligand","apo",
          "annotated_not_observed","unresolved_site_class","unresolved_mapping",
          "assembly_ambiguity","tethered_ligand_candidate","source_conflict",
          "mutation_or_construct_complexity"]+["family:"+f for f in fams]
    pool=[(it,strata(it)) for it in items]
    coverage=Counter(s for _,ss in pool for s in ss)
    # greedy cover: hardest strata first, then top up to a balanced quota per family
    chosen={}; per_stratum=defaultdict(list)
    for st in sorted(need,key=lambda s:coverage.get(s,0)):
        got=[it for it,ss in pool if st in ss]
        quota=2 if coverage.get(st,0)>=2 else coverage.get(st,0)
        for it in sorted(got,key=lambda x:(int(x["priority_rank"]),x["review_item_id"]))[:quota]:
            chosen[it["review_item_id"]]=it
            per_stratum[st].append(it["review_item_id"])
    for f in fams:
        got=[it for it,ss in pool if ("family:"+f) in ss and it["review_item_id"] not in chosen]
        for it in sorted(got,key=lambda x:(int(x["priority_rank"]),x["review_item_id"]))[:2]:
            chosen[it["review_item_id"]]=it
    # A control arm. Measuring the pipeline only on items it could NOT settle would measure the
    # hard tail and call it performance. Strata that produce no open review item — because the
    # pipeline resolved them cleanly — are represented here by RESOLVED items, so a reviewer can
    # test whether those resolutions were right.
    UNIV=rd(P4/"canonical_review_universe.jsonl")
    ADJ={a["review_item_id"]:a for a in rd(P4/"evidence_adjudications.jsonl")}
    open_ids={i["review_item_id"] for i in items}
    control=[]
    resolved=[u for u in UNIV if u["review_item_id"] not in open_ids]
    def rstrata(u):
        out=set(); pid=u["pdb_id"]; st=S.get(pid,{})
        out.add("family:"+(st.get("major_family_id") or "?"))
        lg=LC.get(u.get("ligand_entity_id") or "",{})
        sc=lg.get("binding_site_class")
        if sc=="canonical_7tm_pocket": out.add("small_molecule_pocket")
        if sc in ("extracellular_polymer_interface","tethered_ligand_interface"): out.add("polymer_interface")
        if sc=="covalent_core_site": out.add("covalent_ligand")
        if st.get("ligand_status")=="multi_ligand_bound": out.add("multi_ligand")
        if st.get("apo_status")=="confirmed_apo": out.add("apo")
        if pid in ANO: out.add("annotated_not_observed")
        if ASM.get(pid,{}).get("outcome")=="ambiguous_human_review_required": out.add("assembly_ambiguity")
        if any(t.startswith("source_conflict") for t in u["issue_types"]): out.add("source_conflict")
        return out
    uncovered=[s for s in need if not per_stratum.get(s)]
    for st in uncovered:
        got=[u for u in resolved if st in rstrata(u)]
        for u in sorted(got,key=lambda x:x["review_item_id"])[:2]:
            if u["review_item_id"] in chosen: continue
            a=ADJ.get(u["review_item_id"],{})
            control.append({"review_item_id":u["review_item_id"],"pdb_id":u["pdb_id"],
              "major_family_id":S.get(u["pdb_id"],{}).get("major_family_id"),
              "priority_class":"control_resolved_item",
              "issue_types":";".join(u["issue_types"]),
              "strata":";".join(sorted(rstrata(u))),
              "second_review_recommended":"no",
              "selection_reason":("control arm: the pipeline reports this as "
                f"{a.get('evidence_adjudication')}; the reviewer tests whether that is right")})
    # A second control tier. Some strata are absent from the review universe entirely — no item,
    # open or resolved, ever touched them. That is not evidence they are correct; it means no
    # check ever looked. Those are sampled straight from the underlying records so the blind
    # spot is reviewed rather than recorded as "not representable".
    covered_now=set()
    for it in chosen.values(): covered_now.update(strata(it))
    for r in control: covered_now.update(r["strata"].split(";"))
    unflagged=[]
    still=[s for s in need if s not in covered_now]
    seen_u={u["review_item_id"] for u in UNIV}
    for st in still:
        cand=[]
        for lid,lg in sorted(LC.items()):
            sc=lg.get("binding_site_class"); pid=lg.get("pdb_id"); tags=set()
            if sc=="canonical_7tm_pocket": tags.add("small_molecule_pocket")
            if sc=="covalent_core_site": tags.add("covalent_ligand")
            if sc in ("extracellular_polymer_interface","tethered_ligand_interface"): tags.add("polymer_interface")
            tags.add("family:"+(S.get(pid,{}).get("major_family_id") or "?"))
            if st in tags: cand.append((lid,lg,tags))
        for lid,lg,tags in cand[:2]:
            unflagged.append({"review_item_id":"UNFLAGGED:"+lid,"pdb_id":lg.get("pdb_id"),
              "major_family_id":S.get(lg.get("pdb_id"),{}).get("major_family_id"),
              "priority_class":"control_unflagged_record",
              "issue_types":"","strata":";".join(sorted(tags)),
              "second_review_recommended":"no",
              "selection_reason":("control arm: no review item of any kind covers this stratum, "
                f"so the {st} path has never been checked; sampled from ligand_candidates directly")})
    rows=[]
    for rid,it in sorted(chosen.items()):
        ss=dict(pool)[it] if False else strata(it)
        rows.append({"review_item_id":rid,"pdb_id":it["pdb_id"],
          "major_family_id":it["major_family_id"],"priority_class":it["priority_class"],
          "issue_types":";".join(it["issue_types"]),
          "strata":";".join(sorted(ss)),
          "second_review_recommended":"yes" if int(it["priority_rank"])==1 else "no",
          "selection_reason":"stratified coverage; not selected for ease"})
    rows.extend(control); rows.extend(unflagged)
    cols=["review_item_id","pdb_id","major_family_id","priority_class","issue_types","strata",
          "second_review_recommended","selection_reason"]
    with (CUR/"gold_subset_plan.csv").open("w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=cols); w.writeheader(); w.writerows(rows)
    missing=[s for s in need if not any(s in r["strata"].split(";") for r in rows)]
    n_control=len(control); n_unflagged=len(unflagged)
    second=sum(1 for r in rows if r["second_review_recommended"]=="yes")
    plan={"total_review_items":len(items),"gold_subset_size":len(rows),
      "fraction_of_queue":round(len(rows)/max(len(items),1),3),
      "strata_required":len(need),"strata_covered":len(need)-len(missing),
      "strata_not_representable":missing,
      "open_review_items_sampled":len(chosen),
      "control_resolved_items_sampled":n_control,
      "control_unflagged_records_sampled":n_unflagged,
      "blind_spot_note":("covalent_core_site holds 45 ligand entities and contributes 0 review "
        "items; the review universe never examined it, so it is sampled directly"),
      "control_arm_rationale":("strata with no open item are represented by items the pipeline "
        "reports as resolved, so performance is not measured only on the hard tail"),
      "second_review_recommended":second,
      "estimated_reviews":len(rows)+second,
      "workload_note":("each item ships as a self-contained packet; a reviewer familiar with the "
        "data should expect minutes rather than hours per item, but that estimate is not "
        "measured and should be calibrated on the first ten"),
      "full_queue_workload":{"items":len(items),
        "priority_1":sum(1 for i in items if i["priority_rank"]=="1"),
        "priority_2":sum(1 for i in items if i["priority_rank"]=="2"),
        "priority_3":sum(1 for i in items if i["priority_rank"]=="3")},
      "contains_decisions":False,
      "purpose":("sampling plan for an independent performance evaluation; no performance figure "
                 "may be computed until these items carry human decisions")}
    (CUR/"gold_subset_plan.json").write_text(json.dumps(plan,indent=1,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(plan,indent=1,ensure_ascii=False))
    return 0
if __name__=="__main__": raise SystemExit(main())
