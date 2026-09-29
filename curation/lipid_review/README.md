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
| `not_a_ligand` | 3 | 8XXU, 8XXV, 9IYB: phosphatidylinositol. Decided by the reviewer on 2026-09-30. |
| `proposed_not_a_ligand` | 6 | Rhodopsin 4J4Q, 4PXF, 5TE3, 5WKT, 6NWE (octyl glucoside) and 4X1H (nonyl glucoside): a detergent recorded with binding mode "unknown" in ligand-free opsin. Awaiting a decision. |
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

## Re-running

```bash
python3 curation/lipid_review/audit_lipids.py
```
