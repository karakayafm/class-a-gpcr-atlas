# Lipids and detergents: what the bundles carry, and which ones are counted as ligands

Prepared 2026-09-30 against release `0.1.0-beta.2`. Nothing in the release data is changed here.

## Why

8XXU and 8XXV are apo structures whose only hetero group, A1D5Q, is phosphatidylinositol; the
record counts it as a positive allosteric modulator. 9IYB carries the same lipid and the record calls
it PGD2 (Agonist) because the annotated PGD2 is absent from the coordinates and its label reached the
lipid. A component becomes a ligand in this atlas only through a per-structure source annotation
(`config/component_reference.json`), so a lipid the source annotates as a ligand is carried as one.

## What the audit does

`audit_lipids.py` (standard library only) reads every viewer bundle and classes each hetero component
as a membrane lipid or a detergent by the component reference, or, where the reference has no entry,
by its chemical name (phospho- and lysolipids written out systematically, sterols, monoacylglycerols,
glucoside and maltoside detergents). The name rules found what the reference missed: A1D5Q, PEF,
the lysophosphatidylserines, BNG and LDA.

- `lipid_components.csv` - 23 components in 237 bundles. Monoolein (130), cholesterol (112) and oleic
  acid (106) account for most of them. This is what the viewer's *Lipids* layer draws.
- `lipid_as_ligand.csv` - the 20 observations whose ligand is one of those components.
- `lipid_as_ligand_decisions.csv` - the same rows with a decision.

| status | rows | |
|---|---|---|
| `not_a_ligand` | 9 | 8XXU, 8XXV, 9IYB: phosphatidylinositol. Rhodopsin 4J4Q, 4PXF, 5TE3, 5WKT, 6NWE (octyl glucoside) and 4X1H (nonyl glucoside): detergent in the retinal pocket of opsin that GPCRdb lists as apo. Decided by the reviewer on 2026-09-30. |
| `keep_ligand` | 11 | Published lipid ligands of lipid receptors: lysophosphatidylserine and analogues at GPR34, GPR174, P2Y10; oleic and palmitic acid at FFAR4, GPR3, GPR6. |

Nothing is demoted automatically, because lipid receptors have lipid ligands: oleic acid is a bulk
lipid in 103 bundles and the agonist in 8ID6.

## The viewer's lipid layer

*Lipids* (off by default) draws the membrane lipids and detergents of the bundle as thin grey sticks,
and leaves out any component the record counts as that structure's ligand. The component list is in
`app/js/viewer/viewer.js` (`LIPID_COMPONENTS`) and comes from `lipid_components.csv`. Where the bundle
carries no lipid the button is disabled and says so; many cryo-EM bundles carry none, because
auxiliary and environment chains are left out of the bundle for size.

Once the three phosphatidylinositol records are corrected in the data, the lipid will move from the
ligand layer to this one without a change to the viewer.

## Applied to the pipeline (2026-09-30)

Phosphatidylinositol in 8XXU, 8XXV and 9IYB, and the detergent in the six opsin structures
(decided: GPCRdb lists them as apo; the detergent sits in the retinal pocket and that is kept as a
structure note, not as a ligand), are written into `pipeline/phase5/build_payloads.py`
(`CURATED_APO_STRUCTURES`, `CURATED_NON_LIGAND_STRUCTURES`, `CURATED_STRUCTURE_NOTES`) for the next
full build. The eleven lipid ligands of lipid receptors stay ligands.

## Recovering the lipids the bundles left out (2026-09-30)

A bundle carried lipids only when the whole of its auxiliary and environment content fitted a
450 kB budget, so 1,086 of 1,358 bundles carry none - and 289 of those structures have lipids or
detergents in their deposited models (RCSB entry records). Two fixes:

- **Next build.** `pipeline/phase5/build_bundles.py` puts every membrane lipid and detergent within
  6 Å of the receptor into the bundle, outside the budget, and lists them in `viewer_meta.json`
  (`lipid_residues`). The component list is the component reference's membrane_lipid and detergent
  entries, to which ten components found here were added (A1D5Q, J40, D21, PEF, DAO, A6L, BNG,
  BGL, LDA, LMN). The phospho- and lysolipids that are lipid receptors' ligands were not added.
- **Now.** `pipeline/overlays/build_lipid_overlay.py` applies the same rule to the RCSB entries and
  writes `site/data/web/overlay/structures/<PDB>/lipids.cif` beside the frozen bundles, with
  `overlay/lipids_index.json` recording the source, its hash and the rule. 271 structures, 1,391
  lipid residues (cholesterol 496, oleic acid 188, palmitic acid 151, monoolein 149), 3.2 MB in
  all. Coordinates are copied unchanged; the downloaded entries are cached in `data/cache/coordinates`,
  where build_bundles.py reads them.

The viewer's *Lipids* layer draws the bundle's own lipids where it has them and loads the overlay
file where it does not; both are in the deposited frame, so the overlay needs no transformation.

## Re-running

```bash
python3 curation/lipid_review/audit_lipids.py
python3 pipeline/overlays/build_lipid_overlay.py        # downloads RCSB entries once, then cached
```
