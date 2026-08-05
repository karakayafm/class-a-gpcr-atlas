# Firefox test report

Phase 6A. Release candidate `0.1.0-rc.4`. Raw results: `firefox_results.json`, `FIREFOX_RAW_LOG.txt`.

**`FIREFOX_STATUS = PASSED` — 30 checks, 0 failed.**

---

## 1. Why a second engine

Every other browser test in this project runs on Chromium through the Chrome DevTools Protocol.
An application validated on one engine is validated for one engine's tolerances. The specific
risks that differ between Gecko and Blink and that this atlas is exposed to:

- **WebGL context handling** — the number of simultaneous contexts allowed, and what happens on
  the one after that, differ between engines.
- **`inert` and dialog semantics** — support landed at different versions.
- **CSS layout at narrow viewports** — overflow behaviour is a classic engine difference.
- **ES module loading from `file://` and over HTTP** — Firefox is stricter in places.

## 2. Harness

Firefox was driven through **geckodriver over the W3C WebDriver protocol**, using a WebDriver
client written for this project against the standard library (`tests/phase6a/webdriver.py`). No
Selenium, no Playwright, no npm — consistent with the project's stdlib-only constraint, which
otherwise would have been quietly broken by the test suite.

| | |
|---|---|
| Browser | Firefox 153.0 |
| Platform | Linux 6.8.0-124-generic |
| WebGL renderer | `NVIDIA GeForce GTX 980, or similar` (vendor: NVIDIA Corporation) |
| Software rasterizer | **false** |
| `real_gpu` | **true** |

**A note on the renderer string.** Firefox deliberately reports a *generalised* renderer —
"GTX 980, or similar" — as an anti-fingerprinting measure. The machine's actual GPU is an RTX
4070 Ti SUPER, as Chrome reports directly. This is a Firefox privacy behaviour, not a
misdetection and not a different device. What matters for validation is that it is hardware
rather than a software rasterizer, and it is.

## 3. What was checked — 30 checks, 0 failed

**Rendering and navigation.** Landing renders; all 11 family cards present; family view opens;
structures table renders; routing by URL hash works; deep links resolve.

**3D viewer.** The viewer opens in Firefox; exactly one canvas is created; the canvas is
released on close. This is the check most likely to differ by engine and it passed.

**Accessibility semantics.** The modal is labelled; closing the modal returns focus to the
element that opened it. Focus restoration is easy to get wrong and invisible until someone
navigates by keyboard.

**CSV export.** CSV building works and the export controls are present.

**Responsive layout — four viewports.** `desktop_wide`, `laptop`, `tablet`, `mobile_portrait`:
**no horizontal overflow in any of them.** A page that scrolls sideways on a phone is a defect
users notice immediately and developers on wide monitors never see.

**Console.** No captured page errors across the whole run.

## 4. Summary

| Area | Result |
|---|---|
| Rendering and routing | PASS |
| 3D viewer lifecycle | PASS |
| Accessibility semantics (label, focus return) | PASS |
| CSV export | PASS |
| Four viewports, no horizontal overflow | PASS |
| Console errors | none |
| **Total** | **30 checks, 0 failed** |

**`FIREFOX_STATUS = PASSED`.**

## 5. Cross-engine position

| Engine | Status | Checks |
|---|---|---:|
| Chromium (real GPU, NVIDIA) | PASSED | 61 |
| Chromium (regression suite) | PASSED | 42 |
| Firefox 153 (real GPU) | PASSED | 30 |
| **WebKit / Safari** | **untested** | — |

**WebKit is not tested at all**, and that gap is real rather than theoretical: Safari has the
most restrictive WebGL context limits of the three engines, and this application creates and
destroys contexts repeatedly. It is listed in `PHASE6B_RECOMMENDATION.md`. No claim of Safari
compatibility is made anywhere in the release.
