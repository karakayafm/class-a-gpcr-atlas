#!/usr/bin/env python3
"""Build web payloads from the Phase 4 and enrichment freezes without recomputing science.

The four search indices and the affinity side file are part of the build, not extras. They were
added as standalone scripts and left out of this list, so a build produced a site whose Find
motif, Contact map and search pages fetched files that were not there; the loader reported the
404 as a schema mismatch. They run here, after the bundles, because they read
data/web/structures, and before build_site.py, which assembles whatever data/web holds.

Their own defaults read and write site/data/web - the published directory, not the build output -
so every path is passed explicitly here. Do not drop those arguments.
"""
from __future__ import annotations
import shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WEB=ROOT/"data/web"; P3=ROOT/"data/intermediate/phase3"; RAW=ROOT/"data/raw/gpcrdb"
SEARCH_IO=["--contacts",str(WEB/"structures"),
           "--mapping",str(P3/"receptor_residue_mapping.jsonl"),
           "--gpcrdb",str(RAW/"receptor_residues.json"),
           "--families",str(WEB/"families")]
STEPS=[("freeze validated enrichment artefacts","pipeline/enrichment/freeze_enrichment.py",[]),
       ("validate freezes and run preflight","pipeline/phase5/preflight.py",[]),
       ("generate global and family payloads","pipeline/phase5/build_payloads.py",[]),
       ("generate structure viewer bundles","pipeline/phase5/build_bundles.py",[]),
       ("build the receptor search index","pipeline/phase5/build_receptor_search.py",
        SEARCH_IO+["--out",str(WEB/"global/receptor_search.json")]),
       ("build the pocket search index","pipeline/phase5/build_pocket_search.py",
        SEARCH_IO+["--out",str(WEB/"global/pocket_search.json")]),
       ("build the generic-numbering side file","pipeline/phase5/build_generic_numbering.py",
        ["--gpcrdb",str(RAW/"receptor_residues.json"),
         "--payloads",str(WEB/"global/motif_search.json"),str(WEB/"global/pocket_search.json"),
         str(WEB/"global/receptor_search.json"),
         "--out",str(WEB/"global/generic_numbering.json")]),
       ("build the supersessions side file","pipeline/phase5/build_supersessions.py",
        ["--families",str(WEB/"families"),"--out",str(WEB/"global/supersessions.json")]),
       ("build the per-structure numbering tables","pipeline/phase5/build_receptor_residues.py",
        ["--mapping",str(P3/"receptor_residue_mapping.jsonl"),
         "--structures",str(WEB/"structures"),"--out",str(WEB/"overlay/structures")]),
       ("carry the overlay content phase 5 does not build","pipeline/phase5/carry_overlays.py",
        ["--web",str(WEB)]),
       ("register the side files in the manifest","pipeline/phase5/register_side_files.py",
        ["--web",str(WEB)]),
       ("assemble static site and offline family exports","pipeline/phase5/build_site.py",[]),
       ("measure performance","pipeline/phase5/measure_performance.py",[]),
       ("run integrity tests","tests/phase5/run_tests.py",[]),
       ("generate freeze manifests","pipeline/phase5/freeze_phase_5.py",[])]

# Copied, not generated: the enrichment freeze already holds it and nothing in phase 5 derives it.
AFFINITY=(ROOT/"data/intermediate/enrichment/binding_affinity.json", WEB/"global/binding_affinity.json")


def main()->int:
    for label,script,args in STEPS:
        if script.endswith("register_side_files.py"):
            src,dst=AFFINITY
            print("\n=== place the binding-affinity side file ===",flush=True)
            if not src.is_file():
                print(f"missing: {src}",file=sys.stderr); return 1
            dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,dst)
            print(f"{src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")
        print(f"\n=== {label} ===",flush=True)
        r=subprocess.run([sys.executable,str(ROOT/script),*args],cwd=str(ROOT))
        if r.returncode!=0:
            print(f"FAILED at: {label} ({script})",file=sys.stderr); return r.returncode
    print("\nBuild complete. Browser tests run separately: python3 tests/phase5/browser_tests.py")
    return 0
if __name__=="__main__": raise SystemExit(main())
