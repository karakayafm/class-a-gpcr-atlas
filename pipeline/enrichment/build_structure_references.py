#!/usr/bin/env python3
"""E4: build structure references and database citations from local caches."""
from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "data/normalized/class_a_structure_universe.json"
RCSB_CACHE = ROOT / "data/cache/rcsb"
NCBI_CACHE = ROOT / "data/cache/ncbi/database_citations_esummary.json"
OUTPUT = ROOT / "data/intermediate/enrichment/structure_references.json"
DB_OUTPUT = ROOT / "data/intermediate/enrichment/database_citations.json"
SCHEMA = ROOT / "schemas/enrichment/structure_reference.schema.json"
REPORT = ROOT / "reports/enrichment_references.md"
SOURCE_ROLES = ROOT / "config/enrichment/source_roles.json"

DATABASE_PMIDS = {
    "pdb": "39607707",
    "gpcrdb": "39558158",
    "gtopdb": "41160876",
    "chembl": "37933841",
    "pubchem": "39558165",
    "uniprot": "39552041",
    # NGL Viewer is bundled with the site, so its two papers belong in the citation list.
    # PMIDs resolved from the published DOIs through esearch, not typed from memory.
    "ngl_2015": "25925569",
    "ngl_2018": "29850778",
}


def date_only(value):
    return value.split("T", 1)[0] if isinstance(value, str) else None


def citation(value):
    if not isinstance(value, dict) or not value:
        return None
    return {
        "authors": value.get("rcsb_authors") or [],
        "title": value.get("title"),
        "journal": value.get("rcsb_journal_abbrev") or value.get("journal_abbrev"),
        "year": value.get("year") if isinstance(value.get("year"), int) else None,
        "volume": value.get("journal_volume"),
        "pages": value.get("page_first"),
        "page_last": value.get("page_last"),
        "doi": value.get("pdbx_database_id_DOI"),
        "pubmed_id": (str(value["pdbx_database_id_PubMed"])
                      if value.get("pdbx_database_id_PubMed") is not None else None),
    }


def database_citations():
    payload = json.loads(NCBI_CACHE.read_text(encoding="utf-8"))["result"]
    result = {}
    for source, pmid in DATABASE_PMIDS.items():
        item = payload[pmid]
        doi = next((article_id["value"] for article_id in item.get("articleids", [])
                    if article_id.get("idtype") == "doi"), None)
        year_match = re.search(r"\b(19|20)\d{2}\b", item.get("pubdate", ""))
        result[source] = {
            "pmid": pmid,
            "authors": [author["name"] for author in item.get("authors", [])],
            "title": item.get("title", "").rstrip(".") or None,
            "journal": item.get("fulljournalname") or item.get("source"),
            "year": int(year_match.group(0)) if year_match else None,
            "volume": item.get("volume") or None,
            "issue": item.get("issue") or None,
            "pages": item.get("pages") or None,
            "doi": doi,
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "metadata_source": "NCBI E-utilities esummary",
            "retrieved": "2026-08-08",
        }
    return result


def main():
    structures = json.loads(UNIVERSE.read_text(encoding="utf-8"))["structures"]
    refs, missing_entries, missing_citations = [], [], []
    for structure in sorted(structures, key=lambda row: row["pdb_id"]):
        pdb_id = structure["pdb_id"]
        cache = RCSB_CACHE / f"entry_{pdb_id}.json"
        if cache.exists():
            entry = json.loads(cache.read_text(encoding="utf-8"))
            accession = entry.get("rcsb_accession_info") or {}
            primary = citation(entry.get("rcsb_primary_citation"))
            row = {
                "pdb_id": pdb_id,
                "title": (entry.get("struct") or {}).get("title"),
                "deposited": date_only(accession.get("deposit_date")),
                "released": date_only(accession.get("initial_release_date")),
                "revision": date_only(accession.get("revision_date")),
                "primary_citation": primary,
            }
        else:
            missing_entries.append(pdb_id)
            row = {"pdb_id": pdb_id, "title": None,
                   "deposited": date_only(structure.get("deposition_date")),
                   "released": date_only(structure.get("release_date")),
                   "revision": None, "primary_citation": None}
        if row["primary_citation"] is None:
            missing_citations.append(pdb_id)
        refs.append(row)

    validator = jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8")))
    errors = [(row["pdb_id"], error.message) for row in refs
              for error in validator.iter_errors(row)]
    if errors:
        raise RuntimeError(f"structure reference schema errors: {errors[:10]}")
    if len(refs) != 1358 or len({row["pdb_id"] for row in refs}) != 1358:
        raise RuntimeError("expected exactly 1358 unique structure references")

    roles = json.loads(SOURCE_ROLES.read_text(encoding="utf-8"))
    for source, role in roles["sources"].items():
        if not role.get("licence") or not role.get("license_page"):
            raise RuntimeError(f"incomplete licence metadata for {source}")
    db_citations = database_citations()
    if set(db_citations) != set(DATABASE_PMIDS):
        raise RuntimeError("database citation set is incomplete")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(refs, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n", encoding="utf-8")
    DB_OUTPUT.write_text(json.dumps(db_citations, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")) + "\n", encoding="utf-8")
    with_citation = len(refs) - len(missing_citations)
    report = f"""# Enrichment structure references and source roles

## Structure-reference coverage

| Measure | Count |
|---|---:|
| Class A structures | {len(refs)} |
| Local RCSB entry bodies used | {len(refs) - len(missing_entries)} |
| RCSB entries unavailable after targeted live checks | {len(missing_entries)} |
| Primary citations present | {with_citation} |
| Primary citations null | {len(missing_citations)} |

Unavailable RCSB entries: {', '.join(f'`{x}`' for x in missing_entries) or 'none'}.
Both unavailable IDs returned HTTP 404 from the official RCSB Data API on 2026-08-08; their records remain in the 1358-row atlas universe with null reference fields.

Primary citation null: {', '.join(f'`{x}`' for x in missing_citations) or 'none'}.

## Database citations

NCBI E-utilities `esummary` metadata was cached in one request for the current official citations of PDB, GPCRdb, GtoPdb, ChEMBL, PubChem, UniProt and NGL Viewer. Records written: {len(db_citations)}/{len(DATABASE_PMIDS)}.

## Licence verification

Seven source roles have non-empty licence descriptions and official `license_page` URLs: {', '.join(f'`{x}`' for x in sorted(roles['sources']))}. Verification date: {roles['verified']}.

- RCSB PDB: official policy confirms CC0 1.0 for PDB archive files and RCSB API data, except integrated external data.
- GPCRdb: official legal notice confirms CC BY 4.0 for data and Apache 2.0 for code.
- GtoPdb: official download page confirms ODbL for the database and CC BY-SA 4.0 for contents.
- ChEMBL: the official current ChEMBL landing page states CC BY-SA 3.0 for ChEMBL data.
- PubChem: the official download guidance states that contributor-specific licence information applies; no blanket licence is asserted here.
- UniChem: EMBL-EBI terms impose no extra restriction and preserve upstream owners' rights and licences.
- UniProt: official licence page confirms CC BY 4.0 for copyrightable database content and notes possible patent/third-party rights.
"""
    REPORT.write_text(report, encoding="utf-8")
    print(json.dumps({"records": len(refs), "local_rcsb_entries": len(refs)-len(missing_entries),
                      "missing_entries": missing_entries, "primary_citations": with_citation,
                      "missing_primary_citations": len(missing_citations),
                      "database_citations": len(db_citations),
                      "source_roles": len(roles["sources"]), "schema_errors": 0}, indent=2))


if __name__ == "__main__":
    main()
