#!/usr/bin/env python3
"""Morgan fingerprints for every parsed chemical component, for similarity search in the browser.

The atlas is a static site, so there is nowhere to run a search server. The corpus is fingerprinted
here and shipped; the reader's query molecule is fingerprinted in their own browser by the vendored
RDKit build, and the comparison is a bit operation that needs no chemistry library at all. A
structure a reader has drawn but not published therefore never leaves their machine.

Browser and pipeline must agree bit for bit or every score is wrong. They were checked against each
other on ethanol, caffeine and carvedilol: identical bits from RDKit 2025.09.6 here and RDKit
2025.03.2 in the browser. `radius` and `bits` travel in the payload so the browser cannot silently
apply different parameters.

    python3 pipeline/enrichment/build_ligand_fingerprints.py
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/intermediate/enrichment/ligand_chemistry.json"
OUT = ROOT / "data/intermediate/enrichment/ligand_fingerprints.json"

RADIUS = 2
BITS = 2048

from rdkit import Chem, RDLogger  # noqa: E402
from rdkit.Chem import rdFingerprintGenerator  # noqa: E402
RDLogger.DisableLog("rdApp.*")


def packed(bitvect) -> str:
    """The bit vector as base64, little-endian within each byte.

    This is the layout RDKit's own `get_morgan_fp_as_uint8array` produces in the browser, so the
    two sides index the same bit the same way.
    """
    data = bytearray(BITS // 8)
    for bit in bitvect.GetOnBits():
        data[bit // 8] |= 1 << (bit % 8)
    return base64.b64encode(bytes(data)).decode()


def main() -> int:
    if not SRC.is_file():
        raise SystemExit("run build_ligand_chemistry.py first")
    chemistry = json.loads(SRC.read_text(encoding="utf-8"))
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=RADIUS, fpSize=BITS)

    records, skipped = [], []
    for record in chemistry.get("records", []):
        smiles = record.get("raw_smiles")
        if record.get("parse_status") != "ok" or not smiles:
            skipped.append({"ccd": record["ccd"], "reason": record.get("parse_status") or "no_smiles"})
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            skipped.append({"ccd": record["ccd"], "reason": "unparsed_here"})
            continue
        records.append({
            "ccd": record["ccd"],
            "fp": packed(generator.GetFingerprint(mol)),
            # Carried so a hit can be labelled without loading the chemistry payload as well.
            "instances": record.get("pharmacological_instances") or 0,
        })

    payload = {
        "schema": "ligand_fingerprints",
        "schema_version": "1.0.0",
        "fingerprint": "morgan",
        "radius": RADIUS,
        "bits": BITS,
        "encoding": "base64, little-endian within each byte",
        "rdkit_version": Chem.rdBase.rdkitVersion,
        "note": ("Computed from the deposited SMILES of each chemical component. A query molecule "
                 "is fingerprinted in the reader's browser with the same parameters; nothing about "
                 "it is transmitted or stored."),
        "count": len(records),
        "skipped": sorted(skipped, key=lambda r: r["ccd"]),
        "records": sorted(records, key=lambda r: r["ccd"]),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    print(json.dumps({"components": len(records), "skipped": len(skipped),
                      "bytes": OUT.stat().st_size, "rdkit": Chem.rdBase.rdkitVersion}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
