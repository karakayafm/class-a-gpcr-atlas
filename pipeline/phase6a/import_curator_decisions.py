#!/usr/bin/env python3
"""Import validated curator decisions into data/curation/, with an audit log.

The Phase 4 scientific freeze is NOT modified. Decisions accumulate in a separate layer; a
curated science freeze is a later, explicitly authorised step.

    python3 pipeline/phase6a/import_curator_decisions.py <file> [--curator-batch NAME]
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.canonical import content_sha256   # noqa: E402
from common.http import utc_now               # noqa: E402
PEND=ROOT/"data/curation/pending"; VALID=ROOT/"data/curation/validated"
AUDIT=ROOT/"data/curation/audit_log.jsonl"

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("files",nargs="+")
    ap.add_argument("--curator-batch",default=None)
    ap.add_argument("--promote",action="store_true",
                    help="move from pending to validated after a clean validation run")
    a=ap.parse_args()
    PEND.mkdir(parents=True,exist_ok=True); VALID.mkdir(parents=True,exist_ok=True)
    r=subprocess.run([sys.executable,str(ROOT/"pipeline/phase6a/validate_curator_decisions.py"),
                      *a.files],capture_output=True,text=True,cwd=str(ROOT))
    print(r.stdout)
    if r.returncode!=0:
        print("validation failed; nothing was imported",file=sys.stderr); return r.returncode
    report=json.loads(r.stdout or "{}")
    batch=a.curator_batch or ("batch_"+utc_now().replace(":","").replace("-","")[:15])
    recs=[]
    for f in a.files:
        p=Path(f)
        if p.suffix==".json":
            d=json.loads(p.read_text(encoding="utf-8")); recs+= d if isinstance(d,list) else [d]
        else:
            import csv
            with p.open(encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if row.get("curator_name"): recs.append(row)
    if not recs:
        print("no decision rows found"); return 0
    dest=(VALID if a.promote else PEND)/f"{batch}.json"
    if dest.exists():
        print(f"{dest} already exists; refusing to overwrite",file=sys.stderr); return 3
    dest.write_text(json.dumps(recs,indent=1,ensure_ascii=False),encoding="utf-8")
    entry={"timestamp":utc_now(),"batch":batch,"destination":str(dest.relative_to(ROOT)),
      "records":len(recs),"files":a.files,"promoted":bool(a.promote),
      "validation":{"validated":report.get("validated"),"finalised":report.get("finalised"),
                    "problems":report.get("problems")},
      "phase4_freeze":report.get("current_phase4_freeze"),
      "records_sha256":content_sha256(recs),
      "note":"the Phase 4 scientific freeze is unchanged by this import"}
    with AUDIT.open("a",encoding="utf-8") as fh:
        fh.write(json.dumps(entry,ensure_ascii=False)+"\n")
    print(json.dumps(entry,indent=1,ensure_ascii=False))
    return 0
if __name__=="__main__": raise SystemExit(main())
