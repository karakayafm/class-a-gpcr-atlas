#!/usr/bin/env python3
"""Phase 5 build entry point. Transforms the Phase 4 freeze into web payloads; it never
recomputes science."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
STEPS=[("validate freezes and run preflight","pipeline/phase5/preflight.py"),
       ("generate global and family payloads","pipeline/phase5/build_payloads.py"),
       ("generate structure viewer bundles","pipeline/phase5/build_bundles.py"),
       ("assemble static site and offline family exports","pipeline/phase5/build_site.py"),
       ("measure performance","pipeline/phase5/measure_performance.py"),
       ("run integrity tests","tests/phase5/run_tests.py"),
       ("generate freeze manifests","pipeline/phase5/freeze_phase_5.py")]
def main()->int:
    for label,script in STEPS:
        print(f"\n=== {label} ===",flush=True)
        r=subprocess.run([sys.executable,str(ROOT/script)],cwd=str(ROOT))
        if r.returncode!=0:
            print(f"FAILED at: {label} ({script})",file=sys.stderr); return r.returncode
    print("\nBuild complete. Browser tests run separately: python3 tests/phase5/browser_tests.py")
    return 0
if __name__=="__main__": raise SystemExit(main())
