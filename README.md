# Class A GPCR Structure–Ligand Contact and Interface Atlas

**Class A GPCR Contact Atlas** — version `0.1.0-beta.2`

Website: <https://karakayafm.github.io/class-a-gpcr-atlas/>

> **Research pre-release: This atlas is a technically validated beta covering Class A GPCR structures, ligand–receptor contacts, polymer ligand interfaces and core structural motifs. It provides no functional pathway activity data and no potency data of its own; reported affinities are relayed for 23 of its 578 components, from the one BindingDB subset whose licence permits redistribution. Some evidence records still require human review. Open records that affect identity or aggregation eligibility have been removed from public-beta pooled analyses by an issue-specific review gate. Reference testing of the contact rule and independent human validation vary by family and site class.**
>
> **Araştırma ön sürümü: Bu atlas, Class A GPCR yapıları, ligand–reseptör temasları, polimer ligand arayüzleri ve çekirdek yapısal motifler için teknik olarak doğrulanmış bir beta sürümüdür. Potens, afinite veya fonksiyonel yolak aktivitesi verisi sunmaz. Bazı kanıt kayıtları hâlen insan incelemesi gerektirmektedir. Kimliği veya agregasyon uygunluğunu etkileyen açık kayıtlar, public-beta toplu analizlerinden issue-specific review gate ile çıkarılmıştır. Temas kuralının referans testi ve bağımsız insan doğrulaması aile ve site sınıfına göre değişmektedir.**

---

## What this atlas contains

An interactive atlas of **1,358** experimentally determined Class A (rhodopsin-like) GPCR
structures across **11** GPCRdb major families, with:

- **182,169** receptor–ligand contacts at 5 Å, computed as exact minimum heavy-atom distances
  from deposited coordinates (4.0 and 4.5 Å also available)
- **727** aggregation units, each keyed by receptor accession × species × normalized ligand
  identity × ligand form × binding-site class × structural state
- Residue-level **GPCRdb generic numbering**, mapped through three candidate routes arbitrated
  against observed residue identity
- **8 core Class A motifs** defined by 21 generic positions, with residue identity measured
  rather than assumed
- 3D structure viewing for every entry, Turkish and English interfaces, light and dark themes
- Per-family offline exports (published as release assets)

## What this atlas does NOT contain

This section is as important as the one above.

- **No potency data.** No IC50, EC50, Ki or any measured activity value.
- **No affinity data.**
- **No functional pathway activity.** `functional_pathway_evidence` is null for all 1,358
  structures by design; Guide to Pharmacology, ChEMBL and PubChem are never called.
- **Ligand role labels are not measured pharmacology.** Labels such as orthosteric, allosteric,
  positive or negative allosteric modulator are binding-mode classifications relayed from source
  annotations. They are not evidence of measured pharmacological activity.
- **No structure–activity relationships.**
- **Not a primary database.** It derives from GPCRdb and the RCSB PDB and replaces neither.

## How this was built

Developed by Fatih Karakaya, with AI assistance from OpenAI Codex and Anthropic's Claude Code.
Those tools wrote a substantial part of the pipeline code and the web interface, working to the
author's direction; commits carry a co-author trailer where that assistance was used.

The scientific requirements, the architectural decisions, the curation rules, the verification
of the data and the maintenance of the project are the author's own responsibility. No AI system
is an author of this work.

## Public-beta status

- **189 review items await human decision.** Not one has been decided.
- **Two observations** are excluded from public-beta pooled analyses by the review gate, because
  their unresolved review items can change site classification (see below).
- The atlas is **not fully curated**, and no accuracy figure exists for its automated evidence
  adjudication — none can be computed until human decisions exist.

## Scientific scope

| | |
|---|---:|
| Structures | 1,358 |
| Major families | 11 |
| Contacts at 5 Å | 182,169 |
| Aggregation units | 727 |
| Core motifs | 8 |
| Review items awaiting human decision | 189 |

### Major families

Aminergic, Peptide, Protein, Lipid, Melatonin, Nucleotide, Steroid, Alicarboxylic acid, Sensory,
Orphan, Other — read from the GPCRdb Class A tree at build time, never hard-coded.

### Pocket versus polymer-interface distinction

A small-molecule 7TM pocket and a receptor–polymer interface are **different analysis objects and
never share a denominator**. This is the project's central methodological commitment. A 5 Å shell
around a 30-residue peptide is not the same object as a 5 Å shell around adrenaline, and the
atlas does not pool them.

### Review-gating policy

Public-beta pooled summaries exclude observations or structure slots whose unresolved review
items can alter receptor identity, ligand identity, site classification, coordinate context or
aggregation eligibility. **Metadata-only review items remain visible and remove nothing.**

The policy is *"open items visible and excluded from pooled analyses where required"* — it is
**not** "all open items are excluded". Of the 189 open items: 120 were already excluded upstream,
34 have no effect on any pooled metric, 33 are warnings, and **2 cause an exclusion**. A blanket
"same PDB, drop the unit" rule would have removed 48 units; the issue-specific gate removes 2.

Details: `docs/REVIEW_GATING_IMPLEMENTATION.md`, `docs/REVIEW_GATING_COUNTS.md`.

