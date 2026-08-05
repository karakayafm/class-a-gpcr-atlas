#!/usr/bin/env python3
"""Validate curator decision records. Never writes a decision; only checks one.

    python3 pipeline/phase6a/validate_curator_decisions.py <file.json|file.csv> [...]
"""
from __future__ import annotations
import csv, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.schema import validate            # noqa: E402
from common.canonical import content_sha256   # noqa: E402
AI_NAMES=("claude","gpt","chatgpt","copilot","gemini","llama","ai assistant","bot","pipeline",
          "automated","script")

def load(path: Path):
    if path.suffix==".json":
        d=json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d,list) else [d]
    rows=[]
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r={k:(v if v!="" else None) for k,v in r.items()}
            if r.get("evidence_sources_used"):
                r["evidence_sources_used"]=[x.strip() for x in r["evidence_sources_used"].split(";") if x.strip()]
            else: r["evidence_sources_used"]=[]
            for b in ("second_reviewer_required",):
                if r.get(b) is not None:
                    r[b]=str(r[b]).strip().lower() in ("true","1","yes","evet")
                else: r[b]=False
            rows.append(r)
    return rows

def main()->int:
    if len(sys.argv)<2:
        print(__doc__); return 2
    schema=json.loads((ROOT/"schemas/phase6a/curator_decision.schema.json").read_text(encoding="utf-8"))
    allowed=schema["allowed_decisions_by_issue_type"]
    items={r["review_item_id"]:r for r in (json.loads(l) for l in
        (ROOT/"curation/review_items.csv").with_suffix(".csv").read_text(encoding="utf-8").splitlines()[:0])} if False else {}
    with (ROOT/"curation/review_items.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            items[r["review_item_id"]]={"issue_types":r["issue_types"].split(";")}
    freeze=content_sha256(json.loads((ROOT/"releases/phase4/OUTPUT_MANIFEST.json").read_text(encoding="utf-8")))
    prev={}
    vdir=ROOT/"data/curation/validated"
    if vdir.exists():
        for p in sorted(vdir.glob("*.json")):
            for d in json.loads(p.read_text(encoding="utf-8")):
                prev[d["review_item_id"]]=p.name
    problems=[]; ok=[]; seen=Counter()
    for arg in sys.argv[1:]:
        path=Path(arg)
        for rec in load(path):
            rid=rec.get("review_item_id")
            if not rid: problems.append({"file":str(path),"error":"missing review_item_id"}); continue
            if all(rec.get(k) in (None,"") for k in ("curator_name","decision")):
                continue      # an untouched template row is not an error
            seen[rid]+=1
            errs=[e for e in validate(rec,schema)]
            if rid not in items: errs.append("unknown review_item_id")
            if rec.get("curator_name") and any(a in rec["curator_name"].lower() for a in AI_NAMES):
                errs.append("curator_name looks like an automated system; a human is required")
            if rec.get("decision") and rid in items:
                allow=set()
                for t in items[rid]["issue_types"]: allow|=set(allowed.get(t,[]))
                if allow and rec["decision"] not in allow:
                    errs.append(f"decision {rec['decision']} not allowed for {items[rid]['issue_types']}")
            if rec.get("decision")=="replace_with_curator_value" and not rec.get("curator_value"):
                errs.append("replace_with_curator_value requires curator_value")
            if rec.get("second_reviewer_required") and not (rec.get("second_reviewer_name")
                                                            and rec.get("agreement_status")):
                errs.append("second review requested but reviewer/agreement missing")
            if rec.get("source_freeze_hash") and rec["source_freeze_hash"]!=freeze:
                errs.append("source_freeze_hash does not match the current Phase 4 freeze")
            if seen[rid]>1: errs.append("duplicate decision for this review item")
            if rid in prev: errs.append(f"a validated decision already exists in {prev[rid]}; "
                                        "overwriting silently is not allowed")
            (problems if errs else ok).append({"review_item_id":rid,"file":str(path),
                                               "errors":errs} if errs else rec)
    finalised=[r for r in ok if r.get("curator_name") and r.get("review_date")]
    out={"validated":len(ok),"finalised":len(finalised),"problems":len(problems),
         "problem_detail":problems[:20],"current_phase4_freeze":freeze}
    print(json.dumps(out,indent=1,ensure_ascii=False))
    return 1 if problems else 0
if __name__=="__main__": raise SystemExit(main())
