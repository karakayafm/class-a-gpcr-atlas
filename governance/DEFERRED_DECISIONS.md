# Deferred decisions

Questions this project must answer before it can make a scientific claim, and has deliberately
**not** answered in Phases 0–1. Each records what is undecided, why it could not be settled now,
what would settle it, and what currently blocks it.

Nothing here is a placeholder for a decision already secretly made. Where the frozen aminergic
project has an answer, that answer is listed as *a candidate*, not as inherited law — it was
validated for one family out of eleven.

---

## DD-01 — What counts as "the ligand"

**Undecided.** Which entity in a deposition is the ligand of interest.

**Why deferred.** See SD-06. Across Class A the answer ranges from a single non-polymer
component to a whole polymer chain, and 249 of 1358 structures have no non-polymer component at
all.

**Candidate rule (aminergic).** The single HET component that is not water, ion, lipid or
cryoprotectant. Validated for aminergic receptors only.

**What would settle it.** A rule stated per family, tested against a hand-checked sample from
each of the eleven families, with the ambiguous cases enumerated rather than resolved silently.

**Blocked by.** Nothing external. This is analysis work.

---

## DD-02 — The canonical ligand identity key

**Undecided.** Whether two ligands in different structures are "the same ligand" —
`chem_comp_id`, InChIKey, a cross-source mapping, or something family-specific.

**Why deferred.** The choice determines every downstream count. `chem_comp_id` splits
stereoisomers and salt forms that a pharmacologist would call one compound; an InChIKey merges
things a structural biologist would keep apart.

**Candidate rule (aminergic).** The deduplication unit
`(receptor, canonical_ligand_id, activity_class)`, with replicates collapsing to one vote.

**What would settle it.** A licence-verified chemical identity source and a written rule for
stereochemistry, protonation and salt forms.

**Blocked by.** DD-06 (licence verification).

---

## DD-03 — Binding-site assignment

**Undecided.** How a bound component is assigned to the orthosteric pocket, an allosteric site,
a lipid-facing site, or the transducer interface.

**Why deferred.** It requires coordinates, and Phase 1 downloads none.

**What would settle it.** A geometric criterion applied to downloaded coordinates, benchmarked
against structures whose site assignment is stated in the primary literature.

**Blocked by.** A decision on bulk coordinate download (DD-08).

---

## DD-04 — Where functional pathway evidence comes from

**Undecided.** The source and the acceptance criteria for functional (non-structural) evidence
that a ligand–receptor pair signals through a given transducer.

**Why deferred.** The candidate sources (GtoPdb, ChEMBL) have licence questions open, and the
curation the aminergic project used was manual and covers a handful of pairs.

**Candidate rule (aminergic).** Evidence level A = a transducer chain resolved in the
deposition; level B = a published functional assay, curated by hand with a figure-level
citation.

**What would settle it.** A licence-verified source plus a written acceptance criterion. Note
that manual curation at Class A scale is a different proposition from manual curation for three
receptors — during ADRB curation a figure reference supplied by an external tool was wrong on
inspection and had to be corrected against the paper. At 287 human receptors that failure mode
needs a process, not vigilance.

**Blocked by.** DD-06.

---

## DD-05 — Transducer normalisation

**Undecided.** How raw signalling-protein annotations map onto Gs / Gi/o / Gq/11 / G12/13 /
arrestin, and how to treat mini-G constructs, chimeras, dominant-negative mutants and fusions.

**Why deferred.** See SD-05. Every one of those cases is a judgement with pharmacological
consequences.

**What would settle it.** A written mapping table with an explicit policy for engineered
constructs, reviewed against the constructs actually present in the 798 annotated structures.

**Blocked by.** Nothing external.

---

## DD-06 — Licence verification for pharmacology and sequence sources

**Undecided.** Whether UniProt, GtoPdb, ChEMBL and PubChem data may be used in production
output, and under what attribution.

**Status of each** (updated 2026-08-04, Phase 2):

- **UniProt** — **VERIFIED by this project, 2026-08-04.** CC BY 4.0 on copyrightable database
  content, retrieved from `https://rest.uniprot.org/help/license` (response SHA-256
  `5960c22b…`, source lastModified 2024-12-18). Note that the HTML page at
  `https://www.uniprot.org/help/license` is a JavaScript shell containing no licence text; the
  REST help endpoint carries the canonical wording. DD-06 is **closed for UniProt**.
- **GtoPdb** — **owner-provided official verification, not verified by this project.** The owner
  supplied: database ODbL, database contents CC BY-SA 4.0, current version 2026.2. Direct
  retrieval failed again in Phase 2 (`Temporary failure in name resolution`), host-specifically:
  `data.rcsb.org` and `www.uniprot.org` responded in the same session. Recorded as
  owner-provided; **not** presented as self-verified.
