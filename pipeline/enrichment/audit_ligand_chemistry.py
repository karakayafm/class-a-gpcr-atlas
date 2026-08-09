#!/usr/bin/env python3
"""E8 (Stage 0): measure what a chemistry layer could actually cover in this corpus.

Two coverage numbers are easy to confuse and only one of them is honest for a user-facing
counter:

  * unique CCD parse rate — flattering, because one CCD can appear in dozens of structures
    (G1I is in 81), so a 99.8% parse rate says little about how much of the atlas is covered;
  * structure-ligand instance coverage — what a reader actually browses, and the number the
    interface must be built on.

Both are reported here with explicit numerator and denominator, along with the categories that
explain the gap: peptide and polymer ligands carry no CCD at all, and covalent adducts need
their bound and free forms kept apart rather than silently interchanged.

Writes a machine-readable audit and a human-readable snapshot. Runs entirely from local caches;
no network access.

    python3 pipeline/enrichment/audit_ligand_chemistry.py
"""
from __future__ import annotations

import collections
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "data/normalized/class_a_structure_universe.json"
CANDIDATES = ROOT / "data/intermediate/ligand_candidates.jsonl"
CHEMCOMP = ROOT / "data/cache/rcsb_chemcomp"
OUT_JSON = ROOT / "data/intermediate/enrichment/ligand_chemistry_audit.json"
OUT_MD = ROOT / "reports/enrichment_ligand_audit.md"

try:
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog("rdApp.*")
except ImportError:  # pragma: no cover - environment guard
    print("RDKit is required: python3 -m pip install rdkit", file=sys.stderr)
    raise


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def ccd_of(record: dict) -> str | None:
    """CCD code carried by a ligand entity id, or None for polymer/peptide ligands.

    Ids look like `7D7M:LE:np:P2E` for a non-polymer entity and `5GLH:LE:poly:2` for a chain.
    Only the non-polymer form names a chemical component.
    """
    parts = record["ligand_entity_id"].split(":")
    return parts[3] if len(parts) > 3 and parts[2] == "np" else None


def component_smiles() -> tuple[dict[str, str], dict[str, dict]]:
    """Deposited SMILES per CCD, preferring the CACTVS canonical form for reproducibility."""
    smiles: dict[str, str] = {}
    meta: dict[str, dict] = {}
    for path in sorted(glob.glob(str(CHEMCOMP / "*.json"))):
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        code = doc.get("rcsb_id")
        if not code:
            continue
        meta[code] = doc.get("chem_comp") or {}
        for descriptor in doc.get("pdbx_chem_comp_descriptor") or []:
            kind, program = descriptor.get("type", ""), descriptor.get("program")
            if kind == "SMILES_CANONICAL" and program == "CACTVS":
                smiles[code] = descriptor.get("descriptor")
                break
            if kind.startswith("SMILES") and code not in smiles:
                smiles[code] = descriptor.get("descriptor")
    return smiles, meta


def covalent_form_class(chem_comp: dict) -> str:
    """How the deposited component relates to a free ligand.

    A covalent adduct in the PDB is usually deposited as the free molecule plus a LINK record —
    RET is retinal, not the Schiff base. Those components have a usable free form. A component
    typed as `* linking` only exists inside a polymer, so no free-form descriptor applies and
    none is invented.
    """
    kind = (chem_comp or {}).get("type") or ""
    if kind == "non-polymer":
        return "verified_free_form"
    if "linking" in kind.lower():
        return "bound_form_only"
    return "ambiguous"


