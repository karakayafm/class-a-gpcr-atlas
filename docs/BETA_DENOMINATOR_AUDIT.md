# Beta denominator audit

Every public-beta prevalence row carries both denominators, so the effect of the gate on any
single number is checkable without re-running anything.

| | |
|---|---:|
| Beta prevalence rows | 181672 |
| Rows whose denominator changed | 0 |
| Rows with a zero eligible denominator (reported NA) | 0 |
| Rows reported as 0% because of the gate | **0** |

**A zero denominator yields NA, never 0%.** That distinction is enforced by
`validate_policy_conformance.py` (`zero_denominator_yields_NA_not_zero_percent`), because a
0% reads as "measured and absent" when the truth is "nothing left to measure".

## Per family

| Family | Units | Unchanged | Modified | Removed | Observations | Eligible | Blocked | Warned |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 001_001 | 216 | 216 | 0 | 0 | 382 | 382 | 0 | 0 |
| 001_002 | 221 | 219 | 0 | 2 | 325 | 323 | 2 | 0 |
| 001_003 | 30 | 30 | 0 | 0 | 46 | 46 | 0 | 0 |
| 001_004 | 107 | 107 | 0 | 0 | 148 | 148 | 0 | 0 |
| 001_005 | 9 | 9 | 0 | 0 | 13 | 13 | 0 | 0 |
| 001_006 | 48 | 48 | 0 | 0 | 99 | 99 | 0 | 0 |
| 001_007 | 4 | 4 | 0 | 0 | 5 | 5 | 0 | 0 |
| 001_008 | 18 | 18 | 0 | 0 | 43 | 43 | 0 | 0 |
| 001_009 | 18 | 18 | 0 | 0 | 52 | 52 | 0 | 0 |
| 001_010 | 55 | 55 | 0 | 0 | 78 | 78 | 0 | 0 |
| 001_011 | 1 | 1 | 0 | 0 | 5 | 5 | 0 | 0 |

## Interpretation

Only the Peptide family (001_002) lost units — two, both single-observation units whose sole
observation was blocked by the tethered-ligand rule. Every other family is unchanged, which is
the expected result once the gate is applied per issue rather than per structure: the pipeline
had already excluded the identity-blocking cases upstream.

Where a unit keeps some eligible slots, its metric is re-derived from those slots rather than
the unit being deleted. No such case arises in this build (0 modified units),
but the behaviour is implemented and tested
(`partial_block_does_not_delete_whole_unit`, `unit_removed_only_when_denominator_zero`).
