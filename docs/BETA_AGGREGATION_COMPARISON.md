# Beta aggregation versus original Phase 4

The overlay never overwrites a Phase 4 value. Every beta row carries `source_phase4_metric`, so
the two are comparable row by row and the original remains the citable frozen number.

| | |
|---|---:|
| Beta prevalence rows | 181672 |
| Rows whose 5 Å fraction differs from Phase 4 | 0 |
| Phase 4 prevalence rows (unchanged on disk) | 182169 |
| Phase 4 aggregation units (unchanged on disk) | 727 |

At unit × position level the fractions are largely identical, because the gate removed whole
single-observation units rather than trimming slots inside multi-observation units. The visible
difference is at **family × site class** level, where the affected units no longer contribute to
the mean — which is exactly where a pooled summary is read.

## Thresholds and weightings

All three thresholds (4.0, 4.5, 5.0 Å) and all five weightings are precomputed in the overlay:
unit-weighted continuous, unit-weighted any-contact, structure-weighted, receptor-weighted and
ligand-weighted.

Receptor- and ligand-weighted schemes are genuine re-weightings of the frozen unit contributions
(average within receptor or ligand group, then across groups). This is worth noting because the
**Phase 5 application could not express them** — it silently fell back to the unit-weighted 5 Å
value for both. The overlay computes them properly, so those two menu options now show what they
claim to show.

Nothing was estimated. No combination required the
`not_estimable_from_frozen_contributions` status.

## Default in the interface

The default pooled value is the review-gated beta value. The original Phase 4 aggregate is
available only in a collapsed panel labelled "Original Phase 4 aggregate before public-beta
review gating" / "Public-beta inceleme filtresi uygulanmadan önceki özgün Phase 4 agregasyonu",
and is never used in the main table ranking or the default comparison. Verified in a real browser.
