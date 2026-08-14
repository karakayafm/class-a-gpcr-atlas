#!/usr/bin/env python3
"""Freeze the validated enrichment artefacts without recomputing science."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/intermediate/enrichment"
DEST = ROOT / "data/freezes/enrichment-1.0.4"

FILES = [
    "transducer_assignments.jsonl",
    "pathway_evidence.jsonl",
    "chemical_xrefs.json",
    "structure_references.json",
    "database_citations.json",
    "panel_statistics.json",
    "ligand_chemistry.json",
    "ligand_fingerprints.json",
    "ligand_chemistry_audit.json",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    inputs = [SRC / name for name in FILES]
    inputs += sorted((SRC / "pocket_detail").glob("*.json"))
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise SystemExit("missing enrichment inputs: " + ", ".join(missing))

    copied = []
    for source in inputs:
        relative = source.relative_to(SRC)
        target = DEST / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)

    records = [{"path": str(path.relative_to(DEST)), "bytes": path.stat().st_size,
                "sha256": digest(path)} for path in sorted(copied)]
    checksums = "".join(f"{row['sha256']}  {row['path']}\n" for row in records)
    (DEST / "checksums.sha256").write_text(checksums, encoding="utf-8")
    freeze = {
        "schema": "enrichment_freeze",
        "version": "enrichment-1.0.4",
        "created": "2026-08-14",
        "contract": ("Validated enrichment records are copied byte-for-byte; this freeze "
                     "does not infer or recompute scientific evidence."),
        "supersedes": "enrichment-1.0.3",
        "reason": ("Adds Morgan fingerprints for every parsed chemical component, so a reader "
                   "can search the corpus by structural similarity from their own browser."),
        "files": records,
        "file_count": len(records),
    }
    (DEST / "freeze.json").write_text(
        json.dumps(freeze, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8")
    print(json.dumps({"freeze": str(DEST), "files": len(records),
                      "bytes": sum(row["bytes"] for row in records)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
