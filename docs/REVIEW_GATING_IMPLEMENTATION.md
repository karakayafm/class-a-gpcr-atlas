# Review gating — implementation

Turns the policy sentence *"open items visible and excluded from pooled analyses where required"*
into behaviour, without widening it to *"all open items are excluded"*.

## 1. Architecture

The overlay is a **separate release layer**: `data/release_overlays/rc6/`. It reads frozen Phase 3
and Phase 4 artefacts and writes only into its own tree. No Phase 4 aggregate, Phase 5 payload or
earlier release candidate is modified — verified by test, and by `rc_bundles_sha` and
`phase5_global_manifest_sha` being identical across rc1→rc6.

Original and beta values are separated by **source and version**: every beta prevalence row
carries `source_phase4_metric` alongside its own value and `overlay_rule_version`.

## 2. Contacts are not recomputed

Contact geometry, generic numbering, motif geometry, ligand entity assignment and site-class
source decisions are untouched. The overlay applies an **eligibility mask** over the frozen
per-observation contact rows and re-summarises. That is the only honest way to change a
denominator: the numbers that survive are the same measurements, counted over a different set.

## 3. Nothing is recomputed in the browser

All three thresholds × five weightings are precomputed at build time. The application reads a
field. This is what makes a displayed value traceable to a build hash.

## 4. The decision procedure

Twelve rules in `governance/REVIEW_GATING_POLICY.json`, each with a structural test, an effect
for true and for false, and a written reason. Every rule tests **what the item reaches**, never
its issue name alone:

- Does the ligand entity appear as the ligand of a pooled observation?
- Does the PDB contribute any observation at all?
- Did Phase 4 already exclude this entity or receptor instance?
- Does the unit's structural state actually depend on the disputed transducer?

## 5. Granularity

Narrowest first: observation → structure slot → aggregation unit → family summary. An unresolved
allosteric ligand does not remove a reliable orthosteric ligand in the same deposition. A blocked
slot inside a multi-structure unit removes the slot and the unit metric is re-derived; the unit
is dropped only when the eligible denominator reaches zero, and then it reports **NA, not 0%**.

## 6. Result

| | |
|---|---:|
| Open items | 189 |
| already_excluded | 120 |
| no_effect | 34 |
| warning_only | 33 |
| excluded | 2 |
| Observations blocked | 2 |
| Units removed | 2 |
| Units a blanket PDB rule would have touched | 48 |

## 7. A correction made during implementation

The first version of rule RG-07 decided whether the structural state depends on transducer
presence by searching the frozen decision rule for the word "transducer". That rule reads:
*"mapped from the GPCRdb state annotation only; a transducer-bound structure is NOT relabelled
active on that basis"* — the word appears precisely to say the transducer is **not** used. The
substring test inverted the meaning and over-excluded four sound observations, removing one unit
and modifying two.

Replaced with a test on the uniformity of the documented rule, which fails safe: if the rule ever
changes or stops being uniform, transducer disagreements become blockers again. This is recorded
because over-exclusion is as much a defect as under-exclusion, and it is the harder one to notice
— removed data leaves no error message.
