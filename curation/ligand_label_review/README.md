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

69 candidates remain after the three corrections. Most are not errors: retinal isomers share one component
code (11-cis inverse agonist, all-trans agonist), and rule A also catches transducer-free crystal structures
that the source calls active while GPCRdb agrees they hold antagonists. Those that disagree with GPCRdb and
are **left for a decision**:

| PDB | Receptor | Compound | Atlas | GPCRdb | Note |
|---|---|---|---|---|---|
| 8TF5 | GPR6 | oleic acid | Inverse agonist | Agonist | entry titled "pseudoapo form"; oleic acid may come from the crystallisation lipid - agonist, or apo? |
| 4BVN | β1 (turkey) | cyanopindolol | Antagonist | Agonist (partial) | inactive; GPCRdb itself gives Antagonist for the same pair in 2VT4, 2YCX, 2YCY, 5F8U |
| 9IYA | GPR55 | ONO-9710531 | Antagonist | Inverse agonist | both blockers; the combined group is unaffected |
| 7PP1 | P2Y12 | selatogrel | Antagonist | Inverse agonist | both blockers |
| 6H7O | β1 (turkey) | cyanopindolol | Agonist | Agonist (partial) | both in the agonist group |
| 5UNH | AT2 | compound 2 | Antagonist | Unknown | |

## 2. The same compound under two labels

`scan_labels.py` lists every compound that carries more than one label within a family, from the published
payloads (read only): 22 compound × family pairs after the corrections (`label_conflicts.csv`). The one that matters for the
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
