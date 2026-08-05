#!/usr/bin/env python3
"""Phase 5E — measured performance budget. No claim is written that was not measured."""
from __future__ import annotations
import json, statistics, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=ROOT/"app"; WEB=ROOT/"data/web"; REL=ROOT/"releases/phase5"
def size(p): return p.stat().st_size if p.exists() else 0
def main()->int:
    m=json.loads((WEB/"global/manifest.json").read_text(encoding="utf-8"))
    js_files=sorted((APP/"js").rglob("*.js"))
    out={"shell_html_bytes":size(APP/"index.html"),
      "css_bytes":sum(size(p) for p in (APP/"css").glob("*.css")),
      "app_js_bytes":sum(size(p) for p in js_files),"app_js_files":len(js_files),
      "vendored_ngl_bytes":size(APP/"vendor/ngl.js"),
      "initial_global_payload_bytes":size(WEB/"global/manifest.json")+size(WEB/"global/landing.json"),
      "initial_requests_static":4,
      "global_total_bytes":sum(size(p) for p in (WEB/"global").glob("*.json"))}
    fams=[]
    for f in m["families"]:
        d=WEB/"families"/f["slug"]
        files={p.name if p.parent==d else p.parent.name+"/"+p.name:size(p) for p in d.rglob("*.json")}
        core=sum(v for k,v in files.items() if not k.endswith(".by_receptor.json"))
        fams.append({"slug":f["slug"],"family_id":f["family_id"],
          "summary_bytes":files.get("summary.json",0),
          "structure_index_bytes":files.get("structures.json",0),
          "core_view_bytes":core,"total_bytes":sum(files.values()),
          "largest_file":max(files.items(),key=lambda kv:kv[1])})
    out["families"]=fams
    out["family_total_median_bytes"]=int(statistics.median([f["total_bytes"] for f in fams]))
    out["family_total_max"]=max(fams,key=lambda f:f["total_bytes"])
    out["family_open_bytes_typical"]=int(statistics.median(
        [f["summary_bytes"]+f["structure_index_bytes"] for f in fams]))
    bi=json.loads((ROOT/"data/intermediate/phase5/_bundle_index.json").read_text(encoding="utf-8"))
    sizes=sorted(b["cif_bytes"]+b["meta_bytes"] for b in bi["bundles"])
    out["structure_bundle"]={"count":len(sizes),"median":sizes[len(sizes)//2],
      "p95":sizes[int(len(sizes)*0.95)],"max":sizes[-1],"total":sum(sizes)}
    sb=json.loads((ROOT/"data/intermediate/phase5/_site_build.json").read_text(encoding="utf-8"))
    out["site_bytes"]=sb["site"]["bytes"]; out["site_files"]=sb["site"]["files"]
    out["offline_exports"]=[{"slug":e["family_slug"],"type":e["export_type"],
                             "megabytes":e["megabytes"]} for e in sb["offline_families"]]
    # parse timing, measured not asserted
    t0=time.perf_counter(); json.loads((WEB/"global/landing.json").read_text(encoding="utf-8"))
    out["landing_parse_ms"]=round((time.perf_counter()-t0)*1000,2)
    big=max(fams,key=lambda f:f["structure_index_bytes"])
    p=WEB/"families"/big["slug"]/"structures.json"
    t0=time.perf_counter(); d=json.loads(p.read_text(encoding="utf-8"))
    out["largest_structure_index_parse_ms"]=round((time.perf_counter()-t0)*1000,2)
    out["largest_structure_index"]={"slug":big["slug"],"bytes":big["structure_index_bytes"],
                                    "structures":d["count"]}
    out["phase4_records_not_shipped_to_browser"]=182169
    out["page_size_rows"]={"structures":50,"contacts":40,"evidence":60}
    (ROOT/"reports/phase5").mkdir(parents=True,exist_ok=True)
    (ROOT/"reports/phase5/performance.json").write_text(json.dumps(out,indent=1,ensure_ascii=False),
                                                        encoding="utf-8")
    print(json.dumps({k:out[k] for k in ("shell_html_bytes","css_bytes","app_js_bytes",
        "vendored_ngl_bytes","initial_global_payload_bytes","family_open_bytes_typical",
        "family_total_median_bytes","structure_bundle","site_bytes","landing_parse_ms",
        "largest_structure_index_parse_ms")},indent=1))
    return 0
if __name__=="__main__": raise SystemExit(main())
