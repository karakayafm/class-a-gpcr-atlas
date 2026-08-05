# Licence scope analysis

Prepared after the owner selected PolyForm Noncommercial 1.0.0 (code) and CC BY-NC 4.0
(project-created data and documentation), 2026-08-05.

**This is not legal advice.** It sets out what the licence texts say, what the release actually
contains, and which questions therefore need an answer from someone qualified. Every licence text
quoted was retrieved and hashed; the retrieval record is in
`data/licences/third_party/RETRIEVAL_RECORD.json`.

---

## 1. Why scoping is now load-bearing rather than tidy

Earlier this scoping item (decision D03 / gate G7) read like housekeeping: a `LICENSE` file at a
repository root would *look* like it covered everything. With a **noncommercial** licence selected
it stops being cosmetic, because ~92% of the release by size is material the project does not own
and may not restrict.

| Asset class | Share of release | Source licence | May the project apply NC to it? |
|---|---:|---|---|
| Coordinate bundles (1358 `viewer.cif`) | ~92% | **CC0 1.0** (RCSB) | No — public domain dedication; the project has nothing to license |
| GPCRdb-derived fields (taxonomy, receptor and structure annotation) | small | **CC BY 4.0** | See §2 — this is the clause that matters |
| UniProt accessions relayed via RCSB | negligible | CC BY 4.0 (verified) | identifiers; see §2 |
| Vendored NGL bundle (NGL, three.js, chroma.js, ColorBrewer, JS Signals, Kdtree) | 1.3 MB | MIT / BSD-3 / Apache-2.0 | No — remains under its own terms; notice already ships |
| **Project-created outputs** (182,169 contacts, generic-number mapping, 727 aggregation units, motif metrics, adjudications, the review-gated overlay) | small by bytes, the whole intellectual contribution | this project's | **Yes — this is what CC BY-NC 4.0 governs** |
| **Application and pipeline code** | 0.1 MB source | this project's | **Yes — this is what PolyForm NC governs** |

The owner's wording already states that source-derived materials retain their source licences.
The point of this report is that the statement has to be **precise and prominent**, not a closing
sentence, because of §2.

## 2. The CC BY 4.0 clause that constrains how NC may be applied

CC BY 4.0 §2(a)(5)(B), retrieved verbatim 2026-08-05 (SPDX text, SHA-256 recorded):

> **No downstream restrictions.** You may not offer or impose any additional or different terms or
> conditions on, or apply any Effective Technological Measures to, the Licensed Material if doing
> so restricts exercise of the Licensed Rights by any recipient of the Licensed Material.

Read against this release, that produces a clear split and one open question:

- **Clear:** the project may license *its own* contributions — the contacts it computed, the
  mapping it derived, the aggregates it designed, its code and its prose — under NC terms. CC BY
  4.0 does not require derivative works to be CC BY, and it is not a share-alike licence.
- **Clear:** the project may **not** present the redistributed GPCRdb-derived material itself as
  NC-restricted, because that would impose a different condition on the Licensed Material.
- **Open question for a qualified reviewer:** where a shipped payload interleaves a GPCRdb-derived
  field (for example a receptor family assignment or a structure-state annotation) with a computed
  value in the same JSON record, is the record "the Licensed Material" carrying a downstream
  restriction, or "an Adaptation" the project may license as it wishes? This project cannot answer
  that, and it is the concrete form of gate G7.

**The CC0 coordinates raise no such question** — CC0 is a public domain dedication, so there are no
Licensed Rights to restrict. But equally the project cannot grant, or withhold, anything over them.

## 3. What the scoping statement must therefore do

Three things, and the owner's supplied wording currently does the first two:

1. **Name what the NC licences cover** — project-created code, contacts, mappings, aggregates,
   motif metrics, adjudications, overlay and documentation. ✅ present.
2. **Name what they do not cover**, with the source licences. ✅ present.
3. **Make the exclusion structurally visible**, not only stated in prose — so that a user who
   downloads only the coordinate bundles is not left believing they are NC-restricted. ❌ not yet
   implemented. Recommended: a `LICENSE-SCOPE` manifest listing each shipped path prefix against
   its governing licence, and the same mapping in the in-application sources panel.

`data/release_overlays/` and `data/web/structures/` are cleanly separable path prefixes, so this is
mechanical rather than a drafting problem.

## 4. Consequences of the NC choice, stated as facts

None of these is an objection. They are effects the owner should be choosing deliberately.

- **NC output cannot flow back into the CC BY resources it derives from.** GPCRdb could not ingest
  this atlas's computed contacts under its own CC BY 4.0 terms without a separate grant. If
  contributing results upstream is ever an aim, the separate-written-agreement route in the
  owner's wording is the mechanism.
- **Not OSI open source, and must not be described as such.** `OPEN_SOURCE_STATUS` records this
  explicitly. Audited: no "open source" claim exists anywhere in the project — the only matches are
  the `opensource.org` URL inside NGL's own MIT header, which is third-party text and stays as
  written. A release test now enforces the absence.
- **"Noncommercial" is not defined identically by the two licences.** PolyForm Noncommercial and
  CC BY-NC 4.0 use different formulations, and neither draws a bright line for common academic
  cases: contract research, industry-funded academic work, a company scientist reading the atlas.
  Users will ask. A short FAQ stating the owner's intent — separate from the licence text — would
  prevent the project answering the same question case by case.
- **Some repositories and funders require open licences** for deposited outputs. Zenodo accepts
  NC; some institutional repositories and open-access mandates do not. This interacts with
  `PUBLICATION_TARGET` and with the DOI decision.
- **Attribution obligations survive regardless.** GPCRdb attribution under CC BY 4.0 is required
  whatever this project licenses its own work as.

## 5. Effect on the release gates

| Gate | Before | Now |
|---|---|---|
| G2 code licence | open (Apache-2.0 proposed) | **selected, not effective** — PolyForm NC 1.0.0 chosen, but `CODE_LICENSE_STATUS` is *pending confirmation of copyright holder* |
| G3 derived-data licence | open | **selected, not effective** — same condition |
| G4 share-alike | open | **direct question confirmed closed**; residual aggregator question no longer tracked — see §6 |
| G7 licence scoping | open | **open and now more important**, per §1–§3 |

**No `LICENSE` file has been written, and none may be, because a licence grant needs a grantor and
`COPYRIGHT_HOLDER` is unresolved.** A repository published with licence *text* but no confirmed
rights holder grants nothing reliably. This is now the single narrowest blocker: confirming the
copyright holder converts three conditional decisions into effective ones at once.

## 6. One thing that changed quietly, and should be confirmed

`SHARE_ALIKE_REVIEW_STATUS` moved from `..._residual_aggregator_inheritance_question_pending_institutional_confirmation`
to `not_applicable_to_direct_inputs_source_specific_licences_preserved`.

The new wording confirms the **direct** question, which the evidence already supported: GtoPdb,
ChEMBL and PubChem are not called, cached, stored or redistributed. The **residual** question — whether
an aggregator's CC BY 4.0 relicensing of material whose nomenclature originates with a CC BY-SA /
ODbL source carries any downstream obligation — is no longer mentioned.

It may have been deliberately closed, or it may simply be outside what that statement addresses.
The distinction matters for gate G4, so it is flagged rather than assumed either way.

## 7. Recorded, not decided

This report changes no decision and writes no licence file. It records what the selected licences
say, what the release contains, and the two things that still need a person: **confirmation of the
copyright holder**, and **a decision on the scoping question in §2** — which is a legal reading, not
a technical one.
