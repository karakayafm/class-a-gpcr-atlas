# Cross-family contact-validation disclosure

Generated from the corpus, not from a hardcoded family list:
`pipeline/phase6a/build_validation_disclosure.py`. 21 rows across
11 major families.

**Global statement (shown in the app):** Contact-rule validation varies by family and site class.
**Türkçe:** Temas kuralının doğrulanması aileye ve bölge sınıfına göre değişir.

## 1. The aminergic evidence, stated precisely

| | |
|---|---|
| Independent reference structures | **9** |
| Scope of that test | aminergic small-molecule structures checked against an independent QC table in the frozen project (DD-07) |
| Crosswalk against the frozen project | 323 observations, 323 structures |
| Contact-equivalent | 320 |
| Discrepancies | 3 |
| Crosswalk is independent ground truth? | **False** |

The crosswalk tests consistency with a previously validated implementation. It is not a second independent validation, and must not be reported as one.

**The wording used is "Reference-tested against nine aminergic small-molecule structures", not
"Validated for the Aminergic family".** The test covered small-molecule pocket contacts under the
5 Å heavy-atom definition. It did not cover all aminergic ligand forms, polymer interfaces, all
receptor states, or mutation and construct variants — and the disclosure says so.

## 2. Matrix

| Family | Site class | Ligand form | Units | Status | Ref. structures |
|---|---|---|---:|---|---:|
| Aminergic receptors | canonical_7tm_pocket | nonpolymer_residue | 212 | reference_tested_within_scope | 323 |\n| Aminergic receptors | covalent_core_site | covalent_adduct | 2 | covalent_relation_verified_contact_shell_not_independently_tested | 0 |\n| Aminergic receptors | extracellular_polymer_interface | polymer_chain | 2 | descriptive_interface_rule_not_independently_reference_tested | 0 |\n| Peptide receptors | canonical_7tm_pocket | nonpolymer_residue | 97 | transferred_without_family_specific_reference_test | 0 |\n| Peptide receptors | covalent_core_site | covalent_adduct | 1 | covalent_relation_verified_contact_shell_not_independently_tested | 0 |\n| Peptide receptors | extracellular_polymer_interface | polymer_chain | 123 | descriptive_interface_rule_not_independently_reference_tested | 0 |\n| Protein receptors | canonical_7tm_pocket | nonpolymer_residue | 14 | transferred_without_family_specific_reference_test | 0 |\n| Protein receptors | extracellular_polymer_interface | polymer_chain | 16 | descriptive_interface_rule_not_independently_reference_tested | 0 |\n| Lipid receptors | canonical_7tm_pocket | nonpolymer_residue | 106 | transferred_without_family_specific_reference_test | 0 |\n| Lipid receptors | extracellular_polymer_interface | polymer_chain | 1 | descriptive_interface_rule_not_independently_reference_tested | 0 |\n| Melatonin receptors | canonical_7tm_pocket | nonpolymer_residue | 9 | transferred_without_family_specific_reference_test | 0 |\n| Nucleotide receptors | canonical_7tm_pocket | nonpolymer_residue | 47 | transferred_without_family_specific_reference_test | 0 |\n| Nucleotide receptors | covalent_core_site | covalent_adduct | 1 | covalent_relation_verified_contact_shell_not_independently_tested | 0 |\n| Steroid receptors | canonical_7tm_pocket | nonpolymer_residue | 4 | transferred_without_family_specific_reference_test | 0 |\n| Alicarboxylic acid receptors | canonical_7tm_pocket | nonpolymer_residue | 18 | transferred_without_family_specific_reference_test | 0 |\n| Sensory receptors | canonical_7tm_pocket | nonpolymer_residue | 11 | transferred_without_family_specific_reference_test | 0 |\n| Sensory receptors | covalent_core_site | covalent_adduct | 7 | covalent_relation_verified_contact_shell_not_independently_tested | 0 |\n| Orphan receptors | canonical_7tm_pocket | nonpolymer_residue | 42 | transferred_without_family_specific_reference_test | 0 |\n| Orphan receptors | covalent_core_site | covalent_adduct | 4 | covalent_relation_verified_contact_shell_not_independently_tested | 0 |\n| Orphan receptors | extracellular_polymer_interface | polymer_chain | 9 | descriptive_interface_rule_not_independently_reference_tested | 0 |\n| Other | extracellular_polymer_interface | polymer_chain | 1 | descriptive_interface_rule_not_independently_reference_tested | 0 |

## 3. Status meanings

- **reference_tested_within_scope** — an independent reference comparison exists, for the stated
  scope only.
- **transferred_without_family_specific_reference_test** — the 5 Å definition was transferred from
  the aminergic reference-tested workflow; no family-specific independent validation exists.
- **descriptive_interface_rule_not_independently_reference_tested** — a 5 Å shell around a polymer
  ligand is a descriptive interface definition. **Not pocket validation**, and not validated as a
  universal biological interface threshold.
- **covalent_relation_verified_contact_shell_not_independently_tested** — the covalent bond is
  evidenced by deposited connectivity records; the surrounding shell is not reference-tested.
- **not_applicable** — the combination does not occur in the corpus. Never invented to fill a
  table.

## 4. Where it is shown

Landing family cards (badge), family overview (full table), pocket contacts (badge + notice),
polymer interfaces (persistent descriptive-shell warning), compare (status beside value and
denominator), Methods, and the pre-release banner. Verified in a real browser by
`tests/phase6a/review_gate_ui_tests.py`.