- **ChEMBL** — CC BY-SA 3.0 per the provider's page. Not called.
- **PubChem** — NCBI public domain per NCBI's statement. Not called.

**Effect.** Neither licence blocks Phase 2 technical work, and neither source is called by the
Phase 2 pipeline. Two release gates remain open and must close before any public release: this
project's own code/output licence (DD-12), and institutional review of the ODbL / CC BY-SA
share-alike effect on derived data. See `reports/phase2/LICENSE_VERIFICATION_UPDATE.md`.

**What would settle it.** Retrieving each provider's own licence page and recording it verbatim
with the retrieval date. Not a secondary summary, and not an assumption.

**Blocked by.** Provider availability for GtoPdb only. UniProt is resolved.

---

## DD-07 — Whether the 5 Å contact definition transfers

**Undecided.** Whether the aminergic project's contact definition — minimum heavy-atom to
heavy-atom distance ≤ 5 Å, altlocs `' '` and `'A'`, hydrogens excluded — is appropriate for
peptide, protein and lipid receptors.

**Why deferred.** It was validated against an independent QC table for nine reference
structures, all aminergic, all small-molecule. A 5 Å heavy-atom shell around a 30-residue
peptide is a different object from a 5 Å shell around adrenaline, and "the pocket" may not be
the right abstraction for a protein-receptor complex at all.

**What would settle it.** Re-validation per family against structures whose interface residues
are stated in the primary literature.

**What is in place (2026-08-12).** The part that needs no literature is measured:
`pipeline/validation/analyse_contact_rule_sensitivity.py` recomputes every observation's receptor
set at 4.0 Å and 5.0 Å and reports what the outer angstrom contributes. Across the 17 cells
carrying at least eight observations it contributes 23–37%, median 29%, with the canonical pocket
and the extracellular polymer interface within a few points of each other. So the rule does not
behave differently *in kind* between site classes; they differ in scale and in ligand size — 15–25
receptor residues per ligand residue in the pocket, 1–4 where the ligand is a polymer chain. This
removes one specific worry stated above. It validates nothing: there is no ground truth in it.

The literature half is prepared rather than done. `build_contact_rule_worksheet.py` ranks cells by
how much rests on them and how far their geometry sits from the one cell that was tested, and
draws the sharpest, median and least sharp structure from each — 18 structures over 6 cells, each
with its primary DOI, in `curation/contact_rule_reference.csv`. The `paper_residues` column is
empty and is meant to be filled by a reader; nothing infers it.
`tests/validation/test_contact_rule_reference.py` reads the completed sheet, compares on author
numbering and reports agreement per cell. With no rows filled it reports SKIPPED rather than
passing.

**Blocked by.** DD-01, DD-08, and a reader for the 18 papers.

---

## DD-08 — Bulk coordinate download

**Undecided.** Whether, when and how to download coordinates for up to 1358 entries, and where
to store them.

**Why deferred.** It is out of Phase 1 scope, and the storage and re-download policy should be
decided together with the contact definition that consumes it.

**What would settle it.** A written policy covering format, assembly vs asymmetric unit,
altloc and hydrogen handling, storage location, and re-download triggers.

---

## DD-09 — Whether generic numbering is available for every family

**Undecided.** Whether GPCRdb generic (helix × position) numbering has the coverage across all
eleven families that the aminergic viewer relies on, and how gaps are represented.

**Why deferred.** No residue-level data is fetched in Phase 1.

**What would settle it.** A coverage measurement per family before any interface promises
motif-level labelling.

---

## DD-10 — Species policy for analysis

**Undecided.** Whether analysis is restricted to human receptors, human-plus-orthologues, or
unrestricted.

**Why deferred.** The universe is unfiltered by design (SD-11); the analysis question does not
exist yet.

**What would settle it.** The Phase 2 research question, stated explicitly.

---

## DD-11 — Inclusion criteria for production

**Undecided.** Which QC flags disqualify a record from a given analysis.

**Why deferred.** A flag describes a record; disqualification is relative to a question. The two
`rcsb_unresolved` records (7XOX, 8ZFJ) are unusable for anything needing RCSB metadata and
perfectly usable for counting what GPCRdb lists.

**What would settle it.** A per-analysis inclusion table, written when the analysis is.

---

## DD-12 — Publication, licensing and deposition of this project's own output

**Undecided.** The output licence, the citation record, the DOI, and whether output is deployed
at all.

**Why deferred.** Out of Phase 0–1 scope, and it depends on the licences resolved in DD-06.

**Note.** The frozen aminergic project carries an open licence decision of its own
(`LICENSE_DECISION_REQUIRED.md`). No DOI, ORCID, date, author or licence is to be invented
here — that constraint applies to this project's own metadata as much as to its sources.