### Validation-scope disclosure

**Contact-rule validation varies by family and site class.** The interface shows this on every
family card, in each family overview, and beside every contact number.

| Scope | Status |
|---|---|
| Aminergic small-molecule pocket | Reference-tested against **nine** aminergic small-molecule structures, and cross-checked against a frozen predecessor over 323 observations (3 discrepancies) |
| Other families, small-molecule pocket | **Transferred** from the aminergic workflow **without a family-specific reference test**. Independent human validation not completed. |
| Polymer interfaces | The 5 Å value is a **descriptive interface shell**, not a validated biological interface threshold. It is not pocket validation. |
| Covalent sites | The covalent bond is evidenced by deposited connectivity records; the surrounding 5 Å shell is **not** reference-tested. |

Details: `docs/CROSS_FAMILY_VALIDATION_DISCLOSURE.md`.

## Installation / local serving

No build step and no dependencies. The site is static files.

```bash
git clone https://github.com/karakayafm/class-a-gpcr-atlas.git
cd class-a-gpcr-atlas/site
python3 -m http.server 8801
# open http://localhost:8801/index.html
```

The pipeline is **Python ≥ 3.10, standard library only** — nothing to install.

## GitHub Pages website

<https://karakayafm.github.io/class-a-gpcr-atlas/>

## Offline family exports

Each of the 11 families is available as a self-contained export that runs with no network. They
are published as **release assets** rather than in the repository, because together they exceed
the size that belongs in a Git tree. Each carries its own licence and third-party notices.

## How to cite

Cite `10.5281/zenodo.21901790` together with the underlying data resources (RCSB PDB, GPCRdb,
UniProt). That DOI resolves to the most recent release; release 0.1.0-beta.2 is
`10.5281/zenodo.21901791` if you need to cite one exactly. `CITATION.cff` in the repository root
carries both.

Do not cite this build as a curated or validated resource.

## Licensing

- **Code** — PolyForm Noncommercial License 1.0.0 (`LICENSE`)
- **Project-created data and written content** — CC BY-NC 4.0 (`LICENSE-DATA`)
- **Scope, and what the project licences do *not* cover** — `LICENSE-NOTICE.md`,
  `LICENSE-SCOPE.json`
- **Third-party software** — `THIRD_PARTY_NOTICES.md`
- **Source data** — `SOURCE_DATA_LICENSES.md`

Both licence texts are distributed **unmodified**. Scope is stated separately, never inside them.

**Approximately 92% of this distribution by size is CC0 coordinate data from the RCSB PDB, which
the project licences do not cover.** GPCRdb-derived fields remain CC BY 4.0.

This is **source-available for noncommercial use**. It is **not** open source and not
OSI-approved. Commercial use requires separate written permission from the copyright holder.

## Data sources

| Source | Role | Licence as stated by the provider |
|---|---|---|
| [RCSB PDB](https://www.rcsb.org/) | coordinates, entry metadata, entity inventory | PDB archive files: CC0 1.0 |
| [GPCRdb](https://gpcrdb.org/) | taxonomy, receptor list, structure list, annotations | Data CC BY 4.0; code Apache 2.0 |
| [UniProt](https://www.uniprot.org/) | accessions relayed through RCSB records | CC BY 4.0 |
| [PDB Chemical Component Dictionary](https://www.wwpdb.org/data/ccd) | chemical components | part of the PDB archive |

Data retrieved 2026-08-03/04. See `DATA_PROVENANCE.md`.

## Limitations

1. **No human curation.** 189 review items are open; none is decided.
2. **Contact-rule validation is not uniform.** Ten of eleven families inherited the 5 Å definition
   without a family-specific reference test.
3. **Polymer interfaces use a descriptive shell**, not a validated biological threshold.
4. **A blind spot exists**: 45 covalent-ligand entities produced no review item at all. That is
   not evidence they are correct — it means no check examined them.
5. **One GPU, two browsers.** Validated on NVIDIA hardware in Chromium and Firefox. WebKit/Safari
   is untested.
6. **No manual accessibility testing** with assistive technology has been performed. 67 automated
   checks pass; that is not a WCAG conformance claim.
7. **No maintenance commitment** beyond the single maintainer named below.

## Error reporting

- **Scientific data corrections and software bugs:** [GitHub Issues](https://github.com/karakayafm/class-a-gpcr-atlas/issues)
- **Security or data-integrity issues that should not be public:** edu.mfatih@gmail.com (see `SECURITY.md`)

Corrections are welcome and wanted. Every value links to its primary source so that any figure
can be checked against the deposition it came from.

## Maintainer

**Muhammed Fatih Karakaya** — Cancer Signaling Laboratory, Boğaziçi University
Contact: edu.mfatih@gmail.com

Copyright © 2026 Muhammed Fatih Karakaya.

## Acknowledgements

Developed as part of research conducted at the
[Cancer Signaling Laboratory](https://csl.bogazici.edu.tr/), Boğaziçi University.

Structural data from the RCSB PDB; receptor taxonomy and annotations from GPCRdb; 3D
visualisation by [NGL Viewer](https://github.com/nglviewer/ngl).
