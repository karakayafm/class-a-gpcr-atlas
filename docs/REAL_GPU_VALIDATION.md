# Real-GPU validation

Phase 6A. Release candidate `0.1.0-rc.4`, manifest `d8c199f3248f4308…`.
Raw results: `real_gpu_results.json`, `REAL_GPU_ENVIRONMENT.json`, `REAL_GPU_RAW_LOG.txt`.

**`REAL_GPU_STATUS = PASSED` — 61 checks, 0 failed.**

---

## 1. Why this report exists separately from the Chromium regression suite

Phase 5 tested the viewer under `--headless=new`, which on this machine may fall back to a
software rasterizer. A WebGL test that passes on SwiftShader proves the code paths execute; it
proves nothing about a real driver, and driver-specific failures — context limits, extension
availability, actual context loss — are precisely what a 3D viewer breaks on.

So the first thing this harness does is establish which renderer it is actually using, and it
refuses to report a pass as a real-GPU pass unless the renderer is genuinely hardware.

## 2. The renderer, recorded rather than assumed

| | |
|---|---|
| WebGL renderer | `ANGLE (NVIDIA Corporation, NVIDIA GeForce RTX 4070 Ti SUPER/PCIe/SSE2, OpenGL 4.5.0)` |
| WebGL vendor | `Google Inc. (NVIDIA Corporation)` |
| WebGL version | WebGL 2.0 (OpenGL ES 3.0 Chromium) |
| GPU model | NVIDIA GeForce RTX 4070 Ti SUPER |
| GPU driver | 535.309.01 |
| GPU memory | 16376 MiB |
| **Software rasterizer detected** | **false** |
| **`real_gpu`** | **true** |
| Hardware acceleration | enabled |
| Browser | Google Chrome 149.0.7827.114 |
| OS / kernel | Linux 6.8.0-124-generic, DISPLAY `:1` |
| Screen | 1920×1080, devicePixelRatio 1 |
| `WEBGL_lose_context` extension | available |

The detection is a substring test against `swiftshader`, `llvmpipe`, `softpipe` and
`software rasterizer` in the renderer string. If any matched, `real_gpu` would be false and this
report would say so — a software result may never be presented as a hardware one.

The harness also records which release candidate it tested (`atlas_rc_dir: rc4`,
`atlas_rc_version: 0.1.0-rc.4`, `tested_url`). An earlier version of the harness read a
hardcoded `rc1` path, so its environment file named a build it had not tested. That was fixed
before this report was written; correctness about *what* was tested is not optional in a
validation report.

## 3. Structure matrix — 10 cases, 45 checks

Cases were chosen to span the ways a Class A structure can differ, not to be representative by
count: small-molecule pocket, polymer/peptide interface, covalent ligand, apo, multi-ligand,
ion-containing, largest and smallest bundle, a structure with auxiliary chains, and one with
multiple observations.

For each case the harness opened the 3D view, exercised **all ten viewer controls** (cartoon,
all ligands, contacts, lines, surface, motifs, motif labels, ions, auxiliary chains, spin),
switched observation where more than one exists, reset the view, followed the source link, then
closed the modal and re-counted the WebGL objects.

**Result: 45 of 45 passed.** Every case opened, every enabled control toggled, and — the check
that matters — after closing, `canvasCount`, `stageCount` and `listenerCount` were all **0**.
A control that is legitimately unavailable for a structure (`ions` on a structure with no ions)
is recorded as `disabled` rather than silently skipped.

Open times ranged from 0.25 to 0.27 s for typical bundles.

## 4. Lifecycle — 20 open/close cycles

The viewer was opened and closed 20 times. Each cycle recorded canvas, stage and listener counts
while open and after close.

**Result: 10 of 10 checks passed.** Every cycle showed exactly 1 canvas, 1 stage and 2 listeners
while open, and 0, 0, 0 after close. No accumulation across 20 cycles.

JS heap before the cycles: 41,824,700 bytes. After: **36,025,749 bytes** — lower than at the
start, which is what garbage collection doing its job looks like. Heap alone is a poor leak
signal, which is why the assessment rests on the object counts rather than on the number going
down.

## 5. Controlled context loss

The one failure mode a software rasterizer cannot honestly reproduce.

Using `WEBGL_lose_context`, the harness forced the GPU context to be lost while a structure was
open, then verified the application's response and reopened.

| Stage | canvas | stage | listeners | contextLost |
|---|---:|---:|---:|---:|
| Before loss | 1 | 1 | 2 | false |
| After forced loss | **0** | **0** | **0** | true |
| After reopen | 1 | 1 | 2 | false |

**4 of 4 checks passed.** The application tears the stage down on `webglcontextlost` rather than
leaving an orphaned canvas behind, and a subsequent open produces exactly one canvas — not two.

## 6. Console

**No uncaught JavaScript errors** across the entire run: 10 structures, 20 cycles, a forced
context loss and every control toggled.

This check earned its place. Earlier in Phase 6A the same harness caught three genuine
application defects that headless testing had not surfaced — a deep link that threw, a
representation toggle firing against a torn-down component, and a language change that rebuilt
the viewer and lost the user's camera. All three were fixed in source and the candidate rebuilt.

## 7. Summary

| Group | Checks | Failed |
|---|---:|---:|
| Environment | 1 | 0 |
| Structure matrix | 45 | 0 |
| Lifecycle (20 cycles) | 10 | 0 |
| Context loss | 4 | 0 |
| Console | 1 | 0 |
| **Total** | **61** | **0** |

**`REAL_GPU_STATUS = PASSED`** on genuine NVIDIA hardware.

## 8. What this does not cover

- **One GPU, one driver, one OS.** NVIDIA 535.309.01 on Linux. AMD, Intel integrated graphics,
  Apple Silicon and Windows drivers are untested. WebGL behaviour differs across them, and this
  result should not be read as covering hardware it never touched.
- **One browser engine for the GPU tests.** Firefox was validated separately
  (`FIREFOX_TEST_REPORT.md`); Safari/WebKit is untested entirely.
- **No mobile GPU testing.** Viewport sizes were simulated; mobile GPUs and their much lower
  texture and memory limits were not exercised.
- **Not a performance benchmark.** Timings are recorded for context, not as a claim about
  performance on other hardware.
