# External link audit

Phase 6A, release candidate `0.1.0-rc.2`, checked 2026-08-05.
Raw results: `external_link_results.csv`.

---

## 1. Method

Every `http://` or `https://` URL was extracted from every HTML, CSS, JS, JSON, Markdown and
text file in the release candidate's site directory. **4107 distinct URLs** were found.

They were not all requested. 4074 of them are three per-structure templates repeated across 1358
structures; issuing 4107 requests at a source that serves this project's data for free would be
inconsiderate and would tell us nothing that a sample does not. Instead:

- URLs were grouped into **patterns**. Three templated patterns account for 4074 URLs.
- **12 URLs per pattern** were sampled with a fixed seed (20260805), so the sample is reproducible.
- Every **singleton** URL — 33 of them, each appearing under a single distinct address — was
  requested individually.

Requests used `GET` with a 25-second timeout, a 0.4-second delay between sampled requests, and
an identifying User-Agent. Redirects were followed and the final URL recorded.

## 2. Results

| Pattern | URLs in release | Sampled | HTTP 200 | Other |
|---|---:|---:|---:|---:|
| `https://www.rcsb.org/structure/{PDB_ID}` | 1358 | 12 | **12** | 0 |
| `https://gpcrdb.org/structure/{PDB_ID}` | 1358 | 12 | **12** | 0 |
| `https://doi.org/10.2210/pdb{PDB_ID}/pdb` | 1358 | 12 | **12** | 0 |
| Singletons | 33 | 33 | 29 | 4 |
| **Total** | **4107** | **69** | **65** | **4** |

All three templated patterns resolved cleanly on every sampled structure, including the RCSB
entry DOIs — those are real, resolvable DOIs minted by RCSB, and this audit confirms they
resolve rather than assuming it.

## 3. The four non-200 results, individually

Each was examined. **None is a broken link in the application.**

### 3.1 `https://doi.org/10.2210/pdb{PDB_ID}/pdb` → 404

Not a link. It is the **DOI pattern string** stored in `references.json` so the interface can
construct per-structure DOIs. `{PDB_ID}` is a literal placeholder. A 404 is the correct response
to requesting it, and the extractor picking it up is a property of scanning JSON values rather
than a defect. **No action.**

### 3.2 `https://www.rcsb.org/structure/` → 404

Not a link either. It is the base of a string concatenation in `js/views/views.js:145`:

```javascript
el("a", { href: "https://www.rcsb.org/structure/" + x.pdb_id, ... })
```

The extractor captured the literal without its concatenated identifier. Every structure's
`viewer_meta.json` was checked directly for a truncated or empty `full_structure_url`: **none of
the 1358 has one**. **No action.**

### 3.3 `https://raw.githubusercontent.com/millermedeiros/js-signals/master/LICENSE.txt` → 404

A genuine 404, and an expected one. This URL appears only inside
`data/licences/third_party/RETRIEVAL_RECORD.json`, where it is recorded as a **failed retrieval
attempt**. The audit confirming it 404s confirms the record is accurate. Discussed in
`THIRD_PARTY_NOTICE_AUDIT.md` §5. **No action beyond the open item already logged.**

### 3.4 `http://millermedeiros.github.com/js-signals/` → DNS failure

A dead host. `github.com` retired the `*.github.com` Pages domain in favour of `github.io` years
ago, so this address no longer resolves.

It appears in two places, both of them **inside a licence notice**: the upstream NGL bundle
carries it in the JS Signals header, and `THIRD_PARTY_NOTICES.md` reproduces that header
verbatim. It is not a link the application renders or follows.

**No action, deliberately.** The correct handling of a stale URL inside a third-party copyright
notice is to reproduce the notice as the author wrote it. "Fixing" the URL would mean altering a
licence notice, which is exactly what a notices file must not do. It is recorded here so the
staleness is known rather than discovered later.

## 4. Insecure (`http://`) URLs

Four distinct `http://` URLs appear in the release. **All four are inside licence texts** — the
Apache 2.0 URL in the ColorBrewer notice, the MIT licence URL in the Kdtree header, the FHNW
institutional URL in that same header, and the dead js-signals URL from §3.4.

**None is rendered as a link, and none is requested by the application.** They are historical
strings inside copyright notices, and they are left exactly as their authors wrote them.

The application itself renders exactly three outbound link types, all `https://`, all with
`target="_blank"` and `rel="noopener"` (verified in `js/views/views.js`).

## 5. What the application requests at runtime

This is the part that matters more than the link inventory, and it was checked directly rather
than inferred:

| | |
|---|---|
| External hosts contacted at runtime | **none** |
| `<script src>` / `<link href>` pointing outside the release | **none** — `css/atlas.css`, `js/app.js`, `vendor/ngl.js` only |
| `fetch()` call sites | **one**, in `js/data/loader.js`, resolving against the local payload base |
| CDN dependencies | none — NGL is vendored |
| Analytics, telemetry, tracking, fonts, beacons | none |

Every outbound URL in the release is a link a **user may choose to click**. Nothing is fetched
on the user's behalf. This is what makes the offline exports work, and it is also why the
release has no privacy surface — see `SECURITY_PRIVACY_AUDIT.md`.

## 6. Durability note

Link rot is a question of *when*, not *if*. Three observations for whoever maintains this:

- The **RCSB entry DOIs are the most durable** of the three patterns. A DOI is designed to
  survive a URL change; `https://www.rcsb.org/structure/{ID}` is not. If only one link per
  structure were kept, the DOI is the one to keep.
- The GPCRdb structure pages depend on GPCRdb's URL scheme remaining stable. It is not versioned
  and this project captured no GPCRdb release identifier (see `DERIVED_DATA_REVIEW_PACKET.md`
  §7.1), so a scheme change would be silent.
- Nothing in the release **breaks** if every external link dies. The atlas is complete offline;
  external links are provenance, not dependencies.

## 7. Status

| Check | Result |
|---|---|
| Templated links resolve | **PASS** — 36/36 sampled across three patterns |
| Singleton links resolve | 29/33; the 4 exceptions each explained above, none an application defect |
| Application links use `https` | **PASS** |
| External links use `rel="noopener"` | **PASS** |
| Runtime requests to external hosts | **none** |
| Broken links visible to a user | **none found** |
