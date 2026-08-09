#!/usr/bin/env python3
"""Semantic validation of the chemistry SMARTS catalogue.

Syntactic validity proves nothing about meaning: a pattern that compiles can still call an
amide nitrogen an amine. Every pattern therefore carries a positive example it must match and,
where the distinction is easy to get wrong, a negative example it must reject. Parent-child
relations are checked against the real corpus rather than asserted, because a child that
matches something its parent does not would make the interface hierarchy a lie.

    python3 tests/enrichment/test_chemistry_smarts.py
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "config/enrichment/chemistry_catalog.json"
CHEMCOMP = ROOT / "data/cache/rcsb_chemcomp"

from rdkit import Chem, RDLogger  # noqa: E402
RDLogger.DisableLog("rdApp.*")

# name -> (SMILES that must match, SMILES that must NOT match or None)
# Negatives are chosen to be the classic confusions, not arbitrary non-matches.
EXAMPLES: dict[str, tuple[str, str | None]] = {
    "fg_primary_amine": ("CCN", "CC(=O)N"),                 # not acetamide
    "fg_secondary_amine": ("CNC", "CS(=O)(=O)NC"),          # not methanesulfonamide
    "fg_tertiary_amine": ("CN(C)C", "CC(=O)N(C)C"),         # not N,N-dimethylacetamide
    "fg_quaternary_ammonium": ("C[N+](C)(C)C", "CN(C)C"),   # not a neutral tertiary amine
    "fg_guanidine": ("NC(=N)N", "CC(=N)N"),                 # not a plain amidine
    "fg_amidine": ("CC(=N)N", "CC(=O)N"),                   # not an amide
    "fg_carboxylic_acid": ("CC(=O)O", "CC(=O)OC"),          # not a methyl ester
    "fg_sulfonic_acid": ("CS(=O)(=O)O", "CS(=O)(=O)N"),     # not a sulfonamide
    "fg_phosphate": ("COP(=O)(O)O", "CP(=O)(O)O"),          # not a phosphonate
    "fg_phosphonate": ("CP(=O)(O)O", None),
    "fg_phenol": ("Oc1ccccc1", "CCO"),                      # not ethanol
    "fg_alcohol": ("CCO", "Oc1ccccc1"),                     # not phenol
    "fg_catechol": ("Oc1ccccc1O", "Oc1ccccc1"),             # not a single phenol
    "fg_ether": ("COC", "CC(=O)OC"),                        # not an ester
    "fg_carbonyl": ("CC(C)=O", "CCO"),
    "fg_aldehyde": ("CC=O", "CC(C)=O"),                     # not a ketone
    "fg_ketone": ("CC(C)=O", "CC=O"),                       # not an aldehyde
    "fg_ester": ("CC(=O)OC", "CC(=O)O"),                    # not the free acid
    "fg_amide": ("CC(=O)NC", "CCNC"),                       # not an amine
    "fg_urea": ("NC(=O)N", "CC(=O)N"),                      # not an amide
    "fg_carbamate": ("COC(=O)N", "CC(=O)N"),                # not an amide
    "fg_sulfonamide": ("CS(=O)(=O)NC", "CC(=O)NC"),         # not an amide
    "fg_sulfone": ("CS(=O)(=O)C", "CS(=O)C"),               # not a sulfoxide
    "fg_sulfoxide": ("CS(=O)C", "CS(=O)(=O)C"),             # not a sulfone
    "fg_nitrile": ("CC#N", "CC=N"),                         # not an imine
    "fg_nitro": ("C[N+](=O)[O-]", "CN=O"),
    "rs_tetrazole": ("c1nnn[nH]1", "c1ccccc1"),
    "rs_phenyl": ("c1ccccc1", "C1CCCCC1"),                  # not cyclohexane
    "rs_indole": ("c1ccc2[nH]ccc2c1", "c1ccccc1"),
    "rs_imidazole": ("c1c[nH]cn1", "c1ccncc1"),             # not pyridine
    "rs_pyridine": ("c1ccncc1", "c1ccccc1"),
    "rs_pyrimidine": ("c1cncnc1", "c1ccncc1"),              # not pyridine
    "rs_purine": ("c1ncc2[nH]cnc2n1", "c1cncnc1"),          # not bare pyrimidine
    "rs_xanthine": ("O=c1[nH]c(=O)c2[nH]cnc2[nH]1", "c1ccccc1"),
    "rs_benzimidazole": ("c1ccc2[nH]cnc2c1", "c1c[nH]cn1"),  # not bare imidazole
    "rs_quinoline": ("c1ccc2ncccc2c1", "c1ccccc1"),
    "rs_isoquinoline": ("c1ccc2cnccc2c1", "c1ccccc1"),
    "rs_benzofuran": ("c1ccc2occc2c1", "c1ccccc1"),
    "rs_benzothiophene": ("c1ccc2sccc2c1", "c1ccc2occc2c1"),  # not benzofuran
}

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        failures.append(name)
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail and not ok else ""))


def corpus_molecules() -> dict[str, Chem.Mol]:
    mols: dict[str, Chem.Mol] = {}
    for path in sorted(glob.glob(str(CHEMCOMP / "*.json"))):
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        code, smiles = doc.get("rcsb_id"), None
        for descriptor in doc.get("pdbx_chem_comp_descriptor") or []:
            kind, program = descriptor.get("type", ""), descriptor.get("program")
            if kind == "SMILES_CANONICAL" and program == "CACTVS":
                smiles = descriptor.get("descriptor")
                break
            if kind.startswith("SMILES") and smiles is None:
                smiles = descriptor.get("descriptor")
        if not code or not smiles:
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is not None:
            mols[code] = mol
    return mols


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    patterns = catalog["patterns"]
    print(f"catalogue {catalog['catalog_version']}: {len(patterns)} patterns\n")

    print("syntax")
    queries = {}
    for name, spec in sorted(patterns.items()):
        query = Chem.MolFromSmarts(spec["smarts"])
        check(f"{name} compiles", query is not None)
        if query is not None:
            queries[name] = query

    print("\nevery pattern has a worked example")
    for name in sorted(patterns):
        check(f"{name} has an example", name in EXAMPLES)

    print("\npositive examples")
    for name, query in sorted(queries.items()):
        positive, _ = EXAMPLES.get(name, (None, None))
        if positive is None:
            continue
        mol = Chem.MolFromSmiles(positive)
        check(f"{name} matches {positive}", mol is not None and mol.HasSubstructMatch(query))

    print("\nnegative discriminations")
    for name, query in sorted(queries.items()):
        _, negative = EXAMPLES.get(name, (None, None))
        if negative is None:
            continue
        mol = Chem.MolFromSmiles(negative)
        check(f"{name} rejects {negative}", mol is not None and not mol.HasSubstructMatch(query))

    print("\nmatched atoms are non-empty and within the molecule")
    for name, query in sorted(queries.items()):
        positive, _ = EXAMPLES.get(name, (None, None))
        if positive is None:
            continue
        mol = Chem.MolFromSmiles(positive)
        match = mol.GetSubstructMatch(query)
        check(f"{name} reports atoms", bool(match) and max(match) < mol.GetNumAtoms())

    print("\nparent-child consistency over the corpus")
    mols = corpus_molecules()
    print(f"  ({len(mols)} corpus components)")
    hits = {name: {code for code, mol in mols.items() if mol.HasSubstructMatch(query)}
            for name, query in queries.items()}
    for name, spec in sorted(patterns.items()):
        parent = spec.get("parent")
        if not parent or parent not in hits:
            continue
        extra = hits[name] - hits[parent]
        check(f"{name} is a subset of {parent}", not extra, str(sorted(extra)[:4]))

    print()
    total = 0
    for name in sorted(queries):
        if hits[name]:
            total += 1
    print(f"patterns with at least one corpus match: {total}/{len(queries)}")
    if failures:
        print(f"\n{len(failures)} failed")
        return 1
    print("\nchemistry SMARTS: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
