# Third-party notice audit

Phase 6A. Scope: every third-party component the release candidate distributes, the obligation
each licence creates, and whether the release currently satisfies it.

This audit covers **software**. Data sources are audited separately in
`DERIVED_DATA_REVIEW_PACKET.md` and `DATA_DISTRIBUTION_MATRIX.csv`.

Nothing here is a legal opinion. It records what each licence text says and what the release
does, so that someone qualified can compare the two.

---

## 1. What the release ships

The application has **one** third-party file: `vendor/ngl.js`, 1,283,924 bytes.

That single file is a bundle. Auditing it by filename would have found one MIT library; reading
it found five distinct copyright holders under three different licences.

| Component | Where | Licence | Copyright |
|---|---|---|---|
| NGL Viewer 2.3.1 | the file itself | MIT | Alexander S Rose, 2014–2017 |
| three.js r158 | bundled inside | MIT | three.js authors, 2010–2023 |
| chroma.js | bundled inside | BSD 3-clause | Gregor Aisch, 2011–2017 |
| ColorBrewer colour tables | bundled inside chroma.js | Apache 2.0 | Cynthia Brewer, Mark Harrower, Pennsylvania State University, 2002 |
| JS Signals 1.0.0 | bundled inside | MIT (stated inline) | Miller Medeiros |
| Kdtree | bundled inside | MIT (stated inline) | Alexander Rose; Roman Bolzern; I4DS, 2013–2016 |

No other third-party code is distributed. The pipeline is standard-library Python; there is no
`node_modules`, no build-time dependency, and no runtime request to any external host.

## 2. Provenance of the vendored bundle — verified, not asserted

The file was hashed and compared against the published distribution:

| | |
|---|---|
| Vendored `app/vendor/ngl.js` | `0e8fea984b0e306d948d675f30e10f5a275ab5b4ce2135191a6787ec1b29dc5d` |
| `https://cdn.jsdelivr.net/npm/ngl@2.3.1/dist/ngl.js`, retrieved 2026-08-05 | `0e8fea984b0e306d948d675f30e10f5a275ab5b4ce2135191a6787ec1b29dc5d` |
| **Match** | **byte-identical, 1,283,924 bytes** |

This matters more than it looks. "We vendored NGL 2.3.1" is a claim about a file nobody
re-checked; a matching hash against the published artefact is evidence the shipped bundle is
unmodified upstream code and not a locally patched variant that happens to carry the same name.

The same hash appears in the frozen aminergic project's `COPY_MANIFEST.md`, so both projects
demonstrably ship the same bytes.

**Version determination.** `2.3.1` comes from the recorded source URL and the version string in
the file. `three.js r158` was **observed** rather than assumed: the bundle sets
`data-engine="three.js r158"` on the WebGL canvas at runtime. The bundle does not otherwise
announce which three.js it carries, so this is the only first-party evidence available.

## 3. The obligation, and the defect this audit found

Every licence above requires the same minimum: the copyright notice and permission notice must
travel with the distributed software.

**Finding — the release candidate `rc1` did not satisfy this.** The vendored `ngl.js` carries
inline notices for chroma.js, ColorBrewer, JS Signals and Kdtree, but **carries no NGL copyright
or licence header of its own** — the minified bundle begins directly with executable code. NGL's
`LICENSE` file lives in the source repository and is not part of the distributed `dist/ngl.js`.

So a release consisting of the site directory plus that bundle would have distributed MIT
software while omitting the one thing MIT asks for. Neither is three.js's notice present.

This is not a hypothetical. It is the ordinary failure mode of vendoring a minified bundle: the
notice obligation attaches to the file you ship, and the file you ship dropped it.

**Resolution.** `app/THIRD_PARTY_NOTICES.md` was written, carrying the verbatim licence text for
each component, and `pipeline/phase6a/build_rc.py` now copies it into the site **and into every
one of the eleven offline family exports** — an offline export is a complete copy of the
software, so it carries the same obligation. The builder refuses to produce a release candidate
if the notice file is absent. Release candidate `0.1.0-rc.2` was built with this fix.

`tests/phase6a/rc_integrity_tests.py` checks that the notice ships with the site and with all
eleven exports, that it names each copyright holder, and that the vendored bundle still hashes
to the published distribution.

## 4. Licence texts retrieved

Stored under `data/licences/third_party/`, each with the retrieval URL and hash recorded in
`RETRIEVAL_RECORD.json`. All retrieved 2026-08-05.

| Component | Source | SHA-256 | Bytes |
|---|---|---|---|
| NGL 2.3.1 | `raw.githubusercontent.com/nglviewer/ngl/v2.3.1/LICENSE` | `72883774990bc468…` | 1083 |
| three.js r158 | `raw.githubusercontent.com/mrdoob/three.js/r158/LICENSE` | `852e0e8699169bf9…` | 1081 |
| chroma.js | `raw.githubusercontent.com/gka/chroma.js/master/LICENSE` | `85aae67406281155…` | 2418 |
| Apache 2.0 (for ColorBrewer) | `www.apache.org/licenses/LICENSE-2.0.txt` | (stored) | 11358 |

## 5. Open item — JS Signals

**A standalone licence file for JS Signals could not be retrieved.** `LICENSE`, `LICENSE.txt`
and `MIT-LICENSE.txt` at the project's repository root each returned HTTP 404 on 2026-08-05.

The bundle carries an inline statement — *"Released under the MIT license, Author: Miller
Medeiros"* — and that statement is reproduced verbatim in the notices file. What has **not**
been done is substitute a generic MIT body under that author's name. A licence text the upstream
project did not publish at the location checked would be a document this project invented, and
an invented licence is worse than a missing one because it looks settled.

Two ways to close this, neither taken here because both are the owner's call:

1. Retrieve the licence from the npm package tarball or a release archive of `js-signals`, which
   may carry a licence file the repository root does not expose at these paths.
2. Accept the inline notice as sufficient — it is a first-party statement of the licence by the
   author, in the shipped file.

**Severity: low.** The component is MIT by its own inline declaration; the question is
documentary completeness, not permission.

## 6. Retrieval note

`unpkg.com` timed out on every attempt during this audit; `cdn.jsdelivr.net`,
`raw.githubusercontent.com` and `www.apache.org` all responded in the same session. The recorded
provenance URL for the vendored file remains the unpkg one, because that is where it was
originally fetched. The jsDelivr retrieval serves as an independent confirmation of the same npm
artefact, not as a replacement of the provenance record.

## 7. Status

| Obligation | Status |
|---|---|
| Notice ships with the site | **satisfied in `0.1.0-rc.2`** (was a defect in `rc1`) |
| Notice ships with all 11 offline exports | **satisfied in `0.1.0-rc.2`** |
| Every copyright holder named | satisfied |
| Verbatim licence text for NGL, three.js, chroma.js, ColorBrewer | satisfied |
| Verbatim standalone licence text for JS Signals | **open — see §5** |
| Vendored bundle provenance verified | satisfied |
| This project's own code licence stated | **undecided — DD-12, not a third-party question** |

No third-party licence in this list is copyleft. Nothing in §1 constrains the licence the owner
may choose for this project's own code. The constraints that exist come from the **data**
sources, and they are in `DERIVED_DATA_REVIEW_PACKET.md`.
