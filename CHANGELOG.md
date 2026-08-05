# Changelog

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
