#!/usr/bin/env python3
"""Phase 6A-1 — release-candidate build.

The RC is assembled from the Phase 5 source and the Phase 5 payloads. No scientific value is
recomputed: this stage copies, hashes and records. Timestamped logs are kept out of the
deterministic hash set so two RC builds of the same input are byte-identical.

    python3 pipeline/phase6a/build_rc.py [--rc rc1]
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.canonical import canonical_dumps, content_sha256, write_json  # noqa: E402
from common.http import utc_now                                          # noqa: E402
P5=ROOT/"releases/phase5"; WEB=ROOT/"data/web"; APP=ROOT/"app"
RC_VERSION="0.1.0-rc.10"
PUBLIC_VERSION="0.1.0-beta.1"
PROJECT_TITLE="Class A GPCR Structure\u2013Ligand Contact and Interface Atlas"
SHORT_NAME="Class A GPCR Contact Atlas"

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def agg(d): return hashlib.sha256(canonical_dumps(d).encode()).hexdigest()

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--rc",default="rc1"); a=ap.parse_args()
    RC=ROOT/"releases/phase6a"/a.rc
    for sub in ("site","offline_families","manifests","reports","test_logs"):
        d=RC/sub
        if d.exists() and sub in ("site","offline_families"): shutil.rmtree(d)
        d.mkdir(parents=True,exist_ok=True)

    # --- verify the Phase 5 freeze before copying anything ---------------------------------
    n5={k.strip():v for v,k in (l.split("  ",1) for l in
        (P5/"NAMED_HASHES.txt").read_text().strip().split("\n"))}
    checks={"global_manifest_sha":sha(WEB/"global/manifest.json"),
            "landing_payload_sha":sha(WEB/"global/landing.json")}
    mismatch=[k for k,v in checks.items() if n5.get(k)!=v]
    if mismatch:
        print("Phase 5 freeze mismatch:",mismatch,file=sys.stderr); return 2

    shutil.copytree(P5/"site",RC/"site",dirs_exist_ok=True)
    shutil.copytree(P5/"offline_families",RC/"offline_families",dirs_exist_ok=True)

    # --- third-party notices ----------------------------------------------------------------
    # The vendored NGL bundle is MIT-licensed and carries no copyright header of its own, so
    # shipping it without a notice file fails the licence's one obligation. The notice travels
    # with every copy of the software, which means the offline exports too.
    tpn=APP/"THIRD_PARTY_NOTICES.md"
    if not tpn.exists():
        print("THIRD_PARTY_NOTICES.md missing; refusing to build a release candidate",
              file=sys.stderr); return 3
    shutil.copy2(tpn,RC/"site"/"THIRD_PARTY_NOTICES.md")
    for d in (RC/"offline_families").iterdir():
        if d.is_dir(): shutil.copy2(tpn,d/"THIRD_PARTY_NOTICES.md")
    # The copyright holder is confirmed, so the licences are now effective and must travel with
    # every copy of the work — including each offline export, which is a complete distribution.
    for f in ("LICENSE","LICENSE-DATA","LICENSE-NOTICE.md","LICENSE-SCOPE.json"):
        src=ROOT/f
        if not src.exists():
            print(f"{f} missing; refusing to build",file=sys.stderr); return 4
        shutil.copy2(src,RC/"site"/f)
        for d in (RC/"offline_families").iterdir():
            if d.is_dir(): shutil.copy2(src,d/f)

    lic=ROOT/"data/licences/third_party"
    if lic.is_dir():
        shutil.copytree(lic,RC/"site"/"licences",dirs_exist_ok=True)

    # --- stamp the RC version into the release metadata the app already reads ---------------
    for base in [RC/"site"]+[p for p in (RC/"offline_families").iterdir() if p.is_dir()]:
        rm=base/"data/web/global/release_metadata.json"
        if not rm.exists(): continue
        d=json.loads(rm.read_text(encoding="utf-8"))
        d["release_candidate"]=RC_VERSION
        d["public_version"]=PUBLIC_VERSION
        # The owner selected licences; they are not yet effective, because a grant needs a
        # grantor and the copyright holder is unconfirmed. The metadata says exactly that
        # rather than either claiming a licence or continuing to report "undecided".
        d["code_licence"]="PolyForm-Noncommercial-1.0.0"
        d["code_licence_status"]="approved_by_copyright_holder"
        d["copyright_holder"]="Muhammed Fatih Karakaya"
        d["copyright_notice"]="Copyright © 2026 Muhammed Fatih Karakaya"
        d["copyright_status"]=("owner_declared_under_the_university_policy_for_"
            "student-authored_scientific_works")
        d["affiliation"]="Cancer Signaling Laboratory, Boğaziçi University"
        d["institution"]="Boğaziçi University"
        d["acknowledgement"]=("Developed as part of research conducted at the Cancer Signaling "
            "Laboratory, Boğaziçi University.")
        d["contact_email"]="edu.mfatih@gmail.com"
        d["licence_texts_unmodified"]=True
        d["scientific_beta_gate"]="passed_with_disclosed_open_review_items"
        d["stable_curated_release_gate"]="pending"
        d["licence_files"]=["LICENSE","LICENSE-DATA","LICENSE-NOTICE.md","LICENSE-SCOPE.json"]
        d["data_licence"]="CC-BY-NC-4.0"
        d["data_licence_scope"]=("project-created outputs only; source-derived material retains "
            "its source licence")
        d["commercial_use"]="requires separate written permission from the copyright holder"
        d["open_source_status"]="source_available_noncommercial_not_OSI_open_source"
        d["licence_effective"]=True
        # Supersede the Phase 5 wording: it was written while the licence and redistribution
        # gates were open, and both are now closed. Leaving it would have the site state a
        # condition that no longer exists.
        d["pre_release_notice_en"]=("Pre-release research build. Scientific claims are not yet "
            "human-reviewed; see Methods for scope and limitations.")
        d["pre_release_notice_tr"]=("Ön-sürüm araştırma derlemesi. Bilimsel sonuçlar henüz insan "
            "incelemesinden geçmemiştir; kapsam ve sınırlamalar için Yöntemler bölümüne bakın.")
        d["release_gates"]=[
            {"gate":"code_licence","status":"closed",
             "note":"PolyForm Noncommercial 1.0.0, approved by the copyright holder."},
            {"gate":"derived_data_licence","status":"closed",
             "note":"CC BY-NC 4.0 on project-created outputs; source-derived fields retain their source licences."},
            {"gate":"public_redistribution","status":"closed",
             "note":"Approved by the copyright holder."},
            {"gate":"human_curation","status":"open",
             "note":"189 review items await human decision; pooled beta summaries are review-gated."}]
        d["licence_note_en"]=("Project-created code is under PolyForm Noncommercial 1.0.0 and "
            "project-created data under CC BY-NC 4.0. Roughly 92% of this distribution by size is "
            "CC0 coordinate data from the RCSB PDB, which these licences do not cover. See "
            "LICENSE-SCOPE.json.")
        d["licence_note_tr"]=("Proje tarafından üretilen kod PolyForm Noncommercial 1.0.0, veri "
            "ise CC BY-NC 4.0 altındadır. Bu dağıtımın boyut olarak yaklaşık %92'si RCSB PDB'den "
            "gelen CC0 koordinat verisidir ve bu lisansların kapsamı dışındadır. Bkz. "
            "LICENSE-SCOPE.json.")
        d["licence_scope"]=[
            {"path_prefix":"data/web/structures/","governing_licence":"CC0 1.0 (RCSB PDB)",
             "project_licence_applies":False},
            {"path_prefix":"vendor/","governing_licence":"MIT / BSD-3-Clause / Apache-2.0",
             "project_licence_applies":False},
            {"path_prefix":"data/web/families/","governing_licence":
             "CC BY-NC 4.0 for project-created values; GPCRdb-derived fields remain CC BY 4.0",
             "project_licence_applies":True},
            {"path_prefix":"data/web/overlay/","governing_licence":"CC BY-NC 4.0",
             "project_licence_applies":True},
            {"path_prefix":"js/","governing_licence":"PolyForm-Noncommercial-1.0.0",
             "project_licence_applies":True}]
        d["release_candidate_note_en"]=("Local release candidate. Not a Git tag, not a public "
            "release, carries no DOI, and is not a final version.")
        d["release_candidate_note_tr"]=("Yerel sürüm adayı. Git etiketi değildir, kamuya açık "
            "sürüm değildir, DOI taşımaz ve nihai sürüm değildir.")
        rm.write_text(json.dumps(d,sort_keys=True,separators=(",",":"),ensure_ascii=False),
                      encoding="utf-8")

    for base in [RC/"site"]+[p for p in (RC/"offline_families").iterdir() if p.is_dir()]:
        rf=base/"data/web/global/references.json"
        if not rf.exists(): continue
        d=json.loads(rf.read_text(encoding="utf-8"))
        d.setdefault("atlas",{}).update({"title":PROJECT_TITLE,"short_name":SHORT_NAME,
            "version":PUBLIC_VERSION,"release_candidate":RC_VERSION,
            "phase5_artefact_version":"5.0.0-pre","review_gate":"applied",
            "review_gate_rule_version":"phase6a1-review-gating-1.0.0"})
        rf.write_text(json.dumps(d,sort_keys=True,separators=(",",":"),ensure_ascii=False),
                      encoding="utf-8")

    # Phase 6A.1 overlay: review-gated public-beta aggregates and the validation disclosure.
    # Copied into the release layer, never into the Phase 5 payload tree.
    ovw=ROOT/"data/release_overlays/rc6/web"
    if ovw.is_dir():
        shutil.copytree(ovw,RC/"site"/"data/web/overlay",dirs_exist_ok=True)
        for d in (RC/"offline_families").iterdir():
            if not d.is_dir(): continue
            fam=d.name
            (d/"data/web/overlay/global").mkdir(parents=True,exist_ok=True)
            for g in (ovw/"global").glob("*.json"):
                shutil.copy2(g,d/"data/web/overlay/global"/g.name)
            src=ovw/"families"/fam
            if src.is_dir():
                shutil.copytree(src,d/"data/web/overlay/families"/fam,dirs_exist_ok=True)
        for f in ("review_impact.jsonl","beta_exclusion_summary.json","overlay_manifest.json",
                  "family_validation_status.json","beta_contact_prevalence.jsonl",
                  "structure_slot_eligibility.jsonl","beta_aggregation_units.jsonl",
                  "beta_coverage.jsonl","beta_interface_summaries.jsonl",
                  "beta_motif_context.jsonl"):
            s=ROOT/"data/release_overlays/rc6"/f
            if s.exists():
                (RC/"overlay_data").mkdir(parents=True,exist_ok=True)
                shutil.copy2(s,RC/"overlay_data"/f)
        shutil.copy2(ROOT/"governance/REVIEW_GATING_POLICY.json",RC/"overlay_data")

    payloads={}; bundles={}; assets={}; offline={}
    site=RC/"site"
    for p in sorted(site.rglob("*")):
        if not p.is_file(): continue
        rel=str(p.relative_to(site))
        if "/structures/" in "/"+rel: 
            if p.name=="viewer.cif": bundles[p.parent.name]=sha(p)
            continue
        if p.suffix in (".html",".css",".js",".md",".txt"): assets[rel]=sha(p)
        elif p.suffix==".json": payloads[rel]=sha(p)
    for d in sorted((RC/"offline_families").iterdir()):
        if d.is_dir():
            files={str(x.relative_to(d)):sha(x) for x in sorted(d.rglob("*")) if x.is_file()}
            offline[d.name]={"files":len(files),"bytes":sum(x.stat().st_size for x in d.rglob("*") if x.is_file()),
                             "chain":agg(files)}
    named={"rc_payloads_sha":agg(payloads),"rc_assets_sha":agg(assets),
           "rc_bundles_sha":agg(bundles),"rc_offline_sha":agg(offline),
           "rc_site_sha":agg({**payloads,**assets}),
           "phase5_global_manifest_sha":checks["global_manifest_sha"],
           "rc_manifest_sha":agg({"payloads":payloads,"assets":assets,
                                  "bundles":bundles,"offline":offline})}
    M=RC/"manifests"
    write_json(RC/"INPUT_MANIFEST.json",{"generated_at":utc_now(),"rc_version":RC_VERSION,
      "inputs":{"phase5_named_hashes":n5,
        "phase1_freeze":content_sha256(json.loads((ROOT/"data/freezes/phase_1/freeze.json").read_text(encoding="utf-8"))),
        "phase2_freeze":content_sha256(json.loads((ROOT/"releases/phase2/freeze.json").read_text(encoding="utf-8"))),
        "phase3_output_manifest":content_sha256(json.loads((ROOT/"releases/phase3/OUTPUT_MANIFEST.json").read_text(encoding="utf-8"))),
        "phase4_output_manifest":content_sha256(json.loads((ROOT/"releases/phase4/OUTPUT_MANIFEST.json").read_text(encoding="utf-8")))},
      "note":"No scientific value is recomputed in Phase 6A; the RC is assembled from Phase 5."})
    write_json(RC/"OUTPUT_MANIFEST.json",{"generated_at":utc_now(),"rc_version":RC_VERSION,
      "site_files":sum(1 for p in site.rglob('*') if p.is_file()),
      "site_bytes":sum(p.stat().st_size for p in site.rglob('*') if p.is_file()),
      "payloads":len(payloads),"assets":len(assets),"bundles":len(bundles),
      "offline_families":len(offline)})
    write_json(RC/"PAYLOAD_HASHES.json",{"rc_version":RC_VERSION,"payloads":payloads})
    write_json(RC/"ASSET_HASHES.json",{"rc_version":RC_VERSION,"assets":assets,
      "vendored":{"ngl.js":{"sha256":sha(APP/"vendor/ngl.js"),
        "source":"https://unpkg.com/ngl@2.3.1/dist/ngl.js","licence":"MIT","version":"2.3.1",
        "modified":False}}})
    write_json(RC/"BUNDLE_HASHES.json",{"rc_version":RC_VERSION,"count":len(bundles),"bundles":bundles})
    write_json(RC/"OFFLINE_EXPORT_HASHES.json",{"rc_version":RC_VERSION,"exports":offline})
    (RC/"NAMED_HASHES.txt").write_text("\n".join(f"{v}  {k}" for k,v in sorted(named.items()))+"\n",
                                       encoding="utf-8")
    # checksums exclude timestamped reports and logs so the RC hash stays deterministic
    lines=[]
    for base in (site,RC/"offline_families"):
        for p in sorted(base.rglob("*")):
            if p.is_file(): lines.append(f"{sha(p)}  {p.relative_to(RC)}")
    (RC/"checksums.sha256").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"rc":a.rc,"version":RC_VERSION,"payloads":len(payloads),
      "assets":len(assets),"bundles":len(bundles),"offline_families":len(offline),
      "checksummed":len(lines),"named":named},indent=1))
    return 0
if __name__=="__main__": raise SystemExit(main())
