# Accessibility release audit

Phase 6A. Release candidate `0.1.0-rc.4`. Raw results: `accessibility_results.json`.
Harness: `tests/phase6a/accessibility_tests.py`, run against real Chrome via CDP.

**67 automated checks, 0 failed** — after four genuine defects were found and fixed.

**This is not a WCAG conformance claim.** Automated tooling finds a minority of accessibility
problems. What it cannot tell you is in `ACCESSIBILITY_MANUAL_CHECKLIST.md`, and that work has
not been done.

---

## 1. What was checked, and how

Five views were audited — landing in both themes, family, structures, and the 3D modal — for
document structure, naming, contrast, keyboard operation and language.

Two decisions about method are worth stating, because they determine whether the results mean
anything:

**Contrast was computed, not eyeballed.** The harness reads the computed `color` of every text
node, walks up the DOM for the first opaque background (a transparent element inherits what is
behind it), computes the WCAG relative-luminance ratio, and compares it against 4.5:1 — or 3:1
where the text qualifies as large. Judging contrast by looking at it is how contrast bugs ship.

**Keyboard behaviour was driven with real key events.** The first version of this harness called
`element.focus()` and reported that **33 of 33 controls had no visible focus indicator**. That
was wrong — and wrong in the most dangerous direction, because it looked like a serious finding.
`:focus-visible` deliberately does not match programmatic focus. Re-driven with genuine Tab
keypresses through CDP, every tab stop shows the focus ring the stylesheet defines. Three
"failures" in the first run were artifacts of the probe and are recorded here rather than
quietly dropped, because a validation report that hides its own false positives cannot be
trusted about its true ones.

## 2. Defects found and fixed

All four were real, and all four were fixed in source with the candidate rebuilt.

### 2.1 Active navigation link failed contrast in dark theme — **WCAG AA failure**

`.navlink.active` painted white text on the accent colour. In the dark theme the accent is a
light blue `#69b3d6`, giving **2.33:1** against white — well under the 4.5:1 minimum, and the
active navigation item is exactly the element a user needs to read to know where they are.

Fixed by introducing `--accent-ink` per theme rather than hardcoding `#fff`: white on the light
theme's darker accent (**5.54:1**), and dark ink `#10141a` on the dark theme's accent
(**7.93:1**). The accent itself was left alone, since it is used for links and focus rings
throughout and changing it would have moved everything to fix one thing.

### 2.2 The 3D canvas had no text alternative

A WebGL canvas is opaque to assistive technology. Without a name it is announced as nothing at
all, so a screen-reader user reaching the centre of the viewer found silence.

Fixed by giving the canvas `role="img"` and an `aria-label` naming the structure it displays and
pointing at the side panel where the same information exists as text — in both Turkish and
English, through the existing i18n system rather than a hardcoded string.

### 2.3 124 focusable elements remained reachable behind the open modal

The modal already trapped **Tab**. But a focus trap in JavaScript does not stop a screen
reader's virtual cursor or browser find-in-page, both of which walked straight into the page
behind the dialog — where a user could activate a link they could not see.

Fixed with `inert` plus `aria-hidden` on the background while the dialog is open.

### 2.4 The first fix for 2.3 was incomplete — a lesson worth recording

The initial fix listed landmarks: `header.top`, `#nav`, `#main`, `footer`. Re-running dropped
the count from 124 to **2** — and those two were the skip link and a breadcrumb, both sitting
directly on `<body>` outside every named landmark.

A selector list is a guess about page structure that decays as the page changes. Replaced with
the structural rule: **every direct child of `<body>` except the dialog** becomes inert. Count
went to 0, and the fix does not need revisiting when a footer is added.

## 3. Results after the fixes

| Group | Checks | Failed |
|---|---:|---:|
| landing (grey theme) | 13 | 0 |
| landing (dark theme) | 13 | 0 |
| family view | 13 | 0 |
| structures view | 13 | 0 |
| 3D modal | 9 | 0 |
| keyboard | 2 | 0 |
| language | 3 | 0 |
| **Total** | **67** | **0** |

What passes, specifically:

- `lang` set on `<html>` and **it follows the interface language** — switching to English
  updates it, so a screen reader does not read English text with Turkish pronunciation.
- Exactly one `<h1>` per view; no heading level skipped; `main` landmark present.
- Every button, link and form control has an accessible name. Every image has `alt`.
- No positive `tabindex`; no focusable content inside `aria-hidden` containers.
- External links carry `rel="noopener"`.
- **All text meets WCAG AA contrast in both themes.**
- The modal has `role="dialog"`, `aria-modal="true"`, an accessible name, a named close control,
  takes focus on open, returns focus on close, and **closes on a real Escape keypress**.
- Every tab stop shows a visible focus indicator.

## 4. What automated checking cannot tell you

This is the important section. All 67 checks passing means the page has no *machine-detectable*
accessibility defects. It does not mean the atlas is usable by someone who relies on assistive
technology.

Not covered by any check above:

- **Whether the canvas label is actually useful.** A machine confirms a label exists. Whether
  "Interactive 3D view of structure 6GPX" helps someone who cannot see it — and whether the side
  panel really carries the equivalent information — needs a person.
- **Whether the reading order makes sense** when linearised by a screen reader.
- **Whether dynamic updates are announced.** Two `aria-live="polite"` regions exist (`#status`
  and `#famlabel`, with `aria-busy` toggled during loading), so the mechanism is present. What no
  check verifies is *coverage* — whether every meaningful change, filtering in particular,
  actually reaches one of them, and whether the announcement is useful when it does.
- **Whether the interface is usable at 200% zoom or with a 320px viewport.** Overflow was tested;
  usability was not.
- **Whether the Turkish and English strings are equally clear** to screen-reader users.
- **Anything about cognitive load**, which no tool measures.
- **The colour-blind experience.** Contrast ratios pass; whether the encoding relies on hue
  alone anywhere was not tested and needs review.

## 5. Status

| | |
|---|---|
| Automated checks | **67 passed, 0 failed** |
| Real defects found and fixed | 4 |
| Probe artifacts identified and corrected | 3 |
| Manual testing with assistive technology | **not performed** |
| WCAG conformance claim | **none made** |

**Recommendation:** the automated result is good enough that manual testing would be productive
rather than drowned in obvious defects — which is what it is for. It is not a substitute for
that testing, and no conformance statement should appear in the release until a person has
worked through `ACCESSIBILITY_MANUAL_CHECKLIST.md`.
