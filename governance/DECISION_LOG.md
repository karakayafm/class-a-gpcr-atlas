# Decision log

Chronological record of decisions taken, and of corrections made during the build. Corrections
are logged because a decision that was wrong once will look arbitrary later unless the reason it
changed is written down.

All entries: **2026-08-03**.

---

## Phase 0 — governance and scope freeze

**0.1 — Baseline taken before any work.** 350 files under `pymol_views/` hashed into
`_checksums_before.sha256`; manifest SHA-256 `c070673f5a02b5ba174bfc203849229f732e5d045b7e3002c401b73d0debff71`. Taken
first so that any later write is provable, not arguable. → `READ_ONLY_POLICY.md`

**0.2 — Standard library only.** No third-party dependency, recorded in `config/project.json`.
Accepted cost: a hand-written HTTP client and a partial JSON Schema validator. → AD-01

**0.3 — Two hashes per artefact.** `content_sha256` over the science, `package_sha256` over
everything, with an explicit `VOLATILE_KEYS` list rather than pattern matching. Verified
volatile-independent before use. → AD-03, AD-04, SD-13

**0.4 — Four sources deliberately not called.** UniProt (licence unverified), GtoPdb (not
required for a structure universe), ChEMBL and PubChem (pharmacology, out of scope). Recorded
in `config/source_endpoints.json` as `not_used_in_phase_1` with reasons, so that "not used" is
distinguishable from "forgotten". → `PROJECT_SCOPE_V1.md` §3, DD-06

**0.5 — Vocabularies as data with status flags.** Entity types, binding-site types, transducer
classes and QC flags placed in `config/*.json` carrying `production_ready`,
`assigned_in_phase_1`, `normalised_in_phase_1`. The test suite reads those flags, so a deferred
decision cannot be quietly un-deferred. → AD-09

**0.6 — Nucleotide chosen as pilot, Peptide explicitly deferred.** Nucleotide is large enough
to exercise every path (100 structures) and small enough to inspect. The test suite fails if a
Peptide family folder appears. → `PROJECT_SCOPE_V1.md` §5

---

## Phase 1 — taxonomy

**1.1 — Family count measured, not assumed.** The pipeline reads the count from the source tree
into `data/manifests/class_a_family_manifest.json`. Measured: 11 major families, 61 receptor
families, 29,867 receptor records, 1673 species, 287 human receptors. → SD-02

**1.2 — Correction: family manifest restructured to match its schema.** The first manifest used
`major_family_source_id` / `receptor_count` / `receptor_family_count` and carried no `counts`
block; `family_manifest.schema.json` specified `source_id` / `n_receptor_records` /
`n_receptor_families` plus `counts`. The manifest was changed, not the schema — the schema
describes what downstream code should be able to rely on, and weakening it to match a first
draft would have made it decorative. The taxonomy's `content_sha256` was `76db676e…` before and
after, which is exactly the evidence the two-hash split exists to provide. → SD-13

---

## Phase 1 — structure universe

**1.3 — 1358 Class A structures retrieved**, matching the discovery-phase count exactly
(Aminergic 395, Peptide 356, Lipid 157, Orphan 110, Nucleotide 100, Protein 82, Sensory 77,
Alicarboxylic acid 48, Melatonin 13, Steroid 10, Other 10).

**1.4 — Correction: experimental-method vocabulary.** The first build compared
`rcsb_entry_info.experimental_method` (`EM`, `X-ray`) against the full wwPDB vocabulary
(`ELECTRON MICROSCOPY`, `X-RAY DIFFRACTION`) and flagged **all 1356** resolved structures as
`method_not_experimental`. The data were fine; the check was comparing two different
vocabularies. Fixed by reading `exptl[].method` for the controlled term and keeping the RCSB
abbreviation in a separate field. Flag count fell from 1358 to 251. A check that fails on
everything is not a strict check, it is a broken one. → SD-10

