# Contributing

Corrections are genuinely wanted. This is a pre-release beta whose scientific claims have **not**
been reviewed by a human curator, and the fastest route to finding errors is people who know the
structures reporting what looks wrong.

## Before anything else

Please read the limitation the whole project turns on:

> Research pre-release: This atlas is a technically validated beta covering Class A GPCR structures, ligand–receptor contacts, polymer ligand interfaces and core structural motifs. It provides no functional pathway activity data and no potency data of its own; reported affinities are relayed for 23 of its 578 components, from the one BindingDB subset whose licence permits redistribution. Some evidence records still require human review. Open records that affect identity or aggregation eligibility have been removed from public-beta pooled analyses by an issue-specific review gate. Reference testing of the contact rule and independent human validation vary by family and site class.

## What is most useful

**1. Scientific data corrections.** If a contact, a ligand assignment, a site classification or a
receptor mapping looks wrong, say so. Use the *Scientific data correction* issue template and
include the PDB identifier, the disputed field, the proposed correction and a source — a DOI or a
database record. Every value in the atlas links back to its primary source so a claim can be
checked against the deposition.

**2. Review-queue items.** 189 records are queued for human decision and none has been decided.
If you have the expertise to settle one, that is the most valuable contribution available.
See `docs/REVIEW_ITEM_EFFECT_MATRIX.md`.

**3. Software bugs and viewer problems.** Especially on hardware this project could not test:
AMD and Intel GPUs, Apple Silicon, WebKit/Safari, and mobile devices. Only NVIDIA hardware in
Chromium and Firefox has been validated.

**4. Accessibility.** 67 automated checks pass, but **no manual testing with assistive technology
has been done**. Reports from screen-reader users would be acted on.

## What will not be accepted

- Changes that alter a frozen scientific definition without a version bump and a changelog entry
  naming the affected hashes. The 5 Å contact definition, the site-class separation and the
  adjudication/curation boundary are fixed commitments.
- Anything that records an automated assessment as human curation. The two occupy disjoint fields
  and always will.
- Claims the evidence does not support — "validated", "curated", "open source" — anywhere in the
  interface or documentation.

## Code contributions

The code is licensed **PolyForm Noncommercial 1.0.0**, which is *not* an OSI-approved open source
licence. Please make sure that suits you before spending time on a patch. By contributing you
confirm you have the right to contribute the work under that licence.

The pipeline is **Python ≥ 3.10, standard library only**. Please keep it that way — no third-party
dependency, no build step.

## Style

Match the surrounding code. Comments explain *why*, not *what*. If a check can be computed rather
than asserted, compute it.

## Contact

edu.mfatih@gmail.com — or open an issue.
