# Read-only policy

The existing aminergic application is a **frozen reference implementation**. This document
states what is protected, how the protection is verified, and what the pipeline is allowed to
do instead.

## 1. What is frozen

Everything in the parent directory `pymol_views/` that existed when this project began, in
particular:

- `index.html` (the GitHub Pages entry point)
- every `pathway_pocket_viewer_*` file and template
- `build_pathway_pocket_html.py`, `build_pathway_pocket_data_v15.py`, and all build shell
  scripts
- every JSON data artefact (`pathway_pocket_data_v15.json`,
  `pathway_pocket_pockets_v15.json`, `structure_references.json`, `references_payload.json`,
  `ligand_xrefs.json`, `baseline_stats.json`)
- every documentation file (`README.md`, `CITATION.cff`, `AUTHORS.md`, `DATA_PROVENANCE.md`,
  `DATA_LICENSE.md`, `THIRD_PARTY_NOTICES.md`, `CHANGELOG.md`, `PROJECT_GOVERNANCE.md`,
  `LICENSE_DECISION_REQUIRED.md`, the per-version viewer READMEs)
- every checksum and hash file
- everything under `../aminergic_diff_eq/`
- the discovery reports in `class_a_expansion_workspace/00_discovery/`

**350 files** are covered by the baseline manifest `_checksums_before.sha256`, whose own SHA-256 is
`c070673f5a02b5ba174bfc203849229f732e5d045b7e3002c401b73d0debff71`.

## 2. What "frozen" means

No modification, no deletion, no rename, no reformatting, no "harmless" fix. This includes
files with known defects: `reference_enrichment_report.md` is truncated at 20 lines (logged
during discovery as risk R24) and is **left exactly as it is**. Repairing it would be a change
to a frozen artefact, and the repair is not this project's to make.

The frozen project is also not a runtime dependency: this pipeline does not read its data files,
import its modules, or call its scripts. It is a reference to be read by people, not by code.

## 3. How it is verified

`tests/run_tests.py`, group `read_only`, re-hashes every file in the baseline manifest with
SHA-256 and compares. It reports separately on:

- **changed** files — a byte differs
- **missing** files — a path in the baseline no longer exists

Both are hard failures. The check runs on every test invocation, not only at phase boundaries,
so a violation is caught by the next test run rather than at the end of the phase.

Because the parent directory is not a Git repository, these manifests are the only integrity
record. That is why the baseline is taken before any work and compared after.

## 4. Flags never delete

The same principle applies inside this project's own data. `config/qc_flags.json` states:

> A flag never removes a record from the raw universe. Production inclusion is a later,
> explicit decision.

`schemas/qc_flag.schema.json` pins `excludes_from_universe` so that no flag definition can
declare itself exclusionary, and the test suite verifies that flagged and unresolved records are
still present in the universe. Deleting a record and flagging a record are different acts; only
one of them is reversible by reading the file.

## 5. Where this project may write

Only under `class_a_gpcr_atlas/`:

```
config/      frozen vocabularies and endpoint configuration
governance/  this document set
pipeline/    fetch, normalise, project
schemas/     JSON Schemas (schemas/drafts/ is explicitly not in use)
data/        cache/, raw/, normalized/, manifests/, freezes/
reports/     human-readable output
tests/       validation suite
```

Nothing is written to `/tmp`, to the parent directory, or to any sibling project.

## 6. If a violation is found

1. Stop. Do not continue the phase.
2. Restore the file from the baseline hash and record which file, which hash, and which run.
3. Add an entry to [`DECISION_LOG.md`](DECISION_LOG.md) describing how the write happened.
4. Re-run the full test suite before resuming.

A violation is a process failure, not a file problem: the file can be restored, but the reason
the pipeline could write there has to be removed.
