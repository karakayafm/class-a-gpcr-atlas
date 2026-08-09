#!/usr/bin/env python3
"""Phase 5D — assemble the static site and the per-family offline exports.

Two export shapes exist and are named honestly:
  * site                     — the full atlas, served over HTTP
  * portable family folder   — one family, its payloads and its 3D bundles, opened from a folder

A single-file HTML export is NOT produced: the smallest family already carries 1.6 MB of
coordinates and the largest 86 MB, so embedding them would be a performance problem wearing the
name "self-contained".
"""
from __future__ import annotations
import hashlib, json, shutil, sys
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.canonical import content_sha256   # noqa: E402
from common.http import utc_now               # noqa: E402
APP=ROOT/"app"; WEB=ROOT/"data/web"; REL=ROOT/"releases/phase5"

def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def copy_app(dst: Path, payload_base: str, offline_family: str | None = None):
    dst.mkdir(parents=True, exist_ok=True)
    for sub in ("css","js","vendor","assets"):
        s=APP/sub
        if s.exists():
            if (dst/sub).exists(): shutil.rmtree(dst/sub)
            shutil.copytree(s,dst/sub)
    html=(APP/"index.html").read_text(encoding="utf-8")
    html=html.replace('data-payload-base="../data/web/"', f'data-payload-base="{payload_base}"')
    if offline_family:
        html=html.replace('<body ', f'<body data-offline-family="{offline_family}" ')
    (dst/"index.html").write_text(html,encoding="utf-8")

def main()->int:
    m=json.loads((WEB/"global/manifest.json").read_text(encoding="utf-8"))
    S={s["pdb_id"]:s for s in rd(ROOT/"data/intermediate/structures.normalized.jsonl")}
    fam_pdbs=defaultdict(list)
    for s in S.values(): fam_pdbs[s["major_family_id"]].append(s["pdb_id"])

    # ---------------- full site -------------------------------------------------------------
    site=REL/"site"
    if site.exists(): shutil.rmtree(site)
    copy_app(site,"data/web/")
    shutil.copytree(WEB,site/"data/web")
    site_files=sorted(p for p in site.rglob("*") if p.is_file())
    asset_hashes={str(p.relative_to(site)):sha(p) for p in site_files
                  if p.suffix in (".html",".css",".js")}

    # ---------------- offline family folders -------------------------------------------------
    off=REL/"offline_families"
    if off.exists(): shutil.rmtree(off)
    exports=[]
    for f in m["families"]:
        slug=f["slug"]; fid=f["family_id"]
        d=off/slug
        copy_app(d,"data/web/",offline_family=slug)
        (d/"data/web/global").mkdir(parents=True,exist_ok=True)
        # a single-family manifest so the shell never advertises families it does not carry
        gm=json.loads(json.dumps(m))
        gm["families"]=[f]; gm["family_count"]=1
        gm["offline_export"]=True; gm["offline_family"]=slug
        gm["cross_family_comparison_available"]=False
        gm["offline_note_en"]=("Cross-family comparison is disabled in a single-family offline "
                               "export, because only one family's data is bundled.")
        gm["offline_note_tr"]=("Çevrimdışı aile dışa aktarımında aileler arası karşılaştırma "
                               "devre dışıdır, çünkü yalnız tek bir ailenin verisi paketlenmiştir.")
        (d/"data/web/global/manifest.json").write_text(
            json.dumps(gm,sort_keys=True,separators=(",",":"),ensure_ascii=False),encoding="utf-8")
        land=json.loads((WEB/"global/landing.json").read_text(encoding="utf-8"))
        land["families"]=[x for x in land["families"] if x["family_slug"]==slug]
        land["family_count"]=1
        (d/"data/web/global/landing.json").write_text(
            json.dumps(land,sort_keys=True,separators=(",",":"),ensure_ascii=False),encoding="utf-8")
        for g in ("motif_catalogue.json","sources.json","references.json","release_metadata.json",
                  "panels.json",
                  "cross_family_summary.json"):
            shutil.copy2(WEB/"global"/g, d/"data/web/global"/g)
        shutil.copytree(WEB/"families"/slug, d/"data/web/families"/slug)
        (d/"data/web/structures").mkdir(parents=True,exist_ok=True)
        for pid in sorted(fam_pdbs[fid]):
            src=WEB/"structures"/pid
            if src.exists(): shutil.copytree(src, d/"data/web/structures"/pid)
        total=sum(p.stat().st_size for p in d.rglob("*") if p.is_file())
        exports.append({"family_id":fid,"family_slug":slug,"family_name":f["name"],
          "export_type":"portable_family_folder",
          "entry":"index.html","opens_from":"file:// double-click, or any static server",
          "structures":len(fam_pdbs[fid]),
          "bytes":total,"megabytes":round(total/1e6,1),
          "cross_family_comparison":"disabled",
          "single_file_html":False,
          "single_file_reason":("coordinate bundles for this family total "
            f"{round(sum((WEB/'structures'/p/'viewer.cif').stat().st_size for p in fam_pdbs[fid] if (WEB/'structures'/p/'viewer.cif').exists())/1e6,1)} MB; "
            "embedding them in one HTML file would be a performance problem, so the export is "
            "a portable folder and is named as one")})

    idx={"generated_at":utc_now(),"site":{"path":"releases/phase5/site",
          "entry":"releases/phase5/site/index.html",
          "files":len(site_files),
          "bytes":sum(p.stat().st_size for p in site_files)},
         "offline_families":exports,
         "asset_hashes":asset_hashes}
    (ROOT/"data/intermediate/phase5"/"_site_build.json").write_text(
        json.dumps(idx,indent=1,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"site_files":len(site_files),
        "site_mb":round(idx["site"]["bytes"]/1e6,1),
        "offline_families":len(exports),
        "offline_total_mb":round(sum(e["bytes"] for e in exports)/1e6,1),
        "smallest":min(exports,key=lambda e:e["bytes"])["family_slug"],
        "largest":max(exports,key=lambda e:e["bytes"])["family_slug"]},indent=1))
    return 0
if __name__=="__main__": raise SystemExit(main())
