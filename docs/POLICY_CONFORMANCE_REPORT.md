# Policy conformance report

Does the implementation match the policy that was actually committed to — which is narrower than
"exclude everything under review"?

| Suite | Checks | Failed |
|---|---:|---:|
| Policy conformance (`validate_policy_conformance.py`) | 43 | 0 |
| Review-gate UI, real browser (`review_gate_ui_tests.py`) | 48 | 0 |

## What is tested

**Completeness (A).** All 737 canonical records and all
189 open items accounted for; no duplicate effects; every effect
carries a rule id and a reason; every effect and scope value is in the closed vocabulary; no
unmatched rule.

**Granularity (B).** An observation-scoped exclusion does not block sibling observations in the
same PDB. A partial block never deletes a whole unit. A unit is removed only when its eligible
denominator reaches zero. And the forbidden blanket rule is provably not applied: it would have
touched 48 units where the gate removes
2.

**Issue semantics (C).** Metadata-only items are never excluded. `annotated_not_observed` is
`already_excluded`. Apo without a contact row is `already_excluded`. Unvalidated generic mapping
is `already_excluded`. Unresolved receptor and ligand identity block only where they reach data.
Non-impacting transducer disagreement is warning-or-no-effect.

**Aggregates (D).** The beta metric uses the gated denominator; a zero denominator yields NA; all
three thresholds and all five weightings are precomputed; the original Phase 4 metric is carried
in every row; every blocked slot has review-item provenance; the Phase 4 tables are unchanged
(182169 rows, 727 units); no silent unit loss.

**Validation disclosure (E).** All 11 families represented; only aminergic marked
reference-tested; the crosswalk is explicitly *not* claimed as independent ground truth; polymer
interfaces never labelled pocket-validated; covalent bond verification kept distinct from shell
validation; TR and EN present in every row; no invented family/site-class row.

**Wording (F).** The policy wording is "where required" and is never widened to "all open items
are excluded"; the constraint field forbidding the wider claim is present.

**Interface (UI).** In a real browser: the default pooled value is the review-gated one and
matches the overlay precisely in the family where the gate actually removed units; the original
Phase 4 panel exists, is collapsed and is explicitly labelled; the gate panel shows both
denominators, excluded and warning-only slot counts, removed and modified units and the affecting
item count; validation badges appear on all 11 family cards; the polymer-interface descriptive
shell warning is persistent; compare shows both families' scope; evidence shows per-item
aggregation effect and reason.

**Result: 91 checks, 0 failed.**