def main() -> int:
    structures = json.loads(UNIVERSE.read_text(encoding="utf-8"))["structures"]
    candidates = load_jsonl(CANDIDATES)
    relevant = [r for r in candidates if r["pharmacological_relevance"] == "relevant"]
    non_pharm = [r for r in candidates if r["pharmacological_relevance"] != "relevant"]

    smiles, chem_meta = component_smiles()
    parsed, failed = {}, {}
    for code, text in smiles.items():
        mol = Chem.MolFromSmiles(text) if text else None
        if mol is None:
            failed[code] = {"raw_smiles": text,
                            "parse_error": "non-standard valence representation"}
        else:
            parsed[code] = mol

    instances_by_ccd = collections.Counter()
    for record in relevant:
        code = ccd_of(record)
        if code:
            instances_by_ccd[code] += 1

    instances_with_ccd = sum(instances_by_ccd.values())
    instances_enrichable = sum(n for c, n in instances_by_ccd.items() if c in parsed)
    instances_parse_failed = sum(n for c, n in instances_by_ccd.items() if c in failed)

    by_structure = collections.Counter(r["pdb_id"] for r in relevant)
    concepts = set()
    for mol in parsed.values():
        try:
            concepts.add(Chem.MolToInchiKey(mol).split("-")[0])
        except Exception:  # noqa: BLE001 - a key that cannot be produced is simply not counted
            pass

    covalent = [r for r in relevant if r["entity_form"] == "covalent_adduct"]
    covalent_classes = collections.Counter()
    covalent_detail = collections.defaultdict(set)
    for record in covalent:
        code = ccd_of(record)
        form = covalent_form_class(chem_meta.get(code, {})) if code else "ambiguous"
        covalent_classes[form] += 1
        if code:
            covalent_detail[form].add(code)

    audit = {
        "schema": "ligand_chemistry_audit",
        "schema_version": "1.0.0",
        "rdkit_version": Chem.rdBase.rdkitVersion,
        "smiles_source": "RCSB chem_comp SMILES_CANONICAL (CACTVS), local cache",
        "network_access": False,
        "structures": {
            "total": len(structures),
            "with_pharmacological_ligand": len(by_structure),
            "with_multiple_pharmacological_ligands": sum(1 for n in by_structure.values() if n > 1),
            "manual_review_required": len({r["pdb_id"] for r in candidates
                                           if r.get("manual_review_status") == "required"}),
        },
        "instances": {
            "candidates_total": len(candidates),
            "relevant": len(relevant),
            "non_pharmacological": len(non_pharm),
            "with_ccd": instances_with_ccd,
            "without_ccd_peptide_or_polymer": len(relevant) - instances_with_ccd,
            "chemistry_enrichable": instances_enrichable,
            "parse_failed": instances_parse_failed,
            "unresolved_manual_review": sum(1 for r in candidates
                                            if r.get("analysis_eligibility") == "unresolved_manual_review"),
            "by_entity_form": dict(collections.Counter(r["entity_form"] for r in relevant)),
            "by_biological_type": dict(collections.Counter(r["biological_type"] for r in relevant)),
        },
        "forms": {
            # The interface counts against the relevant subset; the cache is wider because it
            # also holds components that were never selected as a pharmacological ligand.
            "unique_ccd_in_relevant_instances": len(instances_by_ccd),
            "unique_ccd_in_relevant_instances_parsed": sum(1 for c in instances_by_ccd if c in parsed),
            "unique_ccd_cached": len(smiles),
            "unique_ccd_cached_parsed": len(parsed),
            "chemical_concepts": len(concepts),
        },
        "covalent_adducts": {
            "instances": len(covalent),
            "classes": dict(covalent_classes),
            "components": {k: sorted(v) for k, v in covalent_detail.items()},
            "rule": ("Bound and free forms are never interchanged. Contacts and functional groups "
                     "use the exact bound form as deposited; bulk descriptors are reported only "
                     "where the component itself is a free molecule."),
        },
        "parse_failures": failed,
        "most_repeated_components": instances_by_ccd.most_common(5),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(audit, sort_keys=True, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    def ratio(num: int, den: int) -> str:
        return f"{num} / {den} = {100 * num / den:.1f}%" if den else f"{num} / 0"

    s, i, f = audit["structures"], audit["instances"], audit["forms"]
    lines = [
        "# Ligand chemistry coverage audit", "",
        f"Generated by `pipeline/enrichment/audit_ligand_chemistry.py` with RDKit "
        f"{audit['rdkit_version']} from local caches only (no network).", "",
        "## Structures", "",
        "| Measure | Numerator / denominator |", "|---|---|",
        f"| Class A structures | {s['total']} |",
        f"| With a pharmacological ligand | {ratio(s['with_pharmacological_ligand'], s['total'])} |",
        f"| With more than one | {ratio(s['with_multiple_pharmacological_ligands'], s['with_pharmacological_ligand'])} |",
        f"| Manual review required | {ratio(s['manual_review_required'], s['total'])} |", "",
        "## Structure-ligand instances", "",
        "| Measure | Numerator / denominator |", "|---|---|",
        f"| Ligand candidates | {i['candidates_total']} |",
        f"| Pharmacologically relevant | {ratio(i['relevant'], i['candidates_total'])} |",
        f"| Non-pharmacological components | {ratio(i['non_pharmacological'], i['candidates_total'])} |",
        f"| Carrying a CCD (chemistry applicable) | {ratio(i['with_ccd'], i['relevant'])} |",
        f"| No CCD (peptide/polymer) | {ratio(i['without_ccd_peptide_or_polymer'], i['relevant'])} |",
        f"| **Chemistry-enrichable** | **{ratio(i['chemistry_enrichable'], i['relevant'])}** |",
        f"| Parse failed | {ratio(i['parse_failed'], i['relevant'])} |", "",
        "## Unique forms and concepts", "",
        "| Measure | Numerator / denominator |", "|---|---|",
        f"| Unique CCD in relevant instances | {f['unique_ccd_in_relevant_instances']} |",
        f"| ... parsed | {ratio(f['unique_ccd_in_relevant_instances_parsed'], f['unique_ccd_in_relevant_instances'])} |",
        f"| Unique CCD cached | {f['unique_ccd_cached']} |",
        f"| ... parsed | {ratio(f['unique_ccd_cached_parsed'], f['unique_ccd_cached'])} |",
        f"| Chemical concepts (connectivity InChIKey) | {ratio(f['chemical_concepts'], f['unique_ccd_cached_parsed'])} |",
        "",
        "The interface counts against the relevant-instance subset "
        f"({f['unique_ccd_in_relevant_instances']} components). The cache is wider "
        f"({f['unique_ccd_cached']}) because it also holds components never selected as a "
        "pharmacological ligand; that wider number must not be presented as coverage.", "",
        "## Covalent adducts", "",
        "| Class | Instances |", "|---|---|",
    ]
    for name, count in sorted(audit["covalent_adducts"]["classes"].items()):
        lines.append(f"| `{name}` | {count} |")
    lines += ["", audit["covalent_adducts"]["rule"], "", "## Parse failures", ""]
    if failed:
        for code, info in sorted(failed.items()):
            lines.append(f"- `{code}` — {info['parse_error']}; raw SMILES preserved, "
                         "descriptors null, no manual correction applied.")
    else:
        lines.append("- none")
    lines += ["", "## Most repeated components", "",
              "One component can dominate many structures, which is why a unique-component "
              "rate overstates coverage.", ""]
    for code, count in audit["most_repeated_components"]:
        lines.append(f"- `{code}` — {count} instances")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"structures": s, "instances_relevant": i["relevant"],
                      "chemistry_enrichable": i["chemistry_enrichable"],
                      "unique_ccd_relevant": f["unique_ccd_in_relevant_instances"],
                      "covalent": audit["covalent_adducts"]["classes"],
                      "parse_failures": sorted(failed)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
