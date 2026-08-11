# Source data licences

Every source this atlas draws on, the licence its provider states, and how that licence was
established. A licence this project did not verify itself is recorded as unverified.

## RCSB Protein Data Bank

- **Role:** coordinate files, entry metadata, entity inventory, `struct_conn` records, assemblies
- **Licence as stated by the provider:** PDB archive files are released under **CC0 1.0**
- **What is redistributed:** 1,358 `viewer.cif` files, filtered to the 18 mmCIF categories the
  viewer requires. **No coordinate value is altered.** Approximately 92% of the distribution by
  size.
- **Effect:** CC0 is a public domain dedication. This project's noncommercial licences do **not**
  apply to these files, and this project neither grants nor withholds rights over them.
- **Attribution:** not legally required under CC0; provided as scholarly courtesy. Every structure
  links to its RCSB entry and to its RCSB-minted DOI (`https://doi.org/10.2210/pdb{ID}/pdb`).

## GPCRdb

- **Role:** Class A taxonomy, receptor records, structure list, generic numbering reference,
  structure-state and ligand annotations
- **Licence as stated by the provider:** **Data CC BY 4.0**; code Apache 2.0
- **Attribution: required.** The obligation applies regardless of the terms this project applies
  to its own outputs.
- **Version:** GPCRdb does not expose a release identifier that this project captured.
  Reproducibility rests on the cached responses and their recorded hashes, not on a version
  string. **No version number has been invented.**
- **Downstream restrictions:** CC BY 4.0 §2(a)(5)(B) forbids imposing additional or different
  terms on the licensed material where that would restrict a recipient's exercise of the licensed
  rights. Nothing in this project's licences is intended or may be read to do so. Where a shipped
  record combines a GPCRdb-derived field with a value computed here, the noncommercial condition
  attaches only to the computed value.

## UniProt

- **Role:** accessions relayed through RCSB polymer entity records. UniProt is **not called
  directly** by the pipeline.
- **Licence:** **CC BY 4.0** on copyrightable database content
- **Verification:** **verified by this project on 2026-08-04** by direct retrieval from the
  provider's own help API (`https://rest.uniprot.org/help/license`), response SHA-256
  `5960c22b…`, source last modified 2024-12-18. The HTML page at `www.uniprot.org/help/license`
  is a JavaScript shell containing no licence text; the REST help endpoint carries the canonical
  wording.

## PDB Chemical Component Dictionary

- **Role:** chemical component identity
- **Licence:** part of the PDB archive

## Chemical cross-reference sources

Used to resolve each chemical component to its entry in the public chemistry databases, so a
reader can follow a ligand out of this atlas. Queried by
`pipeline/enrichment/fetch_chemical_xrefs.py`; responses are cached under `data/cache/` and a
normal build reads the cache without reaching the network.

| Source | Licence | What the release carries |
|---|---|---|
| EMBL-EBI UniChem | EMBL-EBI terms | Used to map component to database entries; nothing from it appears in the release |
| Guide to Pharmacology (GtoPdb) | database ODbL; contents CC BY-SA 4.0. Recorded as owner-provided, **not verified by this project** | Ligand identifier, link, retrieval date, match basis, and the preferred name where one was found (300 of 580 records) |
| ChEMBL | CC BY-SA 3.0 | Molecule identifier, link, retrieval date, match basis, and the preferred name where one was found (219 of 580 records) |
| PubChem | NCBI public domain | Compound identifier, link, retrieval date, match basis, and the preferred name where one was found (484 of 580 records) |

Component name, formula and InChIKey come from the PDB Chemical Component Dictionary, not from
these sources.

**Share-alike: open.** Identifiers and links are facts about which entry corresponds to which
component. The preferred names are content from databases published under CC BY-SA 3.0 (ChEMBL)
and CC BY-SA 4.0 (GtoPdb contents), and whether carrying a name alongside its identifier makes
this atlas a derivative under those terms is unresolved. Dropping the names would remove the
question at no cost to the interface, which displays the identifier. See
`docs/DERIVED_DATA_REVIEW_PACKET.md` §3.

## Third-party software

See `THIRD_PARTY_NOTICES.md`: NGL Viewer 2.3.1 (MIT) and, bundled inside it, three.js r158 (MIT),
chroma.js (BSD 3-clause), ColorBrewer colour tables (Apache 2.0), JS Signals (MIT) and Kdtree
(MIT). The vendored bundle was verified byte-identical to the published npm distribution.

## This project's own outputs

Computed contacts, generic-number mappings, aggregation units, motif measurements, evidence
adjudications, the review-gated overlay and the documentation are licensed **CC BY-NC 4.0**
(`LICENSE-DATA`). The application and pipeline code are licensed **PolyForm Noncommercial 1.0.0**
(`LICENSE`). Scope: `LICENSE-NOTICE.md` and `LICENSE-SCOPE.json`.
