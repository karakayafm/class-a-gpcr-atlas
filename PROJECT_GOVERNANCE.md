# Project governance

## Scope

A derived analysis resource built on GPCRdb and the RCSB PDB. Not a primary database, and not a
replacement for either.

## Fixed commitments

These do not change without a major version and a changelog entry naming the affected hashes:

1. **Contact definition** — minimum heavy-atom distance ≤ 5 Å, hydrogens excluded, deterministic
   altloc policy.
2. **Site-class separation** — a small-molecule pocket and a receptor–polymer interface never
   share a prevalence denominator.
3. **Adjudication is not curation** — automated adjudication and human curation occupy disjoint
   fields. No automated process writes a human-curation field.
4. **Sources are not silently reconciled** — where GPCRdb and RCSB disagree, both records are
   kept and flagged.
5. **Nothing is invented** — no DOI, ORCID, date, author, institution, version string or licence
   is recorded unless it exists.

## Corrections

Versioned, never silent. A correction that changes a published number bumps the version and names
the affected hashes. If a systematic error is found after release, the affected version is marked
superseded in place with the error stated; it is not quietly withdrawn.

## Curation status

**The scientific claims have not been reviewed by a human curator.** 189 review items are queued;
none is decided. The atlas presents automated evidence adjudication, labelled as such, with each
item's effect on pooled metrics shown in the evidence view.

Before a stable release, a stratified 55-record gold subset (34 of them double-reviewed, 89 review
events) is planned so that an agreement rate can be measured. **No performance figure may be
computed or published until those records carry human decisions.**

## Release authority

Muhammed Fatih Karakaya, copyright holder.

## Licensing

Code under PolyForm Noncommercial 1.0.0; project-created data and content under CC BY-NC 4.0;
source-derived material under its source licences. Source-available for noncommercial use — **not
open source**. Commercial use requires separate written permission.

## Maintenance

**One maintainer, and no maintenance commitment beyond that.** This is stated rather than omitted:
a released resource whose maintenance is uncertain is a fact users are entitled to know.

## What this project will not claim

- No DOI until one is actually minted
- No ORCID unless supplied by its holder
- No institutional endorsement until an institution records one
- That automated adjudication is human curation
- Any accuracy figure computed against unreviewed data
- Validation for a family or site class where it has not been performed
- "Open source", "fully curated", or "independently validated across Class A"