**1.5 — Source disagreement kept, not reconciled.** 7XOX and 8ZFJ are listed by GPCRdb and
return HTTP 404 from the RCSB Data API (confirmed by direct request, not inferred from the
pipeline's own failure). Both remain in the universe flagged `rcsb_unresolved`; the universe
therefore has 1358 records of which 1356 carry RCSB metadata. → SD-09

**1.6 — `functional_pathway_evidence` pinned to null.** The GPCRdb signalling-protein
annotation is stored raw in a differently named field so a structural observation cannot be read
as a pathway claim. 798 structures carry an annotation, 560 do not. → SD-04

---

## Phase 1 — component inventory

**1.7 — Two-level inventory.** Availability for all 1358 structures; full entity records for the
pilot family only (100 structures, 560 entities: 155 polymer, 405 non-polymer, 0 branched, 0
fetch failures). Fetching every entity of every Class A structure would be ~10,000 requests for
data this phase does not analyse. → AD-08

**1.8 — Five new QC flags declared before use.** `component_is_water`,
`branched_entity_glycan`, `polymer_is_nucleic_acid`, `polymer_type_unrecognised`,
`entity_inventory_empty` added to `config/qc_flags.json`; the test suite refuses any flag not
declared there. → AD-10

**1.9 — Correction: `qc_flag.schema.json` rewritten to describe the real config.** The schema
had been drafted against an imagined shape (`flags`, `description`, `emitted_by`); the config
frozen in Phase 0 uses `qc_flags`, `meaning`, and a `none`/`info`/`medium`/`high` severity
scale. Here the config won, because it is the Phase 0 governance artefact and the schema was
the later draft. The general rule: the earlier frozen artefact wins unless there is a stated
reason to change it — and in 1.2 there was.

**1.10 — Correction: `structure.schema.json` widened for the raw transducer annotation.** The
GPCRdb annotation is an object for complexes (`{"data": {"entity1": {"chain": "D",
"entry_name": "gnas2_human"}, …}, "type": "G protein"}`), not a string or array. The schema was
widened to `["string", "array", "object", "null"]` and the description now shows the real shape.
Widening a schema to admit real source data is legitimate; widening it to admit a pipeline bug
is not, and this was the former.

---

## Phase 1 — pilot family and validation

**1.11 — Correction: manifest provenance hashes were null.** `source_manifest.json` read
`content_sha256_self` from the upstream artefacts — a key that does not exist, because hashes
are returned by the writer rather than embedded in the file. The manifest was silently claiming
a provenance chain it did not have. Fixed by recomputing `content_sha256` from the loaded
objects at manifest time. A provenance field that can be null without failing anything is worse
than no field.

**1.12 — Projection asserted in both directions.** The pilot folder is checked to contain
exactly the receptors and structures the universe assigns to `001_006` — set equality, not
subset. A projection that is merely a subset would hide a silent filter. → AD-07

**1.13 — Validator honesty enforced.** `assert_no_unsupported_keywords()` runs over all nine
schemas in the test suite, so the partial validator cannot report success on a schema it is
unable to check. → AD-01

**1.14 — Phase 1 validation: 83 checks, 0 failures**, including all 350 frozen files unchanged
and no frozen file deleted.

---

## Phase 2 — structure and ligand normalization (2026-08-04)

Phase 2 decisions and corrections are recorded in full in
`reports/phase2/PHASE2_DECISION_LOG.md`. Summary of what changed at project level:

**2.A — Five closed vocabularies added** (`entity_forms`, `biological_types`, `ligand_roles`,
`site_classes`, `analysis_eligibility`): 58 values, each with definition, inclusion rule,
exclusion rule, decision logic, permitted transitions and phase introduced. Tests fail on any
value outside them. → AD-09, AD-10

**2.B — Two evidence references added** (`component_reference.json`,
`polymer_role_reference.json`). Neither selects ligands; both describe chemistry and identity.
The single positive ligand rule is a per-structure source annotation. → SD-06, SD-07 now
implemented rather than deferred in form only.

**2.C — DD-06 partially closed.** UniProt licence verified independently (CC BY 4.0). GtoPdb
recorded as owner-provided official verification after a second retrieval failure. Neither is
called by the pipeline.

**2.D — Five Phase 2 schemas added.** Phase 0/1 schemas and artefacts were not modified; the
Phase 1 taxonomy and universe content hashes are re-verified by the Phase 2 test suite against
`data/freezes/phase_1/freeze.json`.

**2.E — Four corrections logged** (polymer pattern gaps, unattachable annotations claiming a
pharmacological role, an ID collision on a dual-mode annotation, a missing non-polymer
back-annotation) plus one wrong assumption in an edge-case selector about where chemokine
receptors sit in the taxonomy. All in `reports/phase2/PHASE2_DECISION_LOG.md`.

**2.F — Phase 2 validation: 93 checks, 0 failures**, including determinism across two runs and
the frozen aminergic manifest unchanged (350 files).

## Enrichment — chemical cross-references (2026-08-08)

**E.1 — Three of the four sources named in 0.4 are now called.** GtoPdb, ChEMBL and PubChem are
queried by `pipeline/enrichment/fetch_chemical_xrefs.py`, together with UniChem, to resolve each
chemical component to its entry in those databases. Responses are cached under `data/cache/`; a
normal build reads the cache and reaches no network. 0.4 recorded the position in Phase 1 and is
left as written.

**E.2 — What the release carries from them.** Per chemical component: the identifier, the link,
the retrieval date, the basis on which the match was made, the ambiguities that were not resolved,
and the source's preferred compound name where one was found — 219 ChEMBL, 300 GtoPdb and 484
PubChem labels across 580 records. Component name, formula and InChIKey come from the RCSB
chemical component dictionary, not from these three.

**E.3 — The share-alike gate is open again, on a narrower question.** Identifiers and links are
facts; the labels are content from databases published under CC BY-SA 3.0 (ChEMBL) and CC BY-SA
4.0 (GtoPdb contents). Whether carrying a preferred name alongside its identifier makes the atlas
a derivative is unresolved. Dropping the labels would remove the question and cost the interface
nothing, since it displays the identifier. → `RELEASE_DECISIONS_PENDING.json`
`SHARE_ALIKE_REVIEW_STATUS`, `reports/phase6a/DERIVED_DATA_REVIEW_PACKET.md` §3
