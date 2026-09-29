# Binding-site class review: canonical-pocket ligands that are not in the pocket

Prepared 2026-09-30 against release `0.1.0-beta.2` (data version
`phase4-freeze-1.0.0+enrichment-1.0.4`). Nothing in the release has been changed; this folder holds
the screen, the review list and the scripts that produced both.

## Why

A small-molecule observation's `binding_site_class` is assigned from its entity form and the
source's binding-mode annotation (`config/site_classes.json`, `canonical_7tm_pocket.decision_logic`).
Nothing checks it against where the ligand is in the coordinates. The contact-map view made the gap
visible: CXCR3's only antagonist structure, 8HNN, counted as "no contact" at 2x63 because its ligand
sits between TM5 and TM6 below the pocket while the record calls it orthosteric.

## How the screen works

`screen_site_class.py` (standard library only, like the pipeline) measures every one of the 879
ligand observations the release places in `canonical_7tm_pocket`, from the published payloads and the
deposited coordinates, in two independent ways:

- **Geometry.** The ligand's heavy-atom centroid against the orthosteric centre of its own structure
  (mean CA of the conserved pocket positions the structure resolves), split along the bundle axis
  (`axial`: + extracellular, − intracellular) and across it (`radial`), with the structure's own
  helix radius at pocket level (`bundle_radius`) for comparison. A `radial` above `bundle_radius`
  means the ligand is outside the helical bundle.
- **Contacts.** `core_overlap` is the share of the ligand's contacted positions that belong to its
  family's orthosteric core (positions contacted by at least 40% of the family's canonical-pocket
  receptors).

A ligand is flagged when its centroid is more than 12 Å from the pocket centre, or when fewer than
35% of its contacts are in the family core. Across the release the median distance is 4.4 Å
(95th percentile 10.0 Å) and the median core overlap 0.93 (5th percentile 0.46). The seven
structures the reviewer confirmed as misclassified all sit at 15.6–31.3 Å with core overlap
0.00–0.17, so the thresholds separate them with room to spare.

Three corrections were needed before the numbers could be trusted, and they are recorded because
the first versions of this screen flagged the wrong structures:

1. A ligand component can occur more than once in a file; each copy is now taken whole and the one
   nearest the contacted residues is used. Averaging over copies put centroids between them.
2. Where the asymmetric unit holds two receptor copies, the pocket centre is taken on the chain the
   contacts are on. Before, 5F8U, 4UG2 and 6AK3 appeared 30–38 Å from their own pocket.
3. Where the residue table itself lists two chains (6GPX), it is filtered to the contacts' chain.

## The list

`site_class_candidates.csv`, one row per flagged observation, sorted by status:

