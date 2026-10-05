#!/usr/bin/env python3
"""Carry the overlay content phase 5 does not produce into a build's payload tree.

`pipeline/overlays/` writes the lipid and transducer files and their indices, and the receptor-copy
index, straight into the published tree. They are copied unchanged from RCSB entries, cost a
download and a parse per structure, and no curation decision changes them - so a phase-5 build does
not rebuild them. It does need them: without `overlay/structures/<PDB>/receptor_residues.json` the
viewer refuses to superpose ("No generic-numbering table for ..."), and the lipid and transducer
layers go quiet. That file is written by build_receptor_residues.py, which the build runs; the rest
are carried here.

    python3 pipeline/phase5/carry_overlays.py [--from site/data/web] [--web data/web]

This couples a build to the published tree, which is not ideal - the alternative is running
pipeline/overlays/ on every build, which re-downloads ~1000 entries for files that did not change.
The step is loud when the source is missing rather than silently producing a site whose viewer is
half dead.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Written by pipeline/overlays/, not by phase 5. receptor_residues.json is deliberately absent:
# build_receptor_residues.py writes it as part of the build.
INDEX_FILES = ["lipids_index.json", "transducer_index.json", "receptor_copies.json"]
STRUCTURE_FILES = ["lipids.cif", "transducer.cif.gz"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", type=Path, default=ROOT / "site/data/web")
    ap.add_argument("--web", type=Path, default=ROOT / "data/web")
    args = ap.parse_args()
    src, dst = args.src.resolve() / "overlay", args.web.resolve() / "overlay"

    if not src.is_dir():
        print(f"overlay source not found: {src}\n"
              f"Run pipeline/overlays/ or point --from at a tree that has it.")
        return 1

    copied = skipped = 0
    for name in INDEX_FILES:
        s = src / name
        if not s.is_file():
            print(f"missing overlay index: {s}")
            return 1
        d = dst / name
        d.parent.mkdir(parents=True, exist_ok=True)
        if d.is_file() and d.stat().st_size == s.stat().st_size:
            skipped += 1
        else:
            shutil.copyfile(s, d); copied += 1

    for entry in sorted((src / "structures").glob("*")):
        if not entry.is_dir():
            continue
        for name in STRUCTURE_FILES:
            s = entry / name
            if not s.is_file():
                continue
            d = dst / "structures" / entry.name / name
            d.parent.mkdir(parents=True, exist_ok=True)
            if d.is_file() and d.stat().st_size == s.stat().st_size:
                skipped += 1
            else:
                shutil.copyfile(s, d); copied += 1

    print(f"overlay: {copied} copied, {skipped} already current, from {src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
