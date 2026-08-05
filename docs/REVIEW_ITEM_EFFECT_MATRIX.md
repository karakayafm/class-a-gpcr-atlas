# Review item effect matrix

One row per open review item that is excluded or warned. Items with `already_excluded` or
`no_effect` are in `data/release_overlays/rc6/review_impact.jsonl`; there are
120 and 34 of them respectively.

## Rule usage

| Rule | Records |
|---|---:|
| RG-01 | 51 |\n| RG-02 | 46 |\n| RG-03 | 23 |\n| RG-04 | 12 |\n| RG-05 | 22 |\n| RG-06 | 18 |\n| RG-07 | 11 |\n| RG-08 | 6 |\n| RG-09/10 | 151 |\n| RG-11 | 392 |\n| RG-12 | 3 |\n| RG-13 | 2 |

## Excluded and warned items

| Review item | Issue type | PDB | Rule | Scope | Effect |
|---|---|---|---|---|---|
| CHAIN:4QKX:EI:poly:2 | polymer_chain_role | 4QKX | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:5CXV:EI:poly:2 | polymer_chain_role | 5CXV | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:6NWE:EI:poly:2 | polymer_chain_role | 6NWE | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:6PH7:EI:poly:2 | polymer_chain_role | 6PH7 | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:7B6W:EI:poly:1 | polymer_chain_role | 7B6W | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:7X1T:EI:poly:6 | polymer_chain_role | 7X1T | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:7XJL:EI:poly:1 | polymer_chain_role | 7XJL | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:7XMT:EI:poly:3 | polymer_chain_role | 7XMT | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:8IRU:EI:poly:5 | polymer_chain_role | 8IRU | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:8J24:EI:poly:5 | polymer_chain_role | 8J24 | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:8J6L:EI:poly:4 | polymer_chain_role | 8J6L | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:8K2X:EI:poly:6 | polymer_chain_role | 8K2X | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:8K4P:EI:poly:2 | polymer_chain_role | 8K4P | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:8QJ2:EI:poly:6 | polymer_chain_role | 8QJ2 | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:8WRZ:EI:poly:4 | polymer_chain_role | 8WRZ | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:8YNS:EI:poly:3 | polymer_chain_role | 8YNS | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:8YNT:EI:poly:3 | polymer_chain_role | 8YNT | RG-06 | no_current_aggregate_effect | warning_only |\n| CHAIN:9D3E:EI:poly:1 | polymer_chain_role | 9D3E | RG-06 | no_current_aggregate_effect | warning_only |\n| CONFLICT:4ZWJ:conflict:transducer | source_conflict:transducer_presence_disagreement | 4ZWJ | RG-07 | metadata_only | warning_only |\n| CONFLICT:5DGY:conflict:transducer | source_conflict:transducer_presence_disagreement | 5DGY | RG-07 | metadata_only | warning_only |\n| CONFLICT:5W0P:conflict:transducer | source_conflict:transducer_presence_disagreement | 5W0P | RG-07 | metadata_only | warning_only |\n| CONFLICT:6E67:conflict:transducer | source_conflict:transducer_presence_disagreement | 6E67 | RG-07 | metadata_only | warning_only |\n| CONFLICT:6NWE:conflict:transducer | source_conflict:transducer_presence_disagreement | 6NWE | RG-07 | metadata_only | warning_only |\n| CONFLICT:6PH7:conflict:transducer | source_conflict:transducer_presence_disagreement | 6PH7 | RG-07 | metadata_only | warning_only |\n| CONFLICT:7XOX:conflict:transducer | source_conflict:transducer_presence_disagreement | 7XOX | RG-07 | metadata_only | warning_only |\n| CONFLICT:7YOO:conflict:transducer | source_conflict:transducer_presence_disagreement | 7YOO | RG-07 | metadata_only | warning_only |\n| CONFLICT:8GG7:conflict:transducer | source_conflict:transducer_presence_disagreement | 8GG7 | RG-07 | metadata_only | warning_only |\n| CONFLICT:8HNL:conflict:transducer | source_conflict:transducer_presence_disagreement | 8HNL | RG-07 | metadata_only | warning_only |\n| CONFLICT:8ZFJ:conflict:transducer | source_conflict:transducer_presence_disagreement | 8ZFJ | RG-07 | metadata_only | warning_only |\n| TETHER:3VW7 | tethered_ligand_candidate | 3VW7 | RG-08 | observation | exclude_from_public_beta_pooled_analysis |\n| TETHER:5NDD | tethered_ligand_candidate | 5NDD | RG-08 | observation | exclude_from_public_beta_pooled_analysis |\n| TETHER:5NDZ | tethered_ligand_candidate | 5NDZ | RG-08 | no_current_aggregate_effect | warning_only |\n| TETHER:5NJ6 | tethered_ligand_candidate | 5NJ6 | RG-08 | no_current_aggregate_effect | warning_only |\n| TETHER:8XOR | tethered_ligand_candidate | 8XOR | RG-08 | no_current_aggregate_effect | warning_only |\n| TETHER:8XOS | tethered_ligand_candidate | 8XOS | RG-08 | no_current_aggregate_effect | warning_only |

## The two exclusions, in full

Both are PAR (protease-activated) receptors, whose endogenous ligand is a tethered receptor
segment. The tethered-ligand question is `unresolved_human_review_required` and the co-bound
small molecule is classified `canonical_7tm_pocket`. Whether that classification is right cannot
be settled while the receptor's own endogenous ligand is undetermined, so presenting the value as
a settled pocket contact would assert the thing under review.

Each removed exactly one observation, and each of those observations was the only one in its
aggregation unit — hence two units removed rather than two units modified.
