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
| Guide to Pharmacology (GtoPdb) | database ODbL; contents CC BY-SA 4.0. Recorded as owner-provided, **not verified by this project** | Ligand identifier, link, retrieval date, match basis |
| ChEMBL | CC BY-SA 3.0 | Molecule identifier, link, retrieval date, match basis |
| PubChem | NCBI public domain | Compound identifier, link, retrieval date, match basis |

Component name, formula and InChIKey come from the PDB Chemical Component Dictionary, not from
these sources.

## BindingDB

- **Role:** reported binding affinity for ligand-receptor pairs the atlas already holds
- **Licence as stated by the provider:** BindingDB states **two** licences for its contents, not
  one. **Verified by this project on 2026-08-15** by direct retrieval of
  `https://www.bindingdb.org/rwd/bind/info.jsp`, which reads: *"Data imported from ChEMBL are
  provided under their Creative Commons Attribution-Share Alike 3.0 Unported License. All data
  curated by BindingDB staff are provided under the Creative Commons Attribution 3.0 License."*
- **What is fetched:** only `BindingDB_BindingDB_Articles_202608_tsv.zip`, the staff-curated
  subset, SHA-256 `2529b1c5…`. The ChEMBL-derived records are a **separate download that is never
  retrieved**. The remaining subsets — PDSPKi, Patents, PubChem, CSAR, ITC, Covid-19 — fall under
  neither of the two stated categories, so their terms are not established by that sentence and
  they are not used.
- **Why the REST API is not used:** it returns no field identifying which measurement came from
  where. Its columns are `affinity`, `affinity_type`, `doi`, `pmid`, `query`, `smile`, so a
  response cannot be separated into the licence categories above and would mix CC BY-SA content
  into the release.
- **What the release carries:** measurement type, value in nM as a median with its range, the
  number of measurements, and the PubMed identifiers. Values reported as a limit (`>`, `<`) are
  not measurements and are excluded.
- **Coverage:** 23 of 578 components with an InChIKey, across 29 receptors and 63 ligand-receptor
  pairs. The interface states this where a compound has no value, so an absent value is not read
  as an absent measurement.
- **Attribution: required.** CC BY 3.0. Given on the Data sources page as *"Data from BindingDB
  (https://www.bindingdb.org), CC BY 3.0."*
- **Effect on this release's own licence:** none. CC BY 3.0 imposes attribution but no
  share-alike, so the derived data stays under CC BY-NC 4.0. This is the reason the ChEMBL-derived
  subset is excluded rather than merely deprioritised: CC BY-SA material cannot be relicensed
  under a noncommercial term, and carrying any of it would change the licence of the whole
  release. As with GPCRdb's CC BY 4.0, nothing in this project's licences may be read to restrict
  a recipient's exercise of the rights CC BY 3.0 grants over the BindingDB material itself.

**Share-alike: not applicable.** What is carried from these sources is which entry corresponds
to which component, and where to find it. The preferred compound name each of them publishes is
not carried, so no content under CC BY-SA 3.0 or CC BY-SA 4.0 is redistributed and their
share-alike terms are not engaged. The interface shows the identifier and links to the page
where the source publishes the name.

## Third-party software

See `THIRD_PARTY_NOTICES.md`: NGL Viewer 2.3.1 (MIT) and, bundled inside it, three.js r158 (MIT),
chroma.js (BSD 3-clause), ColorBrewer colour tables (Apache 2.0), JS Signals (MIT) and Kdtree
(MIT). The vendored bundle was verified byte-identical to the published npm distribution.

## This project's own outputs

Computed contacts, generic-number mappings, aggregation units, motif measurements, evidence
adjudications, the review-gated overlay and the documentation are licensed **CC BY-NC 4.0**
(`LICENSE-DATA`). The application and pipeline code are licensed **PolyForm Noncommercial 1.0.0**
(`LICENSE`). Scope: `LICENSE-NOTICE.md` and `LICENSE-SCOPE.json`.
