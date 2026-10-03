# Ligand labels: corrections and labels that change between depositions

Prepared 2026-10-02. The contact map compares ligands by the pharmacological label (binding mode) each
deposition records. Two things about those labels came out of the pocket-occupancy experiment and the
reviews of it.

## 1. A label that contradicts its structure: 9IJD

9IJD is the carazolol-activated human β3 receptor in its active, Gs-coupled state. The atlas recorded
carazolol there as an **inverse agonist**. The entry's title ("Carazolol-activated human beta3 adrenergic
receptor"), its primary citation ("Molecular Mechanism of the β3AR Agonist Activity of a β-Blocker",
ChemPlusChem 2024, doi:10.1002/cplu.202400288) and GPCRdb ((S)-carazolol, Agonist) all describe it as an
agonist. Decided 2026-10-02: corrected to **Agonist**.

- Permanent: `pipeline/phase5/build_payloads.py` - `CURATED_LIGAND_ROLES["9IJD:LE:np:CAU"]` and a
  bilingual `CURATED_STRUCTURE_NOTES["9IJD"]`. Takes effect at the next full build.
- Until then: `site/data/web/overlay/curation_pending.json` lists the correction, and the site's loader
  (`app/js/data/loader.js`, `applyPending`) applies it to every structure list it loads - family lists,
  panels, per-class ligand lists (the observation leaves the inverse-agonist list) and the viewer - and
  adds the note to the structure page. Precomputed aggregates (motif and pocket search frequencies,
  panel summaries, the agonist class list) still count the old label until the build.

In the contact map, with agonists against inverse agonists in the aminergic family, the inverse-agonist
group goes from 8 units / 13 structures to 7 / 12, and 5x39 at ≤ 4 Å from −46 to −54 points: the β3
structure did not touch 5x39 and was diluting the group.

### Two more found by the review rules (decided 2026-10-03)

