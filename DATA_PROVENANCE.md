# Data provenance

Every field in this atlas traces to the URL it came from, and every request made during the build
was recorded with provider, endpoint, timestamp, HTTP status, response SHA-256, cache path and
retry count.

## Retrieval

| Source | Endpoint family | Retrieved |
|---|---|---|
| GPCRdb | Class A tree, receptor records, structure list | 2026-08-03 |
| RCSB Data API | entry metadata, entity inventory, `struct_conn`, assemblies | 2026-08-04 |
| RCSB files | mmCIF coordinate files | 2026-08-04 |

UniProt accessions are **relayed through RCSB polymer entity records**; UniProt is not called by
the pipeline. GtoPdb, ChEMBL and PubChem are not called at all.

## What was computed here

- **Contacts** — exact minimum heavy-atom distance between receptor and ligand residues, computed
  from deposited coordinates. Hydrogens excluded. Altloc policy: blank, else highest occupancy,
  else alphabetical. Thresholds of 4.0, 4.5 and 5.0 Å are derived from the exact distance;
  nothing is rounded at generation time.
- **Generic numbering** — `auth_seq_id` → `label_seq_id` → UniProt position → GPCRdb generic
  number, through three candidate routes scored against observed residue identity with an 0.80
  agreement floor. Instances whose route never validated are excluded from generic aggregation.
- **Aggregation units** — receptor accession × species × normalized ligand identity × ligand form
  × binding-site class × structural state.
- **Motifs** — 8 core Class A motifs over 21 generic positions; residue identity measured, not
  assumed.
- **Structural state** — taken from the source annotation only. A transducer-bound structure is
  **not** relabelled active on that basis.

## Coordinate files

The shipped `viewer.cif` files are the deposited RCSB mmCIF **filtered to the 18 categories the
viewer requires**. No coordinate value is altered. They remain CC0 1.0 material.

## Reproducibility

Each phase is frozen with two hashes: `content_sha256` over the science, computed after stripping
an explicit list of volatile keys (timestamps, cache paths, retry counts, HTTP status), and
`package_sha256` over everything. A re-run can therefore prove the science did not change even
though the run did.

Phase 1–5 scientific hashes are unchanged across every release candidate in this line, and the
1,358 coordinate bundles are byte-identical across candidates rc.5 through rc.9.

## Nothing is excluded silently

Records that fail a check are **flagged and kept**. Two PDB identifiers listed by GPCRdb return
HTTP 404 from RCSB; both remain in the universe, flagged. Merging the sources would have produced
a cleaner count and hidden the disagreement.

## Review gating

Public-beta pooled summaries apply an issue-specific review gate over the frozen Phase 4
contributions. **Contacts are not recomputed**; an eligibility mask is applied and the affected
units are re-summarised. The original Phase 4 value is preserved in every beta record and is
reachable in the interface through a labelled panel.
