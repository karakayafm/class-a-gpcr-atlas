#!/usr/bin/env python3
"""E9 (Stage 1): compute ligand chemistry for the chemical components in this corpus.

Chemistry is stored once per chemical component, not once per structure-ligand instance. One
component can appear in dozens of structures — G1I is in 81 — so repeating its descriptors per
instance would multiply the payload and invite the two copies to drift apart. The interface
resolves an observation's component code against this table.

Three rules the science depends on:

  * Descriptors are computed here, from the deposited SMILES, with a recorded RDKit version.
    Values fetched from PubChem or ChEMBL are a different claim and are not mixed in.
  * A component that cannot be parsed stays in the table with `parse_status: "failed"` and its
    raw SMILES. It is never quietly corrected, and it never stops the build.
  * Covalent adducts keep bound and free forms apart. Most are deposited as the free molecule
    with a separate LINK record, so bulk descriptors are meaningful; a component that only
    exists inside a polymer gets none, and no free form is invented for it.

Runs from local caches only; no network access.

    python3 pipeline/enrichment/build_ligand_chemistry.py
"""
from __future__ import annotations

import collections
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "config/enrichment/chemistry_catalog.json"
CHEMCOMP = ROOT / "data/cache/rcsb_chemcomp"
CANDIDATES = ROOT / "data/intermediate/ligand_candidates.jsonl"
OUT = ROOT / "data/intermediate/enrichment/ligand_chemistry.json"
REPORT = ROOT / "reports/enrichment_ligand_chemistry.md"

from rdkit import Chem, RDLogger                                # noqa: E402
from rdkit.Chem.Scaffolds import MurckoScaffold                # noqa: E402
from rdkit.Chem import Crippen, Descriptors, rdMolDescriptors  # noqa: E402
RDLogger.DisableLog("rdApp.*")


SCAFFOLD_MIN_LIGANDS = 2


def scaffold_index(records: list[dict]) -> dict:
    """Scaffolds shared by at least SCAFFOLD_MIN_LIGANDS components, and what was left out."""
    counts: dict[str, int] = {}
    acyclic = 0
    for record in records:
        if record.get("parse_status") != "ok":
            continue
        scaffold = record.get("scaffold")
        if scaffold is None:
            acyclic += 1
            continue
        counts[scaffold] = counts.get(scaffold, 0) + 1
    shared = {k: v for k, v in counts.items() if v >= SCAFFOLD_MIN_LIGANDS}
    return {
        "min_ligands": SCAFFOLD_MIN_LIGANDS,
        "distinct_scaffolds": len(counts),
        "shared_scaffolds": len(shared),
        "components_acyclic": acyclic,
        "components_with_unique_scaffold": sum(1 for v in counts.values()
                                               if v < SCAFFOLD_MIN_LIGANDS),
        "scaffolds": [{"smiles": k, "components": v}
                      for k, v in sorted(shared.items(), key=lambda kv: (-kv[1], kv[0]))],
    }


def deposited_smiles(doc: dict) -> str | None:
    """Prefer the CACTVS canonical SMILES so a rebuild always starts from the same string."""
    fallback = None
    for descriptor in doc.get("pdbx_chem_comp_descriptor") or []:
        kind, program = descriptor.get("type", ""), descriptor.get("program")
        if kind == "SMILES_CANONICAL" and program == "CACTVS":
            return descriptor.get("descriptor")
        if kind.startswith("SMILES") and fallback is None:
            fallback = descriptor.get("descriptor")
    return fallback


def descriptors_for(mol: Chem.Mol) -> dict:
    return {
        "mw": round(Descriptors.MolWt(mol), 2),
        "exact_mass": round(Descriptors.ExactMolWt(mol), 4),
        "mollogp": round(Crippen.MolLogP(mol), 2),
        "tpsa": round(rdMolDescriptors.CalcTPSA(mol), 2),
        "hbd": rdMolDescriptors.CalcNumHBD(mol),
        "hba": rdMolDescriptors.CalcNumHBA(mol),
        "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
        "formal_charge": Chem.GetFormalCharge(mol),
        "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
        "fraction_csp3": round(rdMolDescriptors.CalcFractionCSP3(mol), 3),
    }


