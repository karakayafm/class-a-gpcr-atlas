# Scientific decisions — v1 (frozen)

Decisions that affect what the data *means*. Each states the decision, the reason, and what
would have to be true to revisit it. Architectural choices live in
[`ARCHITECTURE_DECISIONS_V1.md`](ARCHITECTURE_DECISIONS_V1.md).

---

## SD-01 — The class is defined by the source, not by us

**Decision.** Class A membership is whatever GPCRdb's `001` subtree contains. We do not add,
remove or re-parent receptors.

**Reason.** GPCRdb's classification is itself a curated, citable scientific product. Silently
overriding it would produce a taxonomy that matches no published reference and could not be
compared with anything.

**Revisit if.** GPCRdb restructures Class A, or a specific receptor's placement is shown to be
wrong in the literature. Either way the override is recorded per receptor, never applied
globally.

---

## SD-02 — The family count is measured, not assumed

**Decision.** The number of Class A major families is read from the source tree at build time
and written to `data/manifests/class_a_family_manifest.json`. Nothing in the pipeline hard-codes
it. The measured value is **11**.

**Reason.** During discovery a summary listed ten family names, which raised the question of
whether the query was losing a family. It was not — the raw tree, the counts file and the
structure totals all say eleven, and the structure counts sum exactly to 1358. The discrepancy
was in prose, not in data. A hard-coded count would have hidden that; a measured count exposes
it. See `reports/phase_1/TAXONOMY_DISCREPANCY_RESOLUTION.md`.

**Revisit if.** Never as an assumption. The manifest is regenerated with the taxonomy.

---

## SD-03 — Nothing is excluded in Phase 1

**Decision.** No filter on species, method, resolution, date, or ligand presence. Records that
fail a check receive a QC flag and stay in the universe.

**Reason.** An exclusion is a scientific claim ("this structure cannot answer the question"),
and the question has not been posed yet. Excluding first and asking later makes the excluded set
invisible. `config/qc_flags.json` states the policy: *a flag never removes a record from the raw
universe*, and the schema pins that to be structurally unrepresentable.

**Revisit if.** Phase 2 defines an analysis whose preconditions a record provably cannot meet.
The exclusion is then applied at analysis time, on top of an unfiltered universe.

---

## SD-04 — A structural transducer annotation is not a pathway claim

**Decision.** The GPCRdb `signalling_protein` annotation is stored verbatim in
`transducer_observed_in_structure_raw`. The field `functional_pathway_evidence` exists and is
pinned to `null`.

**Reason.** These are different claims with different evidence. "A Gs heterotrimer is resolved
in this map" is a structural observation. "This ligand signals through Gs at this receptor" is a
pharmacological result from a functional assay. The frozen aminergic project keeps them apart as
evidence levels A and B; conflating them would let a crystallisation choice masquerade as
pharmacology. 798 of 1358 structures carry an annotation and 560 carry none — absence of the
annotation is absence of a co-resolved transducer, not absence of signalling.

**Revisit.** Not this decision. What is deferred is only *how* functional evidence is sourced —
see [`DEFERRED_DECISIONS.md`](DEFERRED_DECISIONS.md) DD-04.

---

## SD-05 — Transducer names are not normalised in Phase 1

**Decision.** `config/transducer_classes.json` defines nine classes with
`normalised_in_phase_1: false`. No structure record carries a normalised class.

**Reason.** The raw annotation is an object naming specific entities (`gnas2_human`,
`gbb1_human`, `gbg2_human`) plus a coarse type. Mapping those onto Gs / Gi / Gq / G12 requires
deciding how to treat chimeras, mini-G constructs, dominant-negative mutants and engineered
fusions — every one of which is a judgement call with pharmacological consequences. Making that
call inside a data-collection phase would bury it.

**Revisit if.** A normalisation rule is written, reviewed, and given its own decision record.

---

## SD-06 — No primary ligand is selected

**Decision.** Every non-polymer entity is inventoried; `primary_ligand_id` is pinned to `null`.

