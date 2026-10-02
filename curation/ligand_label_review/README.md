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

## 2. The same compound under two labels

`scan_labels.py` lists every compound that carries more than one label within a family, from the published
payloads (read only): 23 compound × family pairs (`label_conflicts.csv`). The one that matters for the
contact map is Antagonist against Inverse agonist, which separates two groups a reader can choose: in the
aminergic family seven compounds carry both - carazolol, CHEMBL3799125, CHEMBL428892, ICI 118551,
risperidone, timolol and tiotropium; timolol and ICI 118551 carry both even at the same receptor (β2).

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
