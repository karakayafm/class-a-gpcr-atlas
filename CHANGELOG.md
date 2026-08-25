# Changelog

## Unreleased

### Viewer

- **Superposition.** A second structure — or a third — can be laid over the one on screen from
  the viewer's side panel. The fit is over the CA atoms of the generic-numbered positions the two
  structures share, so depositions of one receptor and structures of different receptors are the
  same operation; the panel reports the RMSD and how many positions carried it. Each structure in
  the scene takes one colour through its cartoon, side chains and ligand, with nitrogen, oxygen and
  sulfur keeping theirs, and residue labels carry the structure's colour in their text.
- **Active structure.** With something superposed, the panel's controls address whichever structure
  is selected in the strip at the top: its cartoon, side chains, ligand, contact labels, interaction
  lines, its pocket and ligand surfaces, and its own whole-receptor position list. Each structure's
  pocket surface takes that structure's colour, so two of them in one site can be told apart.
- **Measurement across structures.** Distances, angles and torsions can be taken between atoms of
  different superposed structures. Each atom is named by the generic position of the structure it
  belongs to, and the readout and the exported table name that structure.
- **Interaction types.** Interactions opens three layers that can be shown separately: the ligand's
  contacts with the receptor, the contacts between different transmembrane helices, and those within
  one helix. Hydrogen bonds are drawn in light green and hydrophobic contacts in mustard; the other
  types keep the viewer's existing colours. The helical layers are scoped to the residues on screen
  — the intra-helical one to each of them and four either side, the span an alpha helix bonds
  across — and include backbone hydrogen bonds, which are most of what holds a helix together. Both
  are off by default. Inter-helical contacts run through the interior of the bundle, where the
  cartoon ribbon hides them; turning the receptor cartoon off shows them.
- **2D interaction diagram.** The binding site can be downloaded as a flat figure. The ligand is
  drawn as a structure — rings as rings, at one bond length — surrounded by the residues it
  contacts, each labelled with its generic position above its deposited name and distance, filled by
  the segment it sits in, and sized by how close the contact is. Every contact line is drawn as what
  it is: salt bridge, hydrogen bond, weak hydrogen bond, π-stacking, cation-π, halogen bond, metal
  coordination, hydrophobic, or an untyped close approach, with a key naming the kinds that figure
  contains. PNG on click, SVG on shift-click.
- **One figure per superposition.** With structures superposed, each gets a panel of its own, laid
  out as a grid rather than a row so six of them stay legible. Every panel shares one scale and one
  orientation, and every residue leads with its generic position, so a position can be found in the
  same place with the same label in each panel whatever its deposited numbering. Each panel names
  its receptor, its ligand and whether that ligand is an agonist, an antagonist or an inverse
  agonist. A structure whose ligand is a peptide has no small molecule to draw and is left out.

### Browsing

- Arriving at a named structure — from the search box or a link out of another panel — leaves the
  filters describing it, so the receptor family and receptor it belongs to can be read beside the
  list rather than looked up.

## 0.1.0-beta.2 — 2026-08-12

### Browsing

- **Representative structures.** Repeat depositions of one receptor–ligand context can be
  reduced to a single entry: the β2-adrenoceptor with G1I in the active state is 81 separate
  PDB entries, A2A with ZMA is 31. The filter keeps the highest-resolution structure of each
  analysis unit, 725 across the atlas against 1,358 depositions.
- **Scaffolds.** Ligands can be filtered by Bemis–Murcko scaffold — the ring systems and the
  linkers between them, side chains removed. Computed, not named: no chemotype class is
  claimed. Of 389 distinct scaffolds, the 42 shared by two or more components are offered;
  347 components have a scaffold of their own and 82 have no ring.
- **Multi-ligand structures.** Where a structure holds several ligands, the one on display can
  be changed from the title, the side panel or the viewer itself, and each ligand copy now
  highlights separately.
- Filters are carried in the address bar, so a narrowed list can be sent to someone and
  survives a language change.

### Data corrections

- **8TF5.** The deposition holds twelve copies of oleic acid, all annotated as the canonical
  7TM pocket. Only chain A residue 1210 occupies the orthosteric position; the other eleven are
  structural lipids against the membrane face. The pocket for this structure changes from 86
  receptor residues to 22 (22 at 4.5 Å, 15 at 4.0 Å), and its contact count from 102 to 22.
  Any figure quoted from the previous release for 8TF5 should be re-taken.

### Attribution

- The chemical cross-reference sources are now stated correctly. GtoPdb, ChEMBL and PubChem
  **are** queried, and the release carries per component their identifier, link, retrieval date
  and, where one was found, the source's preferred compound name — 219 ChEMBL, 300 GtoPdb and
  484 PubChem names across 580 records. Whether carrying those names triggers the share-alike
  terms of ChEMBL (CC BY-SA 3.0) and GtoPdb contents (CC BY-SA 4.0) is recorded as an open
  question in `docs/DERIVED_DATA_REVIEW_PACKET.md` §3. Component name, formula and InChIKey come
  from the PDB Chemical Component Dictionary and are unaffected.

### Scientific position

- **Contact rule sensitivity is now measured.** Recomputing every observation at 4.0 Å and
  5.0 Å, the outer angstrom contributes 23–37% of the 5 Å residue set (median 29%) across the
  seventeen cells with at least eight observations, with the canonical pocket and the
  extracellular polymer interface within a few points of each other. The rule does not behave
  differently in kind between site classes; they differ in scale and ligand size. This is not a
  validation — there is no ground truth in the measurement. See
  `docs/CONTACT_RULE_SENSITIVITY.md`.
- The reference test against the primary literature is prepared and unfilled: 18 structures over
  6 cells in `curation/contact_rule_reference.csv`. Validation scope is otherwise unchanged from
  0.1.0-beta.1.
- Still **not curated**, and still no potency, affinity or functional pathway data.

## 0.1.0-beta.1 — 2026-08-05

First public pre-release.

### Contents

- 1,358 Class A GPCR structures across 11 GPCRdb major families
- 182,169 receptor–ligand contacts at 5 Å (4.0 and 4.5 Å also computed)
- 727 aggregation units with site-class-aware prevalence
- 8 core Class A motifs over 21 generic positions
- 3D viewing for every structure, Turkish and English, light and dark themes
- 11 self-contained offline family exports, published as release assets

### Scientific position

- **Not curated.** 189 review items await human decision; none is decided.
- **Review-gated pooled summaries.** Two observations are excluded because their unresolved
  review items can change site classification; 120 items were already excluded upstream, 34 have
  no effect, 33 are warnings. A blanket per-PDB rule would have removed 48 units instead of 2.
- **Validation scope is disclosed per family and site class.** Aminergic small-molecule pockets
  are reference-tested against nine structures; other families inherited the rule without a
  family-specific test; polymer interfaces use a descriptive shell.
- **No potency, affinity or functional pathway data.**

### Licensing

- Code: PolyForm Noncommercial 1.0.0
- Project-created data and content: CC BY-NC 4.0
- Coordinates: CC0 1.0 from RCSB PDB, ~92% of the distribution by size, unaffected by the above
- Both licence texts distributed unmodified; scope stated separately

### Known limitations

WebKit/Safari untested; no manual accessibility testing; 45 covalent-ligand entities produced no
review item at all; no DOI; single maintainer with no maintenance commitment beyond that.