- **8DCS** (turkey β1, cyanopindolol, active with Gs, a representative structure): recorded as Antagonist.
  The entry ("cyanopindolol-bound β1-adrenergic receptor in complex with heterotrimeric Gs", keywords
  "partial agonist"; "Structures of β1-adrenergic receptor in complex with Gs and ligands of different
  efficacies", 2022) and GPCRdb (Agonist (partial)) disagree. Corrected to **Agonist (partial)**.
- **7C61** (5-HT1B, ergotamine): recorded as Antagonist; GPCRdb lists Agonist, and the atlas records the
  same compound at the same receptor (4IAR) as Agonist. Corrected to **Agonist**.

Both are in `CURATED_LIGAND_ROLES` / `CURATED_STRUCTURE_NOTES` and in the pending overlay, like 9IJD.

### Review rules and the candidate list

`scan_labels.py` writes `label_review_candidates.csv` from two rules, run over every family, and puts
GPCRdb's own label for each candidate beside the atlas's (read-only lookups, cached in
`data/cache/gpcrdb_structures/`):

- **A** - a blocker label (Antagonist or Inverse agonist) on a structure that is active or carries a
  transducer;
- **B** - the same compound at the same receptor recorded as an agonist in one entry and a blocker in
  another.

66 candidates remain after the six corrections. Most are not errors: retinal isomers share one component
code (11-cis inverse agonist, all-trans agonist), and rule A also catches transducer-free crystal structures
that the source calls active while GPCRdb agrees they hold antagonists. A GPCRdb entry can also list a
second "ligand" that is not the drug - in 6RZ4/6RZ5 the NAM label belongs to the bound Na+, not to
pranlukast or zafirlukast, and the two sources agree on the drug itself.

### Three more decided 2026-10-03, after a second review

- **8TF5** (GPR6, oleic acid): recorded as Inverse agonist. The entry is the "pseudoapo form" - the authors
  add no ligand - and the primary publication reports "a strong density in the orthosteric pocket of GPR6
  corresponding to a lipid-like endogenous ligand", modelled as oleic acid. GPCRdb gives Agonist, and the
  atlas already records the same situation at GPR3 (8U8F, palmitic acid) as Agonist. Corrected to
  **Agonist**. The lipid's identity is tentative and oleic acid is not a characterised GPR6 agonist, so the
  note says it should not be read as a pharmacological ligand in the ligand-chemistry and affinity panels.
  *Open, as separate work:* `ligand_role` is `pharmacological_orthosteric_ligand` for both 8TF5 and 8U8F,
  which that caveat contradicts. A role value for a lipid of uncertain identity and origin should be added
  and given to both together - not `copurified_lipid`, which would settle a question the sources leave
  open: the review could not separate a lipid carried through purification from one picked up during
  crystallisation.
  `structural_lipid` is not the right value - both sets of authors give the density an activating role, so
  it would contradict the Agonist label beside it and a role-filtered panel would undo the correction.
- **6H7O** (turkey beta1, cyanopindolol, active): recorded as Agonist; GPCRdb gives Agonist (partial), as for
  the same compound at the same receptor in 8DCS. Refined to **Agonist (partial)**. Both entries stay in the
  agonist group, so no group changes.
- **7PP1** (P2Y12, selatogrel): recorded as Antagonist. The entry is titled "in complex with the inverse
  agonist selatogrel", the primary publication says selatogrel stabilises the inactive, basal state and
  abolishes the receptor's constitutive activity, and GPCRdb gives Inverse agonist. Corrected to **Inverse
  agonist**. Both labels are blockers, so the combined group is unchanged.

The structural state is computed from the geometry, so it can differ from the authors' functional
description: 7PP1 reads active here and in GPCRdb, while the authors describe an inactive basal state. The
computed value is kept and the difference recorded as a note - this is a definition difference, not an error.

**Left as recorded, with a note (5UNF, 5UNG, 5UNH - AT2):** the authors give these compounds no functional
label, and although the receptor is in an active-like conformation, helix VIII prevents G protein and
beta-arrestin recruitment, "in agreement with the lack of signalling responses in standard cellular assays".
Nothing contradicts the source's Antagonist label, so it stands; GPCRdb gives Antagonist for 5UNF/5UNG and
leaves 5UNH unannotated, which is an absent annotation rather than evidence against it. The note on all
three records why rule A flags them. It is a note only, with no label change, so it arrives at the next
build rather than through the overlay.

Those that still **disagree with GPCRdb and are left for a decision**:

| PDB | Receptor | Compound | Atlas | GPCRdb | Decision |
|---|---|---|---|---|---|
| 4BVN | beta1 (turkey) | cyanopindolol | Antagonist | Agonist (partial) | **Keep Antagonist.** 4BVN is inactive and is the representative structure, and GPCRdb itself gives Antagonist for the same pair in 2VT4, 2YCX, 2YCY and 5F8U - it disagrees with itself here. |
| 9IYA | GPR55 | ONO-9710531 | Antagonist | Inverse agonist | **Waiting on the primary publication.** Both labels are blockers, so the combined group is unaffected either way. |
| 5UNH | AT2 | compound 2 | Antagonist | Unknown | **Keep Antagonist**, with the AT2 note above. |

### What the six corrections do to the aminergic contact map

Counted from the published payloads with the corrections applied, over exactly what the contact map
compares - contact-eligible observations **in the canonical 7TM pocket**, on representative analysis
units - in the aminergic family:

| Group | Before | After |
|---|---|---|
| Agonist (Agonist + partial) | 34 units / 157 structures | 34 / 159 |
| Blocker (Antagonist + inverse agonist) | 24 / 55 | 23 / 53 |
| Antagonist alone | 20 / 42 | 20 / 41 |
| Inverse agonist alone | 8 / 13 | 7 / 12 |
| Units with both sides (agonist × blocker) | 19 | **18** |
| Units with both sides (agonist × inverse agonist) | 7 | 6 |

The `binding_site_class` condition is part of the count, not a detail: without it three representative
structures that carry a group label outside the canonical pocket are counted too - 3PDS and 4QKX
(agonist, `covalent_core_site`) and 8HN1 (antagonist, `extracellular_polymer_interface`) - which inflates
the agonist and antagonist rows by two and one. The inverse-agonist row is identical either way, because
no inverse agonist in this family sits outside the canonical pocket, so matching a filter on that row
alone does not prove it is right.

The inverse-agonist row is the 9IJD change described above; the rest come from 8DCS and 7C61 moving from
the blocker side to the agonist side. 6H7O, 8TF5 and 7PP1 move nothing here: 6H7O stays in the agonist
group, 7PP1's two labels are both blockers, and 8TF5 is in another family.

These counts are produced from the data, not carried over by hand. Regenerate them rather than editing
them whenever a label decision changes, and note that the precomputed aggregates on the site only follow
at the next full build - until then the overlay carries the labels but not these totals.

## 2. The same compound under two labels

`scan_labels.py` lists every compound that carries more than one label within a family, from the published
payloads (read only): 21 compound × family pairs after the corrections (`label_conflicts.csv`). The one that matters for the
contact map is Antagonist against Inverse agonist, which separates two groups a reader can choose: in the
aminergic family seven compounds carry both - carazolol, carvedilol (CHEMBL3799125), methiothepin /
metitepine (CHEMBL428892), ICI 118551, risperidone, timolol and tiotropium; timolol and ICI 118551 carry both even at the same receptor (β2).

These are left as recorded: they come from the sources, and choosing one label per compound is a
pharmacological decision, not a correction. The contact map instead says so whenever one of the two
labels is chosen on its own, names the compounds, and points to the combined "Antagonist + inverse agonist"
group, which is the default.

## Re-running

```bash
python3 curation/ligand_label_review/scan_labels.py    # writes label_conflicts.csv and overlay/curation_pending.json
```

Decisions go into `CORRECTIONS` in the script and, permanently, into `build_payloads.py`. After a build that
carries them, the entry can be removed from `CORRECTIONS`; the loader only acts on observations whose label
still equals the `from` value, so a stale entry does nothing.
