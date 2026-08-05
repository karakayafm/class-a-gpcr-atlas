#!/usr/bin/env python3
"""Phase 6A-3 — human curation package: universe, priorities, packets and workbooks.

Nothing here decides anything. It turns the open evidence items into material a person can act
on, and keeps every automated field separate from every human field.
"""
from __future__ import annotations
import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402
P4=ROOT/"data/intermediate/phase4"; P3=ROOT/"data/intermediate/phase3"
IN=ROOT/"data/intermediate"; CUR=ROOT/"curation"
def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def wcsv(path,cols,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=cols,extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow(r)
    return {"rows":len(rows),"columns":cols}

def main()->int:
    PRI=json.loads((ROOT/"config/phase6a/curation_priorities.json").read_text(encoding="utf-8"))
    rank={}; 
    for c in PRI["classes"]:
        for t in c["issue_types"]: rank[t]=(c["rank"],c["id"])
    UNIV=rd(P4/"canonical_review_universe.jsonl")
    ADJ={a["review_item_id"]:a for a in rd(P4/"evidence_adjudications.jsonl")}
    S={s["pdb_id"]:s for s in rd(IN/"structures.normalized.jsonl")}
    LC={l["ligand_entity_id"]:l for l in rd(IN/"ligand_candidates.jsonl")}
    RI=defaultdict(list)
    for r in rd(IN/"receptor_instances.jsonl"): RI[r["pdb_id"]].append(r)
    EI={i["entity_inventory_id"]:i for i in rd(IN/"entity_inventory.jsonl")}
    CM={c["pdb_id"]:c for c in rd(P3/"coordinate_manifest.jsonl")}
    ASM={a["pdb_id"]:a for a in rd(P4/"assembly_context_audit.jsonl")}
    SCR={s["ligand_entity_id"]:s for s in rd(P4/"site_class_remediation.jsonl")}
    REMED=defaultdict(list)
    for r in rd(P4/"mapping_remediation.jsonl"): REMED[r["pdb_id"]].append(r)
    CONF=rd(IN/"source_conflicts.jsonl")
    UNI=json.loads((ROOT/"data/normalized/class_a_structure_universe.json").read_text(encoding="utf-8"))
    PUB={u["pdb_id"]:u["gpcrdb_structure_record"].get("publication") for u in UNI["structures"]}
    todo=[u for u in UNIV if u["human_review_requirement"]=="required"]

    items=[]
    for u in sorted(todo,key=lambda x:x["review_item_id"]):
        best=min((rank.get(t,(9,"unclassified")) for t in u["issue_types"]),key=lambda x:x[0])
        a=ADJ.get(u["review_item_id"],{})
        pid=u["pdb_id"]; st=S.get(pid,{})
        le=u.get("ligand_entity_id"); lg=LC.get(le or "",{})
        items.append({"review_item_id":u["review_item_id"],"pdb_id":pid,
          "priority_rank":best[0],"priority_class":best[1],
          "issue_types":u["issue_types"],
          "receptor":st.get("receptor_name"),"receptor_entry_name":st.get("receptor_entry_name"),
          "species":st.get("species"),"major_family_id":st.get("major_family_id"),
          "ligand_entity_id":le,"structure_ligand_id":u.get("structure_ligand_id"),
          "ligand_name":((lg.get("source_annotations") or {}).get("gpcrdb_ligand") or {}).get("name"),
          "ligand_role":lg.get("ligand_role"),"binding_site_class":lg.get("binding_site_class"),
          "automated_proposal":u["automated_proposal"],
          "evidence_adjudication":a.get("evidence_adjudication"),
          "adjudication_basis":a.get("adjudication_basis"),
          "adjudication_confidence":a.get("adjudication_confidence"),
          "current_eligibility":u.get("current_eligibility"),
          "why_human_review_required":a.get("adjudication_basis") or u["automated_proposal"],
          "human_curator_decision":None,"human_review_status":"not_started"})

    # ------------------------------------------------------------------ packets
    made=0
    for it in items:
        pid=it["pdb_id"]; d=CUR/"packets"/it["review_item_id"].replace(":","_").replace("/","_")
        d.mkdir(parents=True,exist_ok=True)
        u=next(x for x in UNIV if x["review_item_id"]==it["review_item_id"])
        le=it["ligand_entity_id"]; lg=LC.get(le or "",{})
        inv=[EI[i] for i in (lg.get("entity_inventory_ids") or []) if i in EI]
        sources={"rcsb_entry":f"https://www.rcsb.org/structure/{pid}",
          "pdb_doi":f"https://doi.org/10.2210/pdb{pid}/pdb",
          "gpcrdb_structure":f"https://gpcrdb.org/structure/{pid}",
          "gpcrdb_receptor":(f"https://gpcrdb.org/protein/{it['receptor_entry_name']}/"
                             if it.get("receptor_entry_name") else None),
          "primary_publication":PUB.get(pid),
          "gtopdb":None,"chembl":None,"pubchem":None,
          "not_used_note":("GtoPdb, ChEMBL and PubChem were not called by the pipeline; a curator "
                           "may consult them and record the identifier used.")}
        packet={"review_item_id":it["review_item_id"],"pdb_id":pid,
          "issue_types":it["issue_types"],"priority_class":it["priority_class"],
          "receptor":it["receptor"],"receptor_entry_name":it["receptor_entry_name"],
          "species":it["species"],"major_family_id":it["major_family_id"],
          "ligand_entity_id":le,"ligand_name":it["ligand_name"],
          "ligand_role":it["ligand_role"],"binding_site_class":it["binding_site_class"],
          "chains_and_entities":{
            "receptor_instances":[{k:r[k] for k in ("receptor_instance_id","auth_asym_id",
               "polymer_entity_id","receptor_accession","mapping_confidence")}
               for r in RI.get(pid,[])],
            "ligand_entities":[{k:i.get(k) for k in ("entity_inventory_id","entity_form",
               "nonpolymer_comp_id","polymer_entity_id","auth_asym_ids","auth_seq_id",
               "entity_description","final_role")} for i in inv]},
          "automated_proposal":it["automated_proposal"],
          "evidence_adjudication":it["evidence_adjudication"],
          "adjudication_basis":it["adjudication_basis"],
          "adjudication_confidence":it["adjudication_confidence"],
          "current_eligibility":it["current_eligibility"],
          "why_human_review_is_required":it["why_human_review_required"],
          "automated_evidence":u["automated_evidence"],
          "sequence_mapping":{"mapping_outcomes":[{k:r[k] for k in ("receptor_instance_id",
              "mapping_route","route_sequence_agreement","outcome")} for r in REMED.get(pid,[])]},
          "coordinate_mapping":{"coordinate_available":
              CM.get(pid,{}).get("coordinate_availability"),
            "assembly_review":ASM.get(pid,{}).get("outcome"),
            "assembly_note":ASM.get(pid,{}).get("note")},
          "site_class_evidence":({k:SCR[le][k] for k in ("phase3_geometry_candidate",
              "contacted_segments","tm_contact_fraction","adjudication_basis")}
              if le in SCR else None),
          "source_conflicts":[c for c in CONF if c["pdb_id"]==pid],
          "sources":sources,
          "allowed_curator_decisions":["approve_automated_proposal","reject_automated_proposal",
            "replace_with_curator_value","metadata_only","exclude_from_aggregation",
            "unresolved_insufficient_evidence","defer_for_second_review"],
          "required_rationale_fields":["rationale","evidence_sources_used","confidence"],
          "evidence_excerpt_policy":("record a short sourced summary and a persistent identifier; "
                                     "do not paste long copyrighted text"),
          "human_curator_decision":None,"human_review_status":"not_started"}
        (d/"packet.json").write_text(json.dumps(packet,indent=1,ensure_ascii=False),encoding="utf-8")
        (d/"sources.json").write_text(json.dumps(sources,indent=1,ensure_ascii=False),encoding="utf-8")
        (d/"coordinate_snapshot_metadata.json").write_text(json.dumps({
            "pdb_id":pid,"coordinate_availability":CM.get(pid,{}).get("coordinate_availability"),
            "decompressed_sha256":CM.get(pid,{}).get("decompressed_sha256"),
            "viewer_bundle":f"data/web/structures/{pid}/viewer.cif",
            "assembly_review":ASM.get(pid,{}).get("outcome"),
            "note":"the deposited coordinates are read-only reference; nothing is regenerated here"},
            indent=1,ensure_ascii=False),encoding="utf-8")
        (d/"decision_template.json").write_text(json.dumps({
            "review_item_id":it["review_item_id"],"curator_name":None,
            "curator_affiliation":None,"curator_identifier":None,"review_date":None,
            "decision":None,"rationale":None,"evidence_sources_used":[],
            "confidence":None,"conflict_of_interest_note":None,
            "second_reviewer_required":False,"second_reviewer_name":None,
            "second_review_date":None,"agreement_status":None,"notes":None,
            "source_freeze_hash":None},indent=1,ensure_ascii=False),encoding="utf-8")
        md=[f"# Review item {it['review_item_id']}","",
            f"**PDB** {pid} · **Receptor** {it['receptor'] or '—'} ({it['species'] or '—'})","",
            f"**Priority** {it['priority_class']}","",
            "## Issue types","", *[f"- {t}" for t in it["issue_types"]],"",
            "## Why a human is needed","",str(it["why_human_review_required"] or "—"),"",
            "## What the pipeline proposed","",
            f"- automated proposal: {it['automated_proposal']}",
            f"- evidence adjudication: {it['evidence_adjudication']} "
            f"(confidence {it['adjudication_confidence']})",
            f"- current eligibility: {it['current_eligibility']}","",
            "This is a pipeline assessment made from sources. It is **not** human curation.","",
            "## Sources","",
            f"- RCSB entry: {sources['rcsb_entry']}",
            f"- PDB DOI: {sources['pdb_doi']}",
            f"- GPCRdb structure: {sources['gpcrdb_structure']}",
            f"- Primary publication: {sources['primary_publication'] or 'none recorded'}","",
            "## Allowed decisions","",
            *[f"- `{x}`" for x in packet["allowed_curator_decisions"]],"",
            "Record the decision in `decision_template.json` and validate it with",
            "`pipeline/phase6a/validate_curator_decisions.py`.",""]
        (d/"summary.md").write_text("\n".join(md),encoding="utf-8")
        made+=1

    # ------------------------------------------------------------------ workbooks
    cols=["review_item_id","pdb_id","priority_rank","priority_class","issue_types","receptor",
          "receptor_entry_name","species","major_family_id","ligand_entity_id","ligand_name",
          "ligand_role","binding_site_class","automated_proposal","evidence_adjudication",
          "adjudication_confidence","current_eligibility","why_human_review_required",
          "human_curator_decision","human_review_status"]
    rows=[{**r,"issue_types":";".join(r["issue_types"])} for r in items]
    a1=wcsv(CUR/"review_items.csv",cols,rows)
    dcols=["review_item_id","curator_name","curator_affiliation","curator_identifier",
           "review_date","decision","rationale","evidence_sources_used","confidence",
           "conflict_of_interest_note","second_reviewer_required","second_reviewer_name",
           "second_review_date","agreement_status","notes","source_freeze_hash"]
    a2=wcsv(CUR/"decision_template.csv",dcols,
            [{"review_item_id":r["review_item_id"]} for r in rows])
    pcols=["priority_class","priority_rank","items","distinct_pdbs","effect"]
    byp=defaultdict(list)
    for r in items: byp[(r["priority_rank"],r["priority_class"])].append(r)
    prows=[{"priority_class":k[1],"priority_rank":k[0],"items":len(v),
            "distinct_pdbs":len({x["pdb_id"] for x in v}),
            "effect":next((c["effect"] for c in PRI["classes"] if c["id"]==k[1]),"")}
           for k,v in sorted(byp.items())]
    a3=wcsv(CUR/"review_priority.csv",pcols,prows)
    ccols=["conflict_id","pdb_id","source_conflict_type","decision_status",
           "manual_review_required","source_values"]
    a4=wcsv(CUR/"source_conflicts.csv",ccols,
            [{**c,"source_values":json.dumps(c["source_values"],ensure_ascii=False)} for c in CONF])

    dd={"generated_at":utc_now(),"files":{
      "review_items.csv":{"rows":a1["rows"],"columns":{c:"" for c in cols}},
      "decision_template.csv":{"rows":a2["rows"],"columns":{c:"" for c in dcols}},
      "review_priority.csv":{"rows":a3["rows"],"columns":{c:"" for c in pcols}},
      "source_conflicts.csv":{"rows":a4["rows"],"columns":{c:"" for c in ccols}}}}
    for c,desc in [("review_item_id","canonical id; the join key for every decision"),
      ("priority_rank","1 aggregation identity, 2 interpretation, 3 metadata completeness"),
      ("issue_types","semicolon-separated canonical issue types"),
      ("automated_proposal","what the pipeline proposed; not a decision"),
      ("evidence_adjudication","pipeline adjudication from sources; NOT human curation"),
      ("human_curator_decision","empty until a person decides"),
      ("human_review_status","not_started | in_progress | completed")]:
        dd["files"]["review_items.csv"]["columns"][c]=desc
    for c,desc in [("curator_name","required; a decision without it is not finalised"),
      ("decision","one of the allowed values for the issue type"),
      ("rationale","required free text"),("evidence_sources_used","semicolon-separated identifiers"),
      ("confidence","high | medium | low"),
      ("source_freeze_hash","the Phase 4 output-manifest hash the decision was made against")]:
        dd["files"]["decision_template.csv"]["columns"][c]=desc
    (CUR/"DATA_DICTIONARY.json").write_text(json.dumps(dd,indent=1,ensure_ascii=False),encoding="utf-8")

    summary={"generated_at":utc_now(),"human_review_required_items":len(items),
      "packets_written":made,
      "by_priority":{f"{k[0]}:{k[1]}":len(v) for k,v in sorted(byp.items())},
      "by_issue_type":dict(Counter(t for r in items for t in r["issue_types"])),
      "distinct_pdbs":len({r["pdb_id"] for r in items}),
      "distinct_families":len({r["major_family_id"] for r in items}),
      "items_sha256":content_sha256(items)}
    (CUR/"_curation_summary.json").write_text(json.dumps(summary,indent=1,ensure_ascii=False),
                                              encoding="utf-8")
    print(json.dumps(summary,indent=1,ensure_ascii=False))
    return 0
if __name__=="__main__": raise SystemExit(main())
