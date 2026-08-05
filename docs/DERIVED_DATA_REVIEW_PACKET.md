# Derived data review packet

Phase 6A. For institutional review of what this project would redistribute, under what upstream
terms, and which questions must be answered by a person rather than by a pipeline.

Companion file: `DATA_DISTRIBUTION_MATRIX.csv` — the same content as a table, generated from the
release candidate's actual contents rather than written by hand.

**This packet decides nothing.** It states facts and marks the open questions.

---

## 1. What the release would redistribute

Measured from release candidate `0.1.0-rc.2`.

| Asset class | Files | Size | Share of release |
|---|---:|---:|---:|
| Structure coordinate bundles (`viewer.cif`) | 1358 | 484.2 MB | 45.9% |
| Per-structure viewer metadata | 1358 | 7.7 MB | 0.7% |
| Family payloads | 130 | 26.6 MB | 2.5% |
| Global payloads | 8 | 2.2 MB | 0.2% |
| Application code (this project's) | 13 | 0.1 MB | <0.1% |
| Vendored third-party code (NGL bundle) | 1 | 1.3 MB | 0.1% |
| Offline family exports (a repackaging of the above) | 3088 | 533.8 MB | 50.6% |
| **Total** | **5956** | **1055.8 MB** | |

**The single most important fact for this review: roughly 92% of the release by size is
coordinate data placed in the public domain under CC0 1.0 by the wwPDB/RCSB.** Counting the
offline exports, coordinates and their repackaged copies dominate everything else by two orders
of magnitude. Whatever is decided about licensing this project's own contribution, it applies to
a small fraction of the bytes and to essentially all of the intellectual content.

## 2. Upstream sources, and their status

| Source | Called by the pipeline? | Licence as stated by the provider | Verification status |
|---|---|---|---|
| RCSB PDB | **yes** — entry metadata, entity inventory, coordinates | PDB archive files: CC0 1.0 | provider statement |
| GPCRdb | **yes** — taxonomy, receptor list, structure list, annotations | Data CC BY 4.0; code Apache 2.0 | provider statement |
| UniProt | **no** — accessions relayed through RCSB records | CC BY 4.0 on copyrightable database content | **verified by this project 2026-08-04**, response SHA-256 `5960c22b…` |
| Guide to Pharmacology | **no** | Database ODbL; contents CC BY-SA 4.0 | **owner-provided, not verified by this project** — direct retrieval failed twice |
| ChEMBL | **no** | CC BY-SA 3.0 | not verified, not needed |
| PubChem | **no** | NCBI public domain statement | not verified, not needed |

Verified by re-reading the pipeline source for this packet: no module imports, calls, or
redistributes GtoPdb, ChEMBL or PubChem content. The only occurrences of those names in the
codebase are explicit `not_used` records and a curation packet field that is fixed at `null` so
a curator can see the source was not consulted.

## 3. The share-alike question — narrowed, not closed

The open gate carried since Phase 2 was whether ODbL / CC BY-SA share-alike obligations from
GtoPdb attach to this project's derived data.

**Direct attachment: no.** Share-alike is triggered by using the licensed material. GtoPdb is
not called, not cached, not stored and not redistributed. There is no GtoPdb content in the
release to trigger anything.

**The residual question, which this project cannot answer and does not attempt to.** GPCRdb's
receptor classification and nomenclature — the family tree this atlas is organised around, the
one that produces "Class A", the eleven major families and the 61 receptor families — follows
IUPHAR/BPS nomenclature, and IUPHAR/BPS nomenclature is what the Guide to Pharmacology
publishes. This project takes that classification from GPCRdb, which states CC BY 4.0 over its
data.

So the question for institutional review is not *"did we use GtoPdb"* — demonstrably no — but:

> When an upstream aggregator relicenses under CC BY 4.0 material whose underlying nomenclature
> originates with a CC BY-SA / ODbL source, does a downstream user of the aggregator inherit any
> share-alike obligation?

That is a question about the relationship between two providers' terms. It is a legal question,
not a technical one, and answering it from inside the pipeline would be exactly the kind of
convenient reasoning this project has avoided elsewhere. **It is stated here so that a reviewer
sees it, and left open.**

Two observations that may help whoever reviews it, offered as facts rather than conclusions:

- What is taken from GPCRdb is largely **factual and non-copyrightable in character**: which
  receptor a structure contains, which family it belongs to, which PDB identifiers exist. The
  atlas does not reproduce GPCRdb's prose, figures or database structure.
- The classification is used as an **organising axis for display**, and the scientific claims of
  the atlas — contacts, prevalence, motif metrics — are computed from CC0 coordinates, not from
  GPCRdb content.

Neither observation resolves the question. Both are for the reviewer to weigh.

## 4. Attribution obligations that are certain

Independent of §3, and applying under CC BY 4.0 as GPCRdb states it:

- **GPCRdb must be attributed** wherever the atlas is distributed. The release does this in the
  in-application reference panel (`data/web/global/references.json`), which names GPCRdb, RCSB
  PDB, UniProt and the PDB Chemical Component Dictionary with their licences and URLs.
- **RCSB attribution is not legally required** (CC0 is a public domain dedication) but is
  requested as scholarly courtesy, and is provided.
- **Per-structure citation** is supported: every structure links to its RCSB DOI via the
  documented `https://doi.org/10.2210/pdb{ID}/pdb` pattern. These are real, resolvable DOIs
  minted by RCSB — they are not this project's DOIs, and the atlas has none of its own.

**Reviewer check:** confirm the attribution wording in the reference panel is adequate for CC BY
4.0 as the institution reads it. The current wording states source name, URL and licence. It
does **not** state a specific GPCRdb release version, because the pipeline records retrieval
dates rather than a GPCRdb version string — see §7.

## 5. What is genuinely this project's own

Not derived, not relayed: computed here from CC0 coordinates.

| Output | Nature |
|---|---|
| 182,169 contacts at 5 Å (plus the 4.0 and 4.5 Å sets) | exact minimum heavy-atom distances computed from deposited coordinates |
| Residue-level generic numbering mapping | three-route arbitration validated by residue identity |
| 727 aggregation units and their prevalence metrics | aggregation designed and implemented here |
| Motif metrics over 8 Class A motifs | computed here |
| The evidence adjudication records | computed here; explicitly **not** human curation |
| The application, its schemas, its pipeline | written here |

This is the material a licence decision (DD-12) actually governs.

## 6. Personal data

None. The release contains no personal data of any kind: no user accounts, no telemetry, no
analytics, no cookies, no server. The only names anywhere in the corpus are the author names in
structure citation metadata relayed from RCSB, which are published bibliographic data. The
curation workflow will record curator names when humans use it — those records live in
`data/curation/` and are **not** part of the distributed site. Detail in
`SECURITY_PRIVACY_AUDIT.md`.

## 7. Known gaps a reviewer should see

1. **No upstream version pinning for GPCRdb.** The pipeline records retrieval dates (2026-08-03)
   and per-request response hashes, but GPCRdb does not expose a release version this project
   captured. Reproducibility rests on the cached responses and their hashes, not on a version
   string. If the institution's attribution practice expects "GPCRdb release X", that string
   does not currently exist and must not be invented.
2. **GtoPdb licence remains owner-provided, not independently verified.** Two retrieval attempts
   failed with DNS resolution errors while other hosts responded in the same session. This does
   not affect §3's conclusion that GtoPdb is not used, but the record should say what it is.
3. **The redistribution of 484 MB of CC0 coordinates is a choice, not a necessity.** The atlas
   could link to RCSB instead of bundling. Bundling was chosen so the offline exports work
   without a network. CC0 permits it outright; the question is whether the institution wants to
   host and serve a near-complete mirror of a slice of the PDB. This is listed as an owner
   decision in `OWNER_RELEASE_DECISION_FORM.md`, not as a licensing problem.
4. **Two version identifiers coexist in the release.** The shipped payloads carry
   `"version": "5.0.0-pre"` (the Phase 5 artefact) while the release-candidate metadata carries
   `0.1.0-rc.2`. Both are visible in the distributed files. This was **not** silently corrected,
   because the payload is a frozen Phase 5 artefact and rewriting it would change scientific
   hashes for a cosmetic reason. The version scheme is an owner decision.

## 8. Summary for the reviewer

| Question | Answer |
|---|---|
| Does the release contain material this project may not redistribute? | **No source prohibits redistribution.** All are CC0, CC BY 4.0, or permissive-licensed software. |
| Is any share-alike obligation directly triggered? | **No** — the ODbL/CC BY-SA sources are not used. |
| Is any share-alike question genuinely closed? | **No** — see §3, the aggregator-inheritance question, which is left for review. |
| Is attribution currently provided? | Yes, in-application. Adequacy is for the reviewer to confirm. |
| Is personal data involved? | No. |
| What blocks release on the data side? | §3 review, and the owner's DD-12 licence decision. |
