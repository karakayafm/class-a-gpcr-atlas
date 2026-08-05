# Validation language audit

Searched the application, README, drafts, reports and overlay payloads for claim language:
*validated, validation, verified, doğrulandı, geçerli, fully curated, benchmarked, curated,
peer-reviewed, expert-reviewed, WCAG compliant*.

| | |
|---|---:|
| Files scanned | 69 |
| Candidate claim phrases | 3 |
| **Unqualified claims remaining** | **0** |

No unqualified validation claim is asserted anywhere in the application or the release documents. Every occurrence is either scoped (technical validation, integrity verification, reference testing) or is an explicit prohibition.

## The distinction the audit preserves

| Permitted, because it is true and scoped | Not permitted |
|---|---|
| "Technically validated release candidate" | "Validated Class A contact atlas" |
| "Integrity verification" (hashes, checksums) | "Verified data" |
| "Reference-tested against nine aminergic small-molecule structures" | "Validated for the Aminergic family" |
| "Descriptive 5 Å interface shell" | "Validated interface threshold" |
| "Covalent linkage evidenced by deposited connectivity" | "Covalent contacts validated" |
| "67 automated accessibility checks pass" | "WCAG AA compliant" |
| "Human curation: not performed" | "Curated database" |

## Findings

The two phrases the scan flagged as unqualified were both inside the **"wordings that must NOT be
used"** table in the pre-release wording draft — the prohibition itself, not a claim. They are
recorded rather than silently dropped, because a scan that quietly reclassifies its own hits is
not an audit.

The one earlier risk was the proposed project name *"Class A GPCR Structural Pharmacology
Atlas"*, which would have asserted pharmacology content the atlas does not contain
(`functional_pathway_evidence` is null for all 1358 structures; GtoPdb, ChEMBL and PubChem are
never called). The adopted name is **Class A GPCR Structure–Ligand Contact and Interface Atlas**,
and a release test asserts the shipped title makes no pharmacology claim.
