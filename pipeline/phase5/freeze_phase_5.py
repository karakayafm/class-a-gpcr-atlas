#!/usr/bin/env python3
"""Phase 5 freeze."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.canonical import canonical_dumps, content_sha256, write_json  # noqa: E402
from common.http import utc_now                                          # noqa: E402
WEB=ROOT/"data/web"; APP=ROOT/"app"; REL=ROOT/"releases/phase5"
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def agg(d): return hashlib.sha256(canonical_dumps(d).encode()).hexdigest()
def main()->int:
    m=json.loads((WEB/"global/manifest.json").read_text(encoding="utf-8"))
    inputs={}
    for label,rel in [("phase1_freeze","data/freezes/phase_1/freeze.json"),
                      ("phase2_freeze","releases/phase2/freeze.json"),
                      ("phase3_output_manifest","releases/phase3/OUTPUT_MANIFEST.json"),
                      ("phase4_output_manifest","releases/phase4/OUTPUT_MANIFEST.json")]:
        inputs[label]={"content_sha256":content_sha256(json.loads((ROOT/rel).read_text(encoding="utf-8")))}
    inputs["frozen_aminergic_manifest"]={"sha256":sha(ROOT/"_checksums_before.sha256"),
        "files":len((ROOT/"_checksums_before.sha256").read_text().strip().split("\n"))}
    payloads={str(p.relative_to(WEB)):{"bytes":p.stat().st_size,"sha256":sha(p)}
              for p in sorted(WEB.rglob("*.json")) if "structures" not in p.parts}
    fam={}
    for f in m["families"]:
        files={}
        d=WEB/"families"/f["slug"]
        for p in sorted(d.rglob("*")):
            if p.is_file(): files[str(p.relative_to(d))]={"bytes":p.stat().st_size,"sha256":sha(p)}
        fam[f["slug"]]={"family_id":f["family_id"],"files":files,"chain":agg(files)}
    bundles={}
    bi=json.loads((ROOT/"data/intermediate/phase5/_bundle_index.json").read_text(encoding="utf-8"))
    for b in bi["bundles"]: bundles[b["pdb_id"]]=b["sha256"]
    assets={}
    for p in sorted(APP.rglob("*")):
        if p.is_file() and p.suffix in (".html",".css",".js"):
            assets[str(p.relative_to(APP))]=sha(p)
    sb=json.loads((ROOT/"data/intermediate/phase5/_site_build.json").read_text(encoding="utf-8"))
    val=json.loads((ROOT/"reports/phase5/validation_results.json").read_text(encoding="utf-8"))
    bro=json.loads((ROOT/"reports/phase5/browser_results.json").read_text(encoding="utf-8")) \
        if (ROOT/"reports/phase5/browser_results.json").exists() else {"total":0,"failed":0}
    named={"global_manifest_sha":sha(WEB/"global/manifest.json"),
      "landing_payload_sha":sha(WEB/"global/landing.json"),
      "global_payloads_sha":agg({k:v["sha256"] for k,v in payloads.items() if k.startswith("global/")}),
      "family_payloads_sha":agg({k:v["chain"] for k,v in fam.items()}),
      "structure_bundles_sha":agg(bundles),
      "app_assets_sha":agg(assets),
      "site_build_sha":agg(sb.get("asset_hashes",{})),
      "offline_exports_sha":agg({e["family_slug"]:e["bytes"] for e in sb["offline_families"]}),
      "phase5_manifest_sha":agg({"inputs":inputs,"payloads":payloads,"assets":assets})}
    REL.mkdir(parents=True,exist_ok=True)
    write_json(REL/"INPUT_MANIFEST.json",{"generated_at":utc_now(),"inputs":inputs,
        "note":"Phase 5 consumes the Phase 4 freeze; no scientific value is recomputed."})
    write_json(REL/"OUTPUT_MANIFEST.json",{"generated_at":utc_now(),"payloads":payloads,
        "site":sb["site"],"offline_families":sb["offline_families"]})
    write_json(REL/"PAYLOAD_HASHES.json",{"generated_at":utc_now(),"payloads":payloads})
    write_json(REL/"FAMILY_PAYLOAD_HASHES.json",{"generated_at":utc_now(),"families":fam})
    write_json(REL/"STRUCTURE_BUNDLE_HASHES.json",{"generated_at":utc_now(),
        "count":len(bundles),"bundles":bundles})
    write_json(REL/"ASSET_HASHES.json",{"generated_at":utc_now(),"assets":assets,
        "vendored":{"ngl.js":{"sha256":sha(APP/"vendor/ngl.js"),
          "source":"https://unpkg.com/ngl@2.3.1/dist/ngl.js","licence":"MIT"}}})
    (REL/"NAMED_HASHES.txt").write_text("\n".join(f"{v}  {k}" for k,v in sorted(named.items()))+"\n",
                                        encoding="utf-8")
    (REL/"VALIDATION_REPORT.md").write_text(
      f"# Phase 5 validation\n\nStatic: {val['total']} checks, {val['failed']} failed.\n"
      f"Browser: {bro['total']} checks, {bro['failed']} failed.\n\n"
      + "\n".join(f"- {c['group']} :: {c['name']} — {c['result']}" for c in val["checks"])+"\n",
      encoding="utf-8")
    lines=[]
    for base in (WEB,APP,ROOT/"schemas/phase5",ROOT/"pipeline/phase5",REL):
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.name!="checksums.sha256" and "structures" not in p.parts:
                lines.append(f"{sha(p)}  {p.relative_to(ROOT)}")
    (REL/"checksums.sha256").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"named_hashes":len(named),"payloads":len(payloads),
                      "families":len(fam),"bundles":len(bundles),"assets":len(assets),
                      "checksummed_files":len(lines)},indent=1))
    return 0
if __name__=="__main__": raise SystemExit(main())
