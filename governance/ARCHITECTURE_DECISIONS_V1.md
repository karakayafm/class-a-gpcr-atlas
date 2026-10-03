# Architecture decisions — v1 (frozen)

Decisions about how the code is built. Decisions about what the data means are in
[`SCIENTIFIC_DECISIONS_V1.md`](SCIENTIFIC_DECISIONS_V1.md).

---

## AD-01 — Standard library only

**Decision.** Python ≥ 3.10, no third-party packages. Declared in `config/project.json`.

**Reason.** The pipeline must be runnable years from now, on a machine whose environment nobody
kept, without resolving a dependency graph. Every dependency added here is a future
reproducibility failure. The cost is real but bounded: an HTTP client with caching (~120 lines)
and a JSON Schema validator (~110 lines).

**Consequence.** `pipeline/common/schema.py` implements only the Draft 2020-12 keywords the
project's own schemas use, and `assert_no_unsupported_keywords()` fails loudly if a schema
starts using one it cannot check. A validator that silently ignores a keyword is worse than no
validator, because it reports success it did not earn. The test suite runs that assertion over
all nine schemas.

---

## AD-02 — Independent directory, no shared code

**Decision.** Everything lives under `class_a_gpcr_atlas/`. Nothing is imported from the
aminergic project, and nothing is written outside this directory.

**Reason.** Shared code means the frozen reference application can be broken by a change made
for Class A. Duplication is the cheaper risk. The read-only test verifies the boundary from the
other side by re-hashing all 350 frozen files.

---

## AD-03 — Canonical JSON, sorted keys, no formatting

**Decision.** All artefacts are written with `sort_keys=True`, `separators=(",", ":")`,
`ensure_ascii=False`.

**Reason.** A hash is only meaningful if serialisation is deterministic. Sorted keys also make
diffs between runs readable, which is how a data change is noticed.

**Consequence.** Artefacts are single-line and not meant to be read by eye; the reports exist
for that.

---

## AD-04 — Volatile fields are named, not guessed

**Decision.** `VOLATILE_KEYS` in `pipeline/common/canonical.py` is an explicit frozen set:
`retrieved_at`, `retrieval_timestamp`, `generated_at`, `queried_at`, `cache_path`,
`elapsed_seconds`, `retry_count`, `response_sha256`, `http_status`, `response_content_type`.

**Reason.** Deciding volatility by pattern-matching field names would eventually strip a
scientific field that happens to contain "time". An explicit list is auditable and fails safe:
an unlisted field is treated as science and changes the content hash.

---

## AD-05 — Only a successful body touches the cache

**Decision.** `pipeline/common/http.py` writes to the cache only after a 2xx response has been
decoded. Failures are recorded in the provenance list, never cached.

**Reason.** A cached error page is indistinguishable from a cached result on the next run, and
would poison every subsequent build until someone thought to clear the cache. Not caching
failures means a re-run retries them, which is the desired behaviour.

---

## AD-06 — Provenance is recorded per request

**Decision.** Every request records provider, endpoint, parameters, timestamp, HTTP status,
content type, response SHA-256, cache path, cache-hit flag, retry count and error message.

**Reason.** "Where did this number come from" must be answerable per field, not per project. The
response hash in particular lets a later run detect that a source changed its answer without
changing its schema.

---

## AD-07 — Fetch, normalise, project: three separable stages

**Decision.** Fetching (`pipeline/taxonomy`, `pipeline/universe`, `pipeline/inventory`) is
separate from projection (`pipeline/families/extract_family.py`), which performs no network I/O.

**Reason.** A family folder must be regenerable offline from the universe. It also means the
per-family output cannot drift from the universe, because it has no independent source of truth
— the test suite asserts the projection is exact in both directions.

---

## AD-08 — Two levels of inventory

**Decision.** Entity *availability* is recorded for all 1358 structures; the *full* entity
inventory is fetched only for the pilot family (100 structures, 560 entities).

**Reason.** Fetching every entity of every Class A structure is on the order of ten thousand
requests against a public API, for data that Phase 1 does not analyse. Recording availability
answers the question Phase 1 actually asks — *can this be built when we need it* — at the cost
of one field per structure. Scaling out is then a parameter change, not a redesign.

---

## AD-09 — Configuration vocabularies are data, not code

**Decision.** Entity types, binding-site types, transducer classes and QC flags live in
`config/*.json` with explicit status flags (`production_ready`, `assigned_in_phase_1`,
`normalised_in_phase_1`).

**Reason.** The status flags are the mechanism that keeps a deferred decision deferred: the test
suite reads them and fails if one has been quietly flipped. A vocabulary hard-coded in a Python
module could be extended in a commit that looks like refactoring.

---

## AD-10 — A flag must be declared before it can be emitted

**Decision.** Every QC flag string emitted by any stage must exist in `config/qc_flags.json`.
Enforced by the test suite for both the universe and the inventory stages.

**Reason.** Undeclared flags accumulate as ad-hoc strings that nobody can enumerate, and a flag
nobody can enumerate cannot be reasoned about. The inventory stage introduced five new flags
(`component_is_water`, `branched_entity_glycan`, `polymer_is_nucleic_acid`,
`polymer_type_unrecognised`, `entity_inventory_empty`); each was added to the config before the
test would pass.

---

## AD-11 — Bounded concurrency, retries, no politeness theatre

**Decision.** GPCRdb: 4 workers, 3 retries, 120 s timeout. RCSB: 6 workers, 3 retries, 60 s
timeout. Configured in `config/source_endpoints.json`, not in code.

**Reason.** These are public scientific services. Bounded worker counts and honest timeouts are
the actual courtesy; the caching layer means a re-run costs the provider nothing at all.

---

## AD-12 — Reports are generated, artefacts are hashed

**Decision.** Human-readable reports live in `reports/`; hashes of the artefacts they describe
live in `data/freezes/phase_1/`.

**Reason.** A report that quotes a number without a hash cannot be checked against the artefact
it describes. Separating them means a report can be rewritten for clarity without touching the
freeze, and a freeze mismatch is unambiguous.
