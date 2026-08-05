# Security and privacy audit

Phase 6A, release candidate `0.1.0-rc.2`, 2026-08-05.

The atlas is a static site with no server, no accounts and no data collection, which removes most
of what a security audit normally examines. This report states what was checked, what was found,
and — where the answer is "nothing" — how that was established rather than assumed.

---

## 1. Attack surface

| Surface | Present? |
|---|---|
| Server-side code | **no** — static files only |
| Database | no |
| User accounts, sessions, authentication | no |
| Form inputs submitted anywhere | no |
| Cookies, `localStorage`, `sessionStorage` | see §4 |
| Third-party scripts, CDNs, fonts | **no** — NGL is vendored, nothing is fetched externally |
| Analytics, telemetry, error reporting | **no** |
| File upload | no |
| Network requests at runtime | **local payloads only** (one `fetch()` call site) |

The realistic threat model for a static scientific atlas has two entries: injection into the
page through the data it displays, and injection into a **file the user exports** that is then
opened in another program. Both are examined below.

## 2. Cross-site scripting

**The application never assigns HTML from data.** Verified by reading every DOM construction
path: nodes are created through the `el()` helper in `js/core/dom.js`, and text is set through
`textContent`. There is no `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`,
`eval`, or `new Function` on any data path.

This matters because the displayed values are **upstream-controlled**: ligand names, receptor
names, structure titles and author lists come from GPCRdb and RCSB. A future deposition title
containing `<script>` would be displayed as those literal characters, not executed.

The remaining route into the page is the URL hash, which drives routing. Route parameters are
compared against known family and structure identifiers; an unrecognised value renders the
landing view rather than being reflected into the document. The Phase 6A real-GPU harness found
and fixed a genuine defect on this path — a deep link naming a structure without a family threw
— but the failure was availability, not injection.

## 3. CSV export and spreadsheet formula injection

This is the one finding in this report that warrants an action, so it is stated in full.

**What was checked.** The client-side exporter (`js/components/csv.js`) escapes per RFC 4180:
values containing a quote, comma, CR or LF are quoted and internal quotes doubled. That is
correct CSV.

**What it does not do.** It applies no guard against *formula injection*. A cell whose value
begins with `=`, `+`, `-`, `@`, tab or CR is interpreted as a formula by Excel and LibreOffice
when the file is opened. A value such as `=HYPERLINK(...)` or a `DDE` payload in a downloaded CSV
is a well-known route to code execution on the person opening it — the vulnerability lands on
the user's machine, not the site.

**Is it currently exploitable? No.** Every string value in the shipped payloads was scanned:

| | |
|---|---|
| String values scanned | **287,485** (family payloads, global payloads, all 1358 `viewer_meta.json`) |
| Values beginning with `=`, `+`, `@`, tab or CR | **0** |
| Values beginning with `-` followed by a non-digit | **0** |

Every CSV this project itself writes was also scanned — the curation queue, decision templates,
priority and conflict tables, the distribution matrix and the link results: **8565 cells, zero
formula triggers.**

**So why is it a finding?** Because the absence is a property of today's data, not of the code.
The values are supplied by external databases. A ligand name, mutation string or structure title
beginning with one of those characters would flow through the exporter unchanged, and nothing in
the pipeline or the application would notice. The safe state is currently accidental.

**Recommended action (low severity, not a release blocker):** prefix any exported value whose
first character is `=`, `+`, `-`, `@`, tab or CR with a single quote, or wrap it as `"\t"+value`.
Roughly three lines in `esc()`. Not applied in this build because it changes an application
artefact after the validation runs; it is recorded here and in the Phase 6B recommendation so it
is fixed deliberately rather than in passing.

## 4. Client-side storage

The application stores the **theme preference** and the **interface language** (TR/EN). Both are
user-set display preferences, both are single short values, and neither identifies anyone.

No cookies are set. No storage is used for anything else. Nothing stored is transmitted, because
nothing is transmitted at all.

## 5. Personal data

**The release contains no personal data of the people who use it.** There is no collection
mechanism of any kind: no server to log to, no analytics, no beacons, no form submission.

The corpus does contain **published bibliographic author names** relayed from RCSB structure
citation metadata. These are published scholarly records, not personal data collected by this
project, and they are reproduced unchanged from the source.

**The curation workflow will record curator names and review dates.** That is deliberate — an
unattributable curation decision is worthless. Two points about it:

- Those records live in `data/curation/`, which is **not part of the distributed site**. It was
  verified that no curation record path appears in the release candidate.
- The workflow refuses names matching known automated systems
  (`pipeline/phase6a/validate_curator_decisions.py`), so the identity field means what it says.

If curation records are ever published, whether curator names go with them is a question for the
owner and the curators, not a technical default. It is not currently in scope for release.

## 6. Content Security Policy

**No CSP is set.** `index.html` carries no `Content-Security-Policy` meta tag, and a static file
release has no server to send the header.

Given §1 and §2 — no external requests, no `innerHTML`, no inline event handlers on data paths —
a CSP would add little in practice. But it is defence in depth against a future change, and it is
cheap:

```
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:;
connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'
```

**Not added in this build**, for the same reason as §3: it modifies an application artefact after
validation. It requires testing, because NGL's WebGL and worker use may need `worker-src 'self'`
or `blob:`, and shipping an untested CSP that breaks the 3D viewer would be worse than shipping
none. Recorded for Phase 6B.

If the site is ever hosted behind a server or GitHub Pages, the same policy should be sent as a
header, which is strictly better than a meta tag.

## 7. Supply chain

| | |
|---|---|
| Build-time dependencies | **none** — standard-library Python only |
| `node_modules`, package manager lockfiles | none |
| Runtime dependencies | one vendored file, `vendor/ngl.js` |
| Vendored file provenance | **verified byte-identical** to the published `ngl@2.3.1` distribution (SHA-256 `0e8fea98…`) |
| Integrity check in the test suite | yes — `rc_integrity_tests.py` re-verifies the hash |

A vendored, hash-verified dependency with no package manager is a small supply-chain surface. The
tradeoff is that security updates to NGL will not arrive automatically; someone must notice.
That is a maintenance question, and it lands in the gap noted in the governance draft: **no
person or body has committed to maintaining this project.**

## 8. Denial of service and resource exhaustion

Not a server concern, but a client one. The viewer loads coordinate files up to several MB and
creates WebGL contexts. Phase 6A measured a 20-cycle open/close sequence on real GPU hardware:
canvas and listener counts did not grow monotonically, and cache eviction was observed working.
Details in `performance_memory.json`.

A structure large enough to exhaust memory would affect only the user's own tab.

## 9. Findings

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | CSV exporter has no formula-injection guard; no live vector in current data (0 of 287,485 values) | **low** | recorded for Phase 6B |
| 2 | No Content-Security-Policy | **low** | recorded for Phase 6B, needs testing against NGL |
| 3 | Vendored NGL will not receive security updates automatically | **informational** | maintenance gap, stated in governance draft |
| 4 | Stale `http://` URL inside a third-party licence notice | **informational** | deliberately not altered — see link audit §3.4 |

**No high or medium severity finding.** Nothing in this report blocks a release. Findings 1 and 2
should be fixed before a stable release, and both are small.
