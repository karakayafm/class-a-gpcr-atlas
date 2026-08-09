# Ligand chemistry build

RDKit 2025.09.6, catalogue 1.0.1, local caches only.

- components written: 580
- parsed: 579/580
- with bulk descriptors: 501/579 (omitted where the component only exists bound)
- components appearing as a pharmacological ligand: 493
- structure-ligand instances covered: 985
- payload bytes: 390716

## Parse failures

- `WJS` — raw SMILES preserved, descriptors null, no manual correction

## Facet coverage, weighted by structure-ligand instances

| Pattern | Instances |
|---|---:|
| `rs_phenyl` | 720 |
| `fg_carbonyl` | 549 |
| `fg_ether` | 348 |
| `fg_alcohol` | 340 |
| `fg_amide` | 307 |
| `fg_secondary_amine` | 284 |
| `fg_phenol` | 251 |
| `fg_tertiary_amine` | 214 |
| `fg_primary_amine` | 179 |
| `fg_carboxylic_acid` | 160 |
| `fg_catechol` | 124 |
| `rs_pyridine` | 121 |
