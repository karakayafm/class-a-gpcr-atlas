# Data licence summary

The short version. The binding statements are in `LICENSE-NOTICE.md` and `LICENSE-SCOPE.json`;
the licence texts themselves are `LICENSE` and `LICENSE-DATA`, distributed unmodified.

| What | Licence | Who holds it |
|---|---|---|
| Coordinate files (`site/data/web/structures/**`) — **~92% of this distribution by size** | **CC0 1.0** | RCSB PDB. Public domain. This project neither grants nor withholds rights. |
| GPCRdb-derived fields (taxonomy, receptor and structure annotation) | **CC BY 4.0** | GPCRdb. **Attribution required.** |
| UniProt accessions relayed via RCSB | CC BY 4.0 | UniProt |
| Vendored software (`site/vendor/**`) | MIT / BSD-3-Clause / Apache-2.0 | see `THIRD_PARTY_NOTICES.md` |
| **Project-created data** — contacts, mappings, aggregation units, motif measurements, adjudications, review-gated overlay, documentation | **CC BY-NC 4.0** | Muhammed Fatih Karakaya |
| **Project-created code** — application, pipeline, schemas, tests | **PolyForm Noncommercial 1.0.0** | Muhammed Fatih Karakaya |

## The two things most often got wrong

**1. The noncommercial condition does not reach the coordinates.** They are CC0. If you want only
the structures, take them and the project's licences do not apply to you.

**2. Mixed records.** Where a shipped record combines a GPCRdb-derived field with a value computed
here, the noncommercial condition attaches **only to the computed value**. CC BY 4.0 §2(a)(5)(B)
forbids imposing additional terms on licensed material where that would restrict a recipient's
exercise of the licensed rights, and nothing here is intended or may be read to do so.

## Commercial use

Not permitted under these public licences. It may be available by separate written agreement with
Muhammed Fatih Karakaya — edu.mfatih@gmail.com.

## Not open source

Neither licence is OSI-approved. The correct description is **source-available for noncommercial
use**.

## Attribution

Cite the atlas version together with the underlying data resources: RCSB PDB, GPCRdb, UniProt.
See `CITATION.cff`.
