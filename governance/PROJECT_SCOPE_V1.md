# Project scope — v1 (frozen)

Class A GPCR Atlas. This document fixes what the project is and, more importantly, what it is
not. It is frozen: changing any statement here requires a new version of this file and an entry
in [`DECISION_LOG.md`](DECISION_LOG.md).

## 1. What this project is

A pipeline that builds a **raw, auditable universe** of Class A (rhodopsin-like) GPCR receptors
and experimentally determined structures from two official sources, and records every field it
takes with the URL it came from.

It is deliberately *not* a port of the existing aminergic pocket viewer. That application is a
frozen reference: it demonstrates that the scientific question is answerable for one family. It
does not demonstrate that its assumptions hold for eleven.

## 2. Scientific scope

| Dimension | In scope | Out of scope |
|---|---|---|
| Class | Class A (Rhodopsin), GPCRdb slug `001` | Classes B1, B2, C, F, T, Other |
| Families | all 11 Class A major families | — |
| Species | all species present in the source | (no species filter is applied) |
| Structures | all Class A entries listed by GPCRdb | — |
| Methods | all experimental methods, recorded as reported | (no method filter is applied) |
| Resolution | recorded as reported | (no resolution cutoff is applied) |

**No filter is applied in Phase 1.** Every exclusion is a scientific decision, and no scientific
decision is made in this phase. Records that fail a check are flagged and kept; see
[`READ_ONLY_POLICY.md`](READ_ONLY_POLICY.md) §4 and `config/qc_flags.json`.

The number of Class A families is **a datum read from the source, not an assumption**. It is
recorded in `data/manifests/class_a_family_manifest.json`, which is the authoritative answer.
Any downstream file that disagrees with that manifest is wrong.

## 3. Sources, and their licences

Two sources are called in Phase 1:

| Source | Role | Licence as stated by the provider |
|---|---|---|
| GPCRdb | Class A tree, receptor records, structure list | Data CC BY 4.0; code Apache 2.0 |
| RCSB PDB | entry metadata, entity inventory | PDB archive files: CC0 1.0 |

Four sources are deliberately **not** called; the reasons are recorded in
`config/source_endpoints.json` under `not_used_in_phase_1`:

- **UniProt** — licence not verified by this project. Unverified licence, no production use.
- **Guide to Pharmacology (GtoPdb)** — not required to build a structure universe.
- **ChEMBL**, **PubChem** — pharmacology sources; pharmacology is out of scope this phase.

An unverified licence is recorded as unverified. It is never presented as verified.

## 4. Phase boundaries

**Phase 0 — governance and scope freeze.** This document set, the configuration vocabularies,
and the read-only baseline.

**Phase 1 — taxonomy and structure universe.** The Class A hierarchy, the receptor set, the
structure set joined to RCSB, a raw component inventory, and one pilot family.

Explicitly forbidden in Phases 0–1, and not present in any artefact:

- 5 Å contact calculation, or any geometric analysis
- bulk coordinate download, PLIP, motif extraction
- shared-pocket prevalence, or any aggregate over pockets
- pharmacology class assignment; agonist / antagonist assignment
- primary-ligand selection
- binding-site type assignment; transducer-name normalisation
- NGL Viewer, HTML, CSS or JavaScript of any kind
- copying the aminergic interface or importing the aminergic builder
- starting the Peptide pilot
- GitHub deployment, Zenodo release

The test suite enforces the data-side prohibitions rather than trusting this list:
`tests/run_tests.py` fails if a Phase 2 field appears in the universe, if a primary ligand is
selected, or if a binding-site type, component category or transducer class is assigned.

## 5. Pilot family

The pilot is **Nucleotide receptors** (`001_006`): 100 structures, 6 receptors with structures,
2 receptor families. It was chosen because it is large enough to exercise every code path and
small enough to inspect by hand.

The Peptide family is the eventual scale test (356 structures, 32 receptor families) and is
**explicitly deferred** — the test suite fails if a Peptide family folder appears.

## 6. Independence from the frozen aminergic project

The aminergic project is a read-only reference. This project:

- does not import its data,
- does not import its builder,
- does not make it a runtime dependency,
- does not write to its directory.

Its conclusions are hypotheses to be re-tested here, not premises. In particular the 5 Å
contact definition, the `(receptor, ligand, activity_class)` deduplication unit, and the A/B
evidence levels are recorded in [`DEFERRED_DECISIONS.md`](DEFERRED_DECISIONS.md) as open
questions for Class A, not as inherited rules.

## 7. What "done" means for Phase 1

1. The taxonomy validates and its family count matches the manifest.
2. Every structure joins to a receptor and a family, or is flagged and kept.
3. Every emitted QC flag is declared in `config/qc_flags.json` before it is emitted.
4. Entity identifiers are retrievable for every structure, or the failure is recorded.
5. The pilot family folder is an exact projection of the universe.
6. The frozen aminergic project is byte-identical to its baseline.
7. Every artefact has a content hash that is independent of when it was generated.

All seven are checked by `tests/run_tests.py`.
