# Review gating — counts

All figures recomputed from the frozen artefacts by `pipeline/phase6a/build_review_gate_overlay.py`.
The 48/63 figures reported earlier came from a **coarse PDB-level join** and are kept below only
to show what the forbidden blanket rule would have removed.

## 1. Objects, kept distinct

| Object | Count |
|---|---:|
| Canonical review records | 737 |
| Human-review-required items | 189 |
| Distinct PDB IDs among those items | 156 |
| Observations (structure–ligand) in aggregation units | 1196 |
| Aggregation units | 727 |
| Aggregate prevalence rows (Phase 4) | 182169 |

A review item, a PDB, an observation, a structure slot, a unit and a prevalence row are six
different things. One item affecting several rows is **one** scientific problem, and the impact
table carries exactly one record per review record — verified by a duplicate check.

## 2. Effect of the 189 open items

| Aggregation effect | Items |
|---|---:|
| already_excluded | 120 |
| no_effect | 34 |
| warning_only | 33 |
| **exclude_from_public_beta_pooled_analysis** | **2** |
| Total | 189 |

## 3. What the gate actually removed

| | |
|---|---:|
| Observations blocked | 2 |
| Observations warning-only | 0 |
| Units modified (slots removed, unit re-derived) | 0 |
| Units removed (eligible denominator reached zero) | 2 |
| Units unchanged | 725 |

## 4. The forbidden rule, for comparison

| | |
|---|---:|
| Units a coarse PDB-level join would have touched | 48 |
| Observations it would have touched | 63 |
| Units the issue-specific gate actually removes | 2 |

The blanket rule would have removed **48** units —
24× more than the
evidence supports — because it treats "an open item shares this PDB" as "this unit is unreliable".