**Reason.** "The ligand" is not a property of a deposition. A Class A entry can contain an
orthosteric agonist, an allosteric modulator, a lipid, a cholesterol molecule, a detergent, an
ion, a fiducial nanobody and crystallographic water. Choosing one requires a rule that is
defensible across eleven families whose ligands range from small amines to whole proteins. The
aminergic project could pick the single HET component because for aminergic receptors that
choice is nearly always unambiguous. Across Class A it is not: 249 of 1358 structures have no
non-polymer component at all, and for a protein-receptor complex the ligand *is* a polymer chain.

**Revisit if.** Phase 2 defines the rule, per family if necessary, with the ambiguous cases
enumerated.

---

## SD-07 — Component categories are preliminary

**Decision.** `config/entity_types.json` defines ten entity types (source-stated, used) and
seven component categories (interpretive, `production_ready: false`). Only the source-stated
type is assigned; `component_category` is `null` everywhere.

**Reason.** Entity type is a fact the deposition states ("this is a non-polymer component").
Category is an interpretation ("this is a crystallisation additive rather than a ligand"), and
getting it wrong silently converts a real ligand into noise or vice versa. Water is the only
component the pipeline names, and it is named with a flag rather than a category.

**Revisit if.** A category rule is validated against a hand-checked set.

---

## SD-08 — Binding-site types are not assigned

**Decision.** `config/binding_site_types.json` defines ten site types with
`assigned_in_phase_1: false`.

**Reason.** Assigning a site type requires geometry, and geometry requires coordinates, which
Phase 1 does not download. Assigning it from the component name instead would be a guess wearing
the clothes of a measurement.

---

## SD-09 — Both sources are kept when they disagree

**Decision.** The GPCRdb record and the RCSB record are stored in separate fields. Disagreements
are flagged, never silently reconciled.

**Reason.** Two curated sources disagreeing is information. Two PDB identifiers listed by GPCRdb
(**7XOX**, **8ZFJ**) return HTTP 404 from the RCSB Data API. Merging the sources would have
produced a universe of 1356 with no trace of the other two; keeping both produces a universe of
1358 in which two records are flagged `rcsb_unresolved` and reported. See
`reports/phase_1/SOURCE_DISAGREEMENT_REPORT.md`.

---

## SD-10 — The experimental method is recorded in its full vocabulary

**Decision.** `experimental_method` carries the wwPDB controlled vocabulary from
`exptl[].method` (`ELECTRON MICROSCOPY`, `X-RAY DIFFRACTION`, `ELECTRON CRYSTALLOGRAPHY`);
`experimental_method_abbrev` carries the RCSB abbreviation (`EM`, `X-ray`).

**Reason.** They are two vocabularies, not synonyms, and the first build treated the
abbreviation as if it were the full term — which flagged all 1356 resolved structures as
"method not experimental". The check was wrong, not the data. Keeping both fields makes the
distinction visible instead of leaving it to be rediscovered. Measured distribution: 891
electron microscopy, 463 X-ray diffraction, 2 electron crystallography.

---

## SD-11 — Human is not privileged in the universe

**Decision.** All 29,867 receptor records across 1673 species are retained. Human counts (287
receptors) are reported alongside, never substituted.

**Reason.** Structures are determined in whatever species crystallises or vitrifies; restricting
the receptor set to human would orphan those structures. Filtering to human is an analysis
choice and belongs to the analysis.

---

## SD-12 — Identity is carried by the source key

**Decision.** Receptors are joined on the GPCRdb entry name (`p2ry1_human`); structures on the
uppercase four-character PDB identifier. Project-generated identifiers exist but carry a `ca-`
prefix and are never used as join keys.

**Reason.** A join key invented by this project would be unverifiable against either source. The
prefix means a project identifier can never be mistaken for an upstream one — the test suite
asserts the two sets are disjoint.

---

## SD-13 — A hash of the science, separate from a hash of the run

**Decision.** Every artefact gets a `content_sha256` computed after stripping volatile fields
(timestamps, cache paths, retry counts, HTTP status) and a `package_sha256` over everything.

**Reason.** Re-running the pipeline must be able to prove that the science did not change even
though the run did. The taxonomy demonstrates this: after the family manifest was restructured
and the pipeline re-run, `content_sha256` was still `76db676e…` while `package_sha256` changed.
Without the split, every re-run would look like a data change and the hashes would stop meaning
anything.