| status | rows | meaning |
|---|---|---|
| `confirmed_misclassified` | 9 | Reviewed 2026-09-30: not in the orthosteric pocket, target class accepted. 8HNN, 5O9H, 9K1C, 8TB7, 8IKG, 8IKH, 6U1N (LY2119620, a PAM that received the absent iperoxo's agonist label) and 8W8R/8W8S (two copies of the GPR101 ligand, both outside the bundle). |
| `not_a_ligand` | 3 | 8XXU, 8XXV and 9IYB. The "ligand" is A1D5Q, phosphatidylinositol - a membrane lipid. 8XXU/8XXV are apo; in 9IYB the record calls the lipid PGD2 (Agonist) because the annotated PGD2 is absent from the coordinates and its label reached the lipid. To be removed from the ligands and shown under a lipid layer. |
| `accepted` | 6 | Target class accepted: FFAR1 ago-allosteric ligands reaching into the pocket from the lipid-facing groove (MK-8666 in 5TZY, TAK-875 in 8EJC/8EJK) → `bitopic_or_multi_region_site`; GPR132 agonists in the vestibule (8HQM, 8HVI) → `extended_orthosteric_pocket`; 5TZY's AgoPAM → `lipid_facing_site`. |
| `accepted_keep` | 15 | Kept `canonical_7tm_pocket` by decision: the 13 MRGPR structures (their orthosteric site is the shallow TM3-TM6 pocket; in MRGPRX1 the classical region holds a PAM) and GPR52 (6LI0, 8HMP; TM1-TM2-TM7 minor pocket). |
| `keep` | 7 | Flagged by the thresholds but in the receptor's own orthosteric site: GPR34, P2Y1, A2A. |

Each row carries what the record says (`binding_mode`, `ligand_role`, `recorded_site_class`), the
measurements, the contacted segments and positions, the evidence quoted from the primary
publication's abstract where it describes the site, and the reference. `decided_by` and
`decided_on` are left for the reviewer.

## Before anything is changed

- **The mechanism exists.** Hand-curated corrections live in `pipeline/phase5/build_payloads.py`:
  `CURATED_SITE_CLASSES` (ligand entity → site class, 53 entries) and `CURATED_STRUCTURE_LIGANDS`
  (per structure: name, role, form, binding mode, site class). The corrections here go there, not
  into the published payloads.
- **Corrections do not propagate between depositions of the same ligand.** A class curated for one
  structure is not applied to the next structure carrying the same component.
  `check_curation_gaps.py` lists every such case; today there are six, and all six are in this list
  (6U1N, 8EJC, 8EJK, 5O9H, 9IYB, 5TZY). Keying the curation on component and receptor, or running the
  gap check before each release, would stop the same correction being needed twice.
- **The declared transitions are not enforced.** `config/site_classes.json` allows
  `canonical_7tm_pocket` to move only to `extended_orthosteric_pocket`,
  `bitopic_or_multi_region_site` or `unresolved`, but nothing in the pipeline reads that rule and
  the existing curation already moves ligands to `lipid_facing_site` and the allosteric pockets.
  The declaration should be brought into line with practice.
- **The site class is not the only wrong field.** Most of these records also carry
  `ligand_role: pharmacological_orthosteric_ligand`, and 6U1N carries `binding_mode: Agonist` for
  LY2119620. For 6U1N the corrected mode is GPCRdb's own: GPCRdb lists iperoxo as the agonist and
  LY2119620 as the PAM, and only LY2119620 is modelled, so the agonist label reached the wrong
  ligand. The absent iperoxo also has no `annotated_not_observed` record, which the pipeline
  produces elsewhere; the step that pairs annotations with components should be checked for other
  structures where an annotated ligand is missing from the coordinates.
- **Every aggregate that uses the canonical pocket changes.** Contact frequencies, the contact map,
  the motif query's pocket pool and the analysis-unit denominators of the affected families all
  move, so the correction belongs in a new data version.

## Applied to the pipeline (2026-09-30)

The decisions are written into `pipeline/phase5/build_payloads.py` and take effect at the next full
build, as a new data version; the published release is unchanged until then.

- `CURATED_SITE_CLASSES`: the 15 reviewed site classes; the two A1D5Q entries (8XXU, 8XXV) removed;
  5TZY's AgoPAM moved to `lipid_facing_site`.
- `CURATED_LIGAND_ROLES` (new): role and binding mode per ligand entity - allosteric for the
  ligands moved out of the pocket, bitopic for the FFAR1 ago-allosteric ligands, PAM for 6U1N.
  `CURATED_STRUCTURE_LIGANDS` could not do this: it applies to every observation of a structure.
- `CURATED_APO_STRUCTURES` / `CURATED_NON_LIGAND_STRUCTURES`: 8XXU, 8XXV, 9IYB and the six opsin
  structures whose only annotated ligand is a detergent.
- `CURATED_STRUCTURE_NOTES` (new): what those structures carry, in English and Turkish, published as
  `curation_notes` on the structure record (`schemas/phase5/structure_index.schema.json`) and shown on
  the structure page.
- `config/site_classes.json`: the canonical pocket's declared transitions widened to the classes the
  curation already uses.

## Re-running

```bash
python3 curation/site_class_review/screen_site_class.py    # ~25 s, writes site_class_screen.csv
python3 curation/site_class_review/build_candidates.py     # writes site_class_candidates.csv
python3 curation/site_class_review/check_curation_gaps.py  # same ligand, curated in one structure only
```