def free_form_status(chem_comp: dict) -> str:
    """Whether bulk descriptors describe a free molecule.

    A component typed `non-polymer` stands alone even when a LINK record attaches it to the
    receptor, so its descriptors are those of the free ligand. A `* linking` component only
    exists as part of a chain; describing it as a free molecule would be a fabrication.
    """
    kind = (chem_comp or {}).get("type") or ""
    if kind == "non-polymer":
        return "free_form_available"
    if "linking" in kind.lower():
        return "bound_form_only"
    return "ambiguous"


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    patterns = catalog["patterns"]
    queries = {}
    for name, spec in patterns.items():
        query = Chem.MolFromSmarts(spec["smarts"])
        if query is None:
            print(f"catalogue pattern does not compile: {name}", file=sys.stderr)
            return 2
        queries[name] = query

    # Components that actually appear as a pharmacological ligand. The cache is wider; coverage
    # must be reported against this subset, not against everything that happens to be cached.
    relevant_codes = collections.Counter()
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        if record["pharmacological_relevance"] != "relevant":
            continue
        parts = record["ligand_entity_id"].split(":")
        if len(parts) > 3 and parts[2] == "np":
            relevant_codes[parts[3]] += 1

    records, failures = [], []
    for path in sorted(glob.glob(str(CHEMCOMP / "*.json"))):
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        code = doc.get("rcsb_id")
        if not code:
            continue
        chem_comp = doc.get("chem_comp") or {}
        smiles = deposited_smiles(doc)
        base = {
            "ccd": code,
            "name": chem_comp.get("name"),
            "component_type": chem_comp.get("type"),
            "free_form_status": free_form_status(chem_comp),
            "pharmacological_instances": relevant_codes.get(code, 0),
        }
        mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is None:
            failures.append(code)
            records.append({**base, "parse_status": "failed",
                            "parse_error": "non-standard valence representation"
                                           if smiles else "no deposited SMILES",
                            "raw_smiles": smiles, "inchikey": None, "concept_key": None,
                            "descriptors": None,
                            "facets": {"functional_groups": [], "ring_systems": []}})
            continue
        try:
            inchikey = Chem.MolToInchiKey(mol)
        except Exception:  # noqa: BLE001 - absence is recorded rather than guessed
            inchikey = None
        matched = {"functional_groups": sorted(n for n, q in queries.items()
                                               if patterns[n]["facet"] == "functional_group"
                                               and mol.HasSubstructMatch(q)),
                   "ring_systems": sorted(n for n, q in queries.items()
                                          if patterns[n]["facet"] == "ring_system"
                                          and mol.HasSubstructMatch(q))}
        # Bemis-Murcko: strip the side chains, keep the ring systems and the linkers between
        # them. Computed, not named — this is the scaffold the algorithm returns, and no
        # pharmacological chemotype is asserted over it. A ligand with no ring has no scaffold,
        # which is recorded as null rather than as an empty string.
        try:
            scaffold_mol = MurckoScaffold.GetScaffoldForMol(mol)
            scaffold = Chem.MolToSmiles(scaffold_mol) if scaffold_mol is not None else ""
        except Exception:
            scaffold = ""
        scaffold = scaffold or None
        # Bulk descriptors only where they describe a free molecule.
        usable = base["free_form_status"] == "free_form_available"
        records.append({**base, "parse_status": "ok", "raw_smiles": smiles,
                        "inchikey": inchikey,
                        "concept_key": inchikey.split("-")[0] if inchikey else None,
                        "descriptors": descriptors_for(mol) if usable else None,
                        "descriptors_omitted_reason": None if usable else base["free_form_status"],
                        "scaffold": scaffold,
                        "scaffold_status": "acyclic" if scaffold is None else "computed",
                        "facets": matched})

    payload = {
        "schema": "ligand_chemistry",
        "schema_version": "1.0.0",
        "catalog_version": catalog["catalog_version"],
        "rdkit_version": Chem.rdBase.rdkitVersion,
        "smiles_source": "RCSB chem_comp SMILES_CANONICAL (CACTVS), local cache",
        "network_access": False,
        "descriptor_note": ("Computed here with the recorded RDKit version from the deposited "
                            "SMILES. Values published by other resources are a separate claim "
                            "and are not merged into these fields."),
        "count": len(records),
        # A scaffold seen in one ligand cannot group anything, and there are hundreds of them.
        # The index carries the ones that are shared, so an interface can offer a list the
        # length of the other facets rather than one entry per ligand.
        "scaffold_index": scaffold_index(records),
        "scaffold_note": ("Bemis-Murcko scaffolds computed with the recorded RDKit version: the "
                          "ring systems and the linkers between them, with side chains removed. "
                          "They are not named chemotypes and no pharmacological class is claimed "
                          "for them."),
        "records": sorted(records, key=lambda r: r["ccd"]),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False) + "\n", encoding="utf-8")

    ok = [r for r in records if r["parse_status"] == "ok"]
    with_desc = [r for r in ok if r["descriptors"]]
    relevant_records = [r for r in records if r["pharmacological_instances"]]
    enriched_instances = sum(r["pharmacological_instances"] for r in ok)
    facet_counts = collections.Counter()
    for record in ok:
        for facet in ("functional_groups", "ring_systems"):
            for name in record["facets"][facet]:
                facet_counts[name] += record["pharmacological_instances"]

    lines = [
        "# Ligand chemistry build", "",
        f"RDKit {payload['rdkit_version']}, catalogue {payload['catalog_version']}, "
        "local caches only.", "",
        f"- components written: {len(records)}",
        f"- parsed: {len(ok)}/{len(records)}",
        f"- with bulk descriptors: {len(with_desc)}/{len(ok)} "
        "(omitted where the component only exists bound)",
        f"- components appearing as a pharmacological ligand: {len(relevant_records)}",
        f"- structure-ligand instances covered: {enriched_instances}",
        f"- payload bytes: {OUT.stat().st_size}", "",
        "## Parse failures", "",
    ]
    lines += [f"- `{code}` — raw SMILES preserved, descriptors null, no manual correction"
              for code in failures] or ["- none"]
    lines += ["", "## Facet coverage, weighted by structure-ligand instances", "",
              "| Pattern | Instances |", "|---|---:|"]
    for name, count in facet_counts.most_common(12):
        lines.append(f"| `{name}` | {count} |")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"components": len(records), "parsed": len(ok),
                      "with_descriptors": len(with_desc),
                      "instances_covered": enriched_instances,
                      "bytes": OUT.stat().st_size, "failures": failures}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
