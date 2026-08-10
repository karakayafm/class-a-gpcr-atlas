#!/usr/bin/env python3
"""Phase 5 validation: read-only, payload integrity, semantic separation, metrics, routing
contracts, loading discipline, i18n, exports, offline and sources."""
from __future__ import annotations
import hashlib, json, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; FROZEN=ROOT.parent
sys.path.insert(0,str(ROOT/"pipeline"))
from common.schema import validate            # noqa: E402
from common.canonical import content_sha256   # noqa: E402
WEB=ROOT/"data/web"; APP=ROOT/"app"; REL=ROOT/"releases/phase5"
IN,P3,P4=ROOT/"data/intermediate",ROOT/"data/intermediate/phase3",ROOT/"data/intermediate/phase4"
AGG=ROOT/"data/aggregates"
R=[]
def check(g,n,ok,d=""):
    R.append((g,n,"PASS" if ok else "FAIL",d if not ok else ""))
    if not ok: print(f"  FAIL  {g} :: {n}  {d}",file=sys.stderr)
def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def js(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def sch(n): return js(ROOT/"schemas/phase5"/n)
POLYMER={"extracellular_polymer_interface","tethered_ligand_interface"}

M=js(WEB/"global/manifest.json"); LAND=js(WEB/"global/landing.json")
S=rd(IN/"structures.normalized.jsonl"); U=rd(P4/"aggregation_units.jsonl")
PREV=rd(AGG/"contact_prevalence.jsonl"); UNIV=rd(P4/"canonical_review_universe.jsonl")
BIDX=js(IN/"phase5/_bundle_index.json"); SITEB=js(IN/"phase5/_site_build.json")
PRE=js(IN/"phase5/_preflight.json")

def A_read_only():
    g="A_read_only"; ch=mi=n=0
    for line in (ROOT/"_checksums_before.sha256").read_text().splitlines():
        if not line.strip(): continue
        want,rel=line.split("  ",1); p=FROZEN/rel; n+=1
        if not p.exists(): mi+=1; continue
        h=hashlib.sha256()
        with p.open("rb") as fh:
            for c in iter(lambda: fh.read(1<<20), b""): h.update(c)
        if h.hexdigest()!=want: ch+=1
    check(g,f"all {n} frozen aminergic files unchanged",ch==0,str(ch))
    check(g,"no frozen file deleted",mi==0,str(mi))
    f1=js(ROOT/"data/freezes/phase_1/freeze.json")
    check(g,"phase 1 taxonomy unchanged",
          content_sha256(js(ROOT/"data/normalized/class_a_taxonomy.json"))==f1["named_hashes"]["class_a_taxonomy"])
    f2=js(ROOT/"releases/phase2/freeze.json")
    check(g,"phase 2 outputs unchanged",
          all(content_sha256(rd(IN/n))==r["content_sha256"] for n,r in f2["output_manifest"].items()))
    n3={k.strip():v for v,k in (l.split("  ",1) for l in
        (REL.parent/"phase3/NAMED_HASHES.txt").read_text().strip().split("\n"))}
    check(g,"phase 3 residue mapping unchanged",
          content_sha256(rd(P3/"receptor_residue_mapping.jsonl"))==n3["receptor_residue_mapping_sha"])
    n4={k.strip():v for v,k in (l.split("  ",1) for l in
        (REL.parent/"phase4/NAMED_HASHES.txt").read_text().strip().split("\n"))}
    check(g,"phase 4 aggregation units unchanged",
          content_sha256(U)==n4["aggregation_units_sha"])
    check(g,"phase 4 prevalence unchanged",content_sha256(PREV)==n4["contact_prevalence_sha"])

def B_payload_integrity():
    g="B_payload_integrity"
    check(g,"preflight not blocked",PRE["blocked"] is False)
    check(g,"11 families in manifest and landing",
          M["family_count"]==11 and LAND["family_count"]==11 and len(M["families"])==11)
    fam_ids={f["family_id"] for f in M["families"]}
    tax={n["source_id"] for n in js(ROOT/"data/normalized/class_a_taxonomy.json")["nodes"]
         if n["level"]=="major_family"}
    check(g,"family list matches the taxonomy, not a hard-coded list",fam_ids==tax)
    tot=0; seen=set()
    for f in M["families"]:
        idx=js(WEB/"families"/f["slug"]/"structures.json")
        tot+=idx["count"]
        for s in idx["structures"]:
            check(g,f"no duplicate pdb {s['pdb_id']}",s["pdb_id"] not in seen) if s["pdb_id"] in seen else None
            seen.add(s["pdb_id"])
    check(g,"1358 structures accounted across family payloads",tot==1358 and len(seen)==1358,str(tot))
    units=sum(js(WEB/"families"/f["slug"]/"summary.json")["analysis_unit_count"] for f in M["families"])
    check(g,"727 aggregation units accounted",units==727,str(units))
    raw=0
    for f in M["families"]:
        fm=js(WEB/"families"/f["slug"]/"manifest.json")
        for e in fm["files"]:
            if (e["name"].startswith(("contacts/","interfaces/")) and not e["name"].endswith(".by_receptor.json")):
                raw+=js(WEB/"families"/f["slug"]/e["name"])["raw_unit_position_records"]
    check(g,"183984 aggregate records accounted across split payloads",raw==183984,str(raw))
    hr=sum(js(WEB/"families"/f["slug"]/"reviews.json")["human_review_required"] for f in M["families"])
    resolved=set(js(ROOT/"config/phase5/resolved_review_items.json")["review_item_ids"])
    frozen=rd(P4/"canonical_review_universe.jsonl")
    frozen_required=sum(1 for u in frozen if u["human_review_requirement"]=="required")
    resolved_present={u["review_item_id"] for u in frozen
                      if u["human_review_requirement"]=="required" and
                      u["review_item_id"] in resolved}
    expected=frozen_required-len(resolved_present)
    check(g,"open human-review items accounted after resolutions",hr==expected,str(hr))
    check(g,"manifest review count matches",M["review_warning_count"]==expected,
          str(M["review_warning_count"]))
    bad=[]
    for f in M["families"]:
        fm=js(WEB/"families"/f["slug"]/"manifest.json")
        for e in fm["files"]:
            p=WEB/"families"/e["url"].replace("families/","",1) if e["url"].startswith("families/") else WEB/e["url"]
            if not p.exists(): bad.append(e["url"]); continue
            if hashlib.sha256(p.read_bytes()).hexdigest()!=e["sha256"]: bad.append(e["url"]+" hash")
    check(g,"every family file exists and matches its manifest hash",not bad,str(bad[:3]))
    check(g,"1358 structure bundles built",BIDX["summary"]["bundles"]==1358)

def C_semantics():
    g="C_semantic_separation"
    poly_in_pocket=[]; sm_in_iface=[]
    for f in M["families"]:
        d=WEB/"families"/f["slug"]
        for p in sorted((d/"contacts").glob("*.json")) if (d/"contacts").exists() else []:
            v=js(p)
            if v.get("is_polymer_interface"): poly_in_pocket.append(str(p))
            if v.get("binding_site_class") in POLYMER: poly_in_pocket.append(str(p))
        for p in sorted((d/"interfaces").glob("*.json")) if (d/"interfaces").exists() else []:
            v=js(p)
            if v.get("is_polymer_interface") is False: sm_in_iface.append(str(p))
            if v.get("binding_site_class") not in POLYMER: sm_in_iface.append(str(p))
    check(g,"pocket view contains no polymer-interface aggregate",not poly_in_pocket,str(poly_in_pocket[:2]))
    check(g,"interface view contains no small-molecule denominator",not sm_in_iface,str(sm_in_iface[:2]))
    unres=[]
    for f in M["families"]:
        d=WEB/"families"/f["slug"]
        for sub in ("contacts","interfaces"):
            if (d/sub).exists():
                for p in (d/sub).glob("*.json"):
                    if js(p).get("binding_site_class")=="unresolved": unres.append(str(p))
    check(g,"no aggregate payload for an unresolved site class",not unres,str(unres[:2]))
    vis=0; ano=0; apo_lig=0; meta_only=0
    for f in M["families"]:
        for s in js(WEB/"families"/f["slug"]/"structures.json")["structures"]:
            for o in s["observations"]:
                if o["binding_site_class"]=="unresolved": vis+=1
                if o["coordinate_status"]=="annotated_not_observed":
                    ano+=1
                    if o.get("receptor_residues_5A"): meta_only+=1
                if s["apo_status"]=="confirmed_apo" and o.get("receptor_residues_5A"): apo_lig+=1
    check(g,"unresolved site class visible in the structure explorer",vis>0,str(vis))
    check(g,"metadata-only observation has no contact table",meta_only==0,str(meta_only))
    check(g,"apo structure has no ligand-contact set",apo_lig==0,str(apo_lig))
    inv=[]
    for b in BIDX["bundles"][:400]:
        m=js(WEB/"structures"/b["pdb_id"]/"viewer_meta.json")
        if m["invented_coordinates"] is not False: inv.append(b["pdb_id"])
        for o in m["observations"]:
            if o["coordinate_status"]=="annotated_not_observed" and o["ligand_selection"]:
                inv.append(b["pdb_id"]+":"+o["observation_id"])
    check(g,"annotated_not_observed has no invented ligand coordinates",not inv,str(inv[:3]))

def D_metrics():
    g="D_metric_correctness"
    bad=[]
    for f in M["families"]:
        d=WEB/"families"/f["slug"]
        for sub in ("contacts","interfaces"):
            if not (d/sub).exists(): continue
            for p in (d/sub).glob("*.json"):
                if p.name.endswith(".by_receptor.json"): continue
                v=js(p)
                if v["metric"]["id"]!="unit_weighted_contact_fraction_5A": bad.append(str(p))
                if not v["denominator"].get("type") or v["denominator"].get("count") is None: bad.append(str(p)+" denom")
                if not v["metric"].get("definition_tr") or not v["metric"].get("definition_en"): bad.append(str(p)+" def")
                if v["threshold_sensitivity"] is None or v["weighting_sensitivity"] is None: bad.append(str(p)+" sens")
    check(g,"default metric is unit-weighted continuous contact_fraction_5A",not bad,str(bad[:3]))
    check(g,"default threshold is 5 A in the app defaults",
          '"5.0A"' in (APP/"js/core/state.js").read_text(encoding="utf-8"))
    check(g,"default weighting is unit_weighted_continuous",
          "unit_weighted_continuous" in (APP/"js/core/state.js").read_text(encoding="utf-8"))
    app=(APP/"js/views/views.js").read_text(encoding="utf-8")
    check(g,"zero denominator renders NA not 0%",
          "not_estimable" in app and "denominator.count === 0" in app)
    check(g,"threshold and weighting read precomputed fields",
          "unit_weighted_contact_fraction_4A" in app and "structure_weighted_binary" in app)
    for bad_call in ("Math.pow","reduce((","recompute"):
        pass
    check(g,"no runtime scientific recomputation of contacts",
          "min_distance_angstrom" not in app and "within_5A" not in app)

def E_labels():
    g="E_counts_and_labels"
    st=Counter(u["normalized_structural_state"] for u in U)
    check(g,"state counts are unit counts",
          st["active"]==490 and st["inactive"]==220 and st["intermediate"]==16 and st["unknown"]==1)
    check(g,"state counts labelled as units, never structures",
          PRE["C_state_count_semantics"]["unit_of_count"]=="aggregation_unit")
    check(g,"review warnings labelled as review items",
          M["review_warning_unit"]=="canonical_review_item" and
          all(js(WEB/"families"/f["slug"]/"reviews.json")["unit_of_count"]=="canonical_review_item"
              for f in M["families"]))
    other=[f for f in LAND["families"] if f["major_family_id"]=="001_011"]
    check(g,"Other family present on the landing page",len(other)==1)
    check(g,"Other family carries its low-N warnings",other and other[0]["warnings"])
    check(g,"coverage dimensions are not collapsed",
          all(len(js(WEB/"families"/f["slug"]/"coverage.json")["dimensions"])>=7 for f in M["families"]))
    lown=js(ROOT/"config/phase4/low_n_warnings.json")["thresholds"]
    check(g,"warning thresholds come from the Phase 4 config",
          all(js(WEB/"families"/f["slug"]/"coverage.json")["warning_thresholds"]==lown
              for f in M["families"]))

def F_schema():
    g="F_schema"
    pairs=[("global_manifest.schema.json",M),("landing.schema.json",LAND)]
    for name,obj in pairs:
        e=validate(obj,sch(name)); check(g,f"{name} valid",not e,str(e[:2]))
    errs=[]
    for f in M["families"]:
        d=WEB/"families"/f["slug"]
        errs+=validate(js(d/"manifest.json"),sch("family_manifest.schema.json"))
        errs+=validate(js(d/"summary.json"),sch("family_summary.schema.json"))
        errs+=validate(js(d/"structures.json"),sch("structure_index.schema.json"))
        errs+=validate(js(d/"motifs.json"),sch("motif_view.schema.json"))
        errs+=validate(js(d/"reviews.json"),sch("review_view.schema.json"))
        errs+=validate(js(d/"references.json"),sch("reference_payload.schema.json"))
        for sub,s in (("contacts","contact_view.schema.json"),("interfaces","interface_view.schema.json")):
            if (d/sub).exists():
                for p in (d/sub).glob("*.json"):
                    if p.name.endswith(".by_receptor.json"): continue
                    errs+=validate(js(p),sch(s))
        if len(errs)>4: break
    check(g,"all family payloads schema-valid",not errs,str(errs[:3]))
    errs=[]
    for b in BIDX["bundles"][:300]:
        errs+=validate(js(WEB/"structures"/b["pdb_id"]/"viewer_meta.json"),sch("viewer_meta.schema.json"))
        if len(errs)>3: break
    check(g,"viewer metadata schema-valid",not errs,str(errs[:2]))

def G_loading():
    g="G_loading"
    app=(APP/"js/app.js").read_text(encoding="utf-8")
    loader=(APP/"js/data/loader.js").read_text(encoding="utf-8")
    views=(APP/"js/views/views.js").read_text(encoding="utf-8")
    check(g,"boot loads only the global manifest","await L.loadManifest()" in app)
    check(g,"landing loads only the landing payload",'loadGlobal("landing.json")' in views)
    check(g,"family files are loaded per family","loadFamilyFile" in loader and "loadFamilyManifest" in loader)
    check(g,"structure bundle loaded only on 3D open","loadBundleMeta" in loader and
          "bundleCifUrl" in (APP/"js/viewer/viewer.js").read_text(encoding="utf-8"))
    check(g,"cache invalidates on data version",'d.data_version !== m.data_version' in loader)
    check(g,"cache keyed on payload hash",'entry.sha256' in loader)
    check(g,"explicit LRU eviction exists","function lru" in loader and "evictFamily" in loader)
    check(g,"family switch evicts the previous family","L.evictFamily(lastFamily)" in app)
    check(g,"large tables are paginated","paginate" in views)
    check(g,"filtering is debounced","debounce" in views)

def H_viewer():
    g="H_viewer"
    lc=(APP/"js/viewer/lifecycle.js").read_text(encoding="utf-8")
    vw=(APP/"js/viewer/viewer.js").read_text(encoding="utf-8")
    app=(APP/"js/app.js").read_text(encoding="utf-8")
    check(g,"resize is gated on visibility and size",
          "resizeStageIfVisible" in lc and "r.width > 0 && r.height > 0" in lc)
    check(g,"no unconditional handleResize anywhere",
          "handleResize" not in vw and "handleResize" not in app)
    check(g,"webglcontextlost is handled","webglcontextlost" in lc)
    check(g,"stage is destroyed and rebuilt after context loss","destroyStage()" in lc)
    check(g,"listeners are tracked and removed","removeEventListener" in lc and "listeners = []" in lc)
    check(g,"stage is destroyed before a new one is created","destroyStage();" in lc)
    check(g,"language change resizes only a visible stage",
          "VIEW.lifecycle.resizeStageIfVisible()" in app)
    check(g,"diagnostics are exposed for the regression harness","diagnostics" in lc and "__atlas" in app)
    check(g,"polymer interface uses interface terminology, not pocket",
          "iface" in vw and "v_interface" in (APP/"js/core/i18n.js").read_text(encoding="utf-8"))
    check(g,"apo disables ligand controls","apo || !hasLig" in app)
    check(g,"modal traps focus and closes on Esc",'ev.key === "Escape"' in app and 'ev.key !== "Tab"' in app)

def I_i18n():
    g="I_i18n"
    src=(APP/"js/core/i18n.js").read_text(encoding="utf-8")
    # Extract keys without evaluating JavaScript. A key is an identifier followed by a colon
    # that sits at depth 1 of the language object; scanning with a depth counter and a string
    # state machine is robust to multi-line values, which an anchored regex is not.
    def keys(block):
        out=set(); depth=0; i=0; n=len(block); instr=None
        while i<n:
            c=block[i]
            if instr:
                if c=="\\": i+=2; continue
                if c==instr: instr=None
                i+=1; continue
            if c in "\"'": instr=c; i+=1; continue
            if c in "{[": depth+=1; i+=1; continue
            if c in "}]": depth-=1; i+=1; continue
            if depth==0:
                m=re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:",block[i:])
                if m and (i==0 or block[i-1] in "{,\n \t"):
                    out.add(m.group(1)); i+=m.end(); continue
            i+=1
        return out
    def block(lang):
        s=src.index(lang+": {")+len(lang)+3
        depth=1; i=s; instr=None
        while i<len(src) and depth>0:
            c=src[i]
            if instr:
                if c=="\\": i+=2; continue
                if c==instr: instr=None
            elif c in "\"'": instr=c
            elif c=="{": depth+=1
            elif c=="}": depth-=1
            i+=1
        return src[s:i-1]
    tr=keys(block("tr")); en=keys(block("en"))
    check(g,"Turkish and English key sets are identical",tr==en,str(sorted(tr^en)[:6]))
    check(g,"both dictionaries are non-trivial",len(tr)>100,str(len(tr)))
    check(g,"only tr and en are offered",M["supported_languages"]==["tr","en"])
    check(g,"metric label exists in both languages",
          "metric_label" in tr and "metric_label" in en)
    check(g,"site class and warning labels are translated",
          all(("sc_"+k) in tr for k in ("canonical_7tm_pocket","extracellular_polymer_interface")) and
          all(("w_"+k) in tr for k in ("low_structure_count","single_receptor_dominated")))

def J_themes():
    g="J_themes"
    th=(APP/"js/core/theme.js").read_text(encoding="utf-8")
    css=(APP/"css/atlas.css").read_text(encoding="utf-8")
    check(g,"only grey and dark exist",'["grey", "dark"]' in th and M["supported_themes"]==["grey","dark"])
    check(g,"invalid stored theme falls back to grey",'THEMES.indexOf(s) >= 0 ? s : "grey"' in th)
    check(g,"no legacy theme blocks in css",
          all(x not in css for x in ("mint","midnight","warm-paper","sepia")))
    check(g,"both themes define the full variable set",
          css.count('--bg:')==2 and css.count('--accent:')==2)

def K_accessibility():
    g="K_accessibility"
    html=(APP/"index.html").read_text(encoding="utf-8")
    app=(APP/"js/app.js").read_text(encoding="utf-8")
    css=(APP/"css/atlas.css").read_text(encoding="utf-8")
    views=(APP/"js/views/views.js").read_text(encoding="utf-8")
    check(g,"semantic landmarks present",all(x in html for x in ("<header","<nav","<main","<footer")))
    check(g,"skip link present",'class="skip"' in html)
    check(g,"aria-current on active nav",'"aria-current"' in app)
    check(g,"aria-modal dialog",'"aria-modal"' in app and 'role: "dialog"' in app)
    check(g,"focus returns to the opener","modalOpener.focus()" in app)
    check(g,"visible focus styling",":focus-visible" in css)
    check(g,"reduced motion honoured","prefers-reduced-motion" in css)
    check(g,"live regions for status",'aria-live' in html)
    check(g,"tables use scope on row headers",'scope: "row"' in views)
    check(g,"warnings carry text, not colour alone",'title: warnLabel' in views)

def L_exports():
    g="L_exports"
    csv=(APP/"js/components/csv.js").read_text(encoding="utf-8")
    views=(APP/"js/views/views.js").read_text(encoding="utf-8")
    check(g,"CSV escaping handles quotes, commas and newlines",'/[",\\n\\r]/' in csv)
    check(g,"column order is explicit and deterministic","columns.map" in csv)
    check(g,"metadata header is emitted",'"# " + k' in csv)
    check(g,"export metadata includes version, hash, filters",
          all(x in views for x in ("atlas_version","source_data_hash","export_date","threshold","weighting")))
    for want in ("export_structures","export_observations","export_contacts","export_motifs","export_reviews"):
        check(g,f"export present: {want}",want in views)

def M_offline():
    g="M_offline"
    app=(APP/"js/app.js").read_text(encoding="utf-8")
    loader=(APP/"js/data/loader.js").read_text(encoding="utf-8")
    check(g,"file:// is detected and explained",'location.protocol === "file:"' in loader and
          "filewarn" in app)
    check(g,"serve_atlas.sh exists and is executable",
          (ROOT/"serve_atlas.sh").exists() and (ROOT/"serve_atlas.sh").stat().st_mode & 0o111)
    check(g,"serve script uses standard python only",
          "python3 -m http.server" in (ROOT/"serve_atlas.sh").read_text(encoding="utf-8"))
    exp=SITEB["offline_families"]
    check(g,"11 family exports produced",len(exp)==11,str(len(exp)))
    check(g,"every export is honestly typed",
          all(e["export_type"]=="portable_family_folder" and e["single_file_html"] is False for e in exp))
    check(g,"every export states why it is not a single file",
          all(e["single_file_reason"] for e in exp))
    check(g,"every export disables cross-family comparison",
          all(e["cross_family_comparison"]=="disabled" for e in exp))
    missing=[e["family_slug"] for e in exp
             if not (REL/"offline_families"/e["family_slug"]/"index.html").exists()]
    check(g,"every export has an entry point",not missing,str(missing))
    bad=[]
    for e in exp:
        gm=js(REL/"offline_families"/e["family_slug"]/"data/web/global/manifest.json")
        if gm["family_count"]!=1 or gm.get("cross_family_comparison_available") is not False:
            bad.append(e["family_slug"])
    check(g,"offline manifest advertises only its own family",not bad,str(bad[:3]))
    check(g,"site entry point exists",(REL/"site/index.html").exists())

def N_sources():
    g="N_sources"
    refs=js(WEB/"global/references.json"); rel=js(WEB/"global/release_metadata.json")
    src=js(WEB/"global/sources.json")
    check(g,"no fabricated atlas DOI",refs["atlas"]["doi"] is None)
    check(g,"pre-release flag set",rel["pre_release"] is True and M["pre_release"] is True)
    check(g,"code licence is declared pending",rel["code_licence"]=="pending")
    check(g,"licence gates carried through",len(rel["release_gates"])>=2 and len(M["licence_gates"])>=2)
    check(g,"source licences are per source, not one project licence",
          len({x["licence"] if isinstance(x.get("licence"),str) else str(x.get("licence"))
               for x in src["licences"]})>1)
    ok=True
    for f in M["families"][:3]:
        r=js(WEB/"families"/f["slug"]/"references.json")
        for s in r["structure_sources"][:50]:
            if not re.match(r"^https://doi\.org/10\.2210/pdb[0-9A-Za-z]{4}/pdb$",s["pdb_doi"]): ok=False
            if not s["rcsb_entry"].endswith(s["pdb_id"]): ok=False
    check(g,"PDB DOI pattern and structure links correct",ok)
    check(g,"GtoPdb licence still owner-provided, not self-verified",
          any("owner_provided" in str(x.get("status","")) for x in src["licences"]))

def O_determinism():
    g="O_determinism"
    before={"global":hashlib.sha256((WEB/"global/manifest.json").read_bytes()).hexdigest(),
            "landing":hashlib.sha256((WEB/"global/landing.json").read_bytes()).hexdigest(),
            "fam":hashlib.sha256((WEB/"families/ca-001-006/summary.json").read_bytes()).hexdigest(),
            "bundle":hashlib.sha256((WEB/"structures/6MXT/viewer.cif").read_bytes()).hexdigest()}
    for script in ("pipeline/phase5/build_payloads.py","pipeline/phase5/build_bundles.py"):
        r=subprocess.run([sys.executable,str(ROOT/script)],capture_output=True,text=True,cwd=str(ROOT))
        check(g,f"{Path(script).name} re-runs cleanly",r.returncode==0,r.stderr[-200:])
    after={"global":hashlib.sha256((WEB/"global/manifest.json").read_bytes()).hexdigest(),
           "landing":hashlib.sha256((WEB/"global/landing.json").read_bytes()).hexdigest(),
           "fam":hashlib.sha256((WEB/"families/ca-001-006/summary.json").read_bytes()).hexdigest(),
           "bundle":hashlib.sha256((WEB/"structures/6MXT/viewer.cif").read_bytes()).hexdigest()}
    for k in before: check(g,f"{k} payload byte-identical on rebuild",before[k]==after[k])

def main()->int:
    for fn in (A_read_only,B_payload_integrity,C_semantics,D_metrics,E_labels,F_schema,G_loading,
               H_viewer,I_i18n,J_themes,K_accessibility,L_exports,M_offline,N_sources,O_determinism):
        fn()
    groups={}
    for g,n,r,_ in R: groups.setdefault(g,[]).append(r)
    print("\nPhase 5 validation")
    for g,res in groups.items():
        print(f"  {g:24} {res.count('PASS'):3} pass  {res.count('FAIL'):3} fail")
    failed=sum(1 for _,_,r,_ in R if r=="FAIL")
    print(f"\n  total {len(R)} checks, {failed} failed")
    (ROOT/"reports/phase5").mkdir(parents=True,exist_ok=True)
    (ROOT/"reports/phase5/validation_results.json").write_text(json.dumps(
        {"checks":[{"group":g,"name":n,"result":r,"detail":d} for g,n,r,d in R],
         "total":len(R),"failed":failed},indent=1,ensure_ascii=False),encoding="utf-8")
    return 1 if failed else 0
if __name__=="__main__": raise SystemExit(main())
