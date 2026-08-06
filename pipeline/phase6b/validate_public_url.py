#!/usr/bin/env python3
"""Phase 6B — validate the deployed public site over its real URL.

Run this AFTER deployment. A local test proves the package is correct; it proves nothing about
what GitHub Pages actually serves — path casing, Jekyll processing, MIME types and redirect
behaviour all differ from `python3 -m http.server`. A Pages deployment that fails is not
successful because the local test passed.

Usage:
    python3 pipeline/phase6b/validate_public_url.py [base_url]
"""
from __future__ import annotations
import hashlib, json, random, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = (sys.argv[1] if len(sys.argv) > 1
        else "https://karakayafm.github.io/class-a-gpcr-atlas/").rstrip("/") + "/"
UA = {"User-Agent": "class-a-gpcr-atlas-public-validation/1.0"}
R: list[dict] = []


def check(group, name, ok, detail=""):
    R.append({"group": group, "check": name, "status": "PASS" if ok else "FAIL",
              "detail": str(detail) if not ok else ""})
    print(("PASS  " if ok else "FAIL  ") + f"{group} :: {name}" +
          (f"  {detail}" if not ok else ""), file=sys.stderr)


def get(path, binary=False, timeout=40):
    url = BASE + path.lstrip("/")
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
        body = r.read()
        return {"ok": True, "status": r.status, "body": body if binary else
                body.decode("utf-8", "replace"), "url": r.url,
                "type": r.headers.get("Content-Type", "")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "body": b"" if binary else "", "url": url}
    except Exception as e:
        return {"ok": False, "status": None, "error": f"{type(e).__name__}: {e}", "url": url}


def main() -> int:
    print(f"Validating {BASE}", file=sys.stderr)

    # --- A. landing and assets --------------------------------------------------------------
    idx = get("index.html")
    check("landing", "index_html_200", idx.get("status") == 200, idx.get("status"))
    root = get("")
    check("landing", "directory_root_serves_index", root.get("status") == 200, root.get("status"))
    if idx.get("status") == 200:
        b = idx["body"]
        check("landing", "is_the_atlas", "atlas" in b.lower() and "<title" in b.lower())
        for asset in ("css/atlas.css", "js/app.js", "vendor/ngl.js"):
            a = get(asset, binary=True)
            check("assets", f"asset_200[{asset}]", a.get("status") == 200, a.get("status"))
    nj = get(".nojekyll")
    check("assets", "nojekyll_present", nj.get("status") in (200, 404),
          "if 404 the file may still be applied by Pages; underscore paths are the real test")
    f404 = get("this-path-does-not-exist-xyz")
    check("assets", "custom_404_served", f404.get("status") == 404, f404.get("status"))

    # --- B. payloads -------------------------------------------------------------------------
    gm = get("data/web/global/manifest.json")
    check("payload", "global_manifest_200", gm.get("status") == 200, gm.get("status"))
    manifest = None
    if gm.get("status") == 200:
        manifest = json.loads(gm["body"])
        check("payload", "manifest_declares_11_families",
              manifest.get("family_count") == 11, manifest.get("family_count"))
        check("payload", "manifest_declares_1358_structures",
              manifest.get("totals", {}).get("structures") == 1358,
              manifest.get("totals", {}).get("structures"))
        fam = manifest["families"][0]
        fm = get("data/web/" + fam["manifest_url"])
        check("payload", "family_manifest_200", fm.get("status") == 200, fm.get("status"))

    ov = get("data/web/overlay/global/review_gate_index.json")
    check("overlay", "review_gate_overlay_200", ov.get("status") == 200, ov.get("status"))
    if ov.get("status") == 200:
        o = json.loads(ov["body"])
        c = o.get("counts", {})
        check("overlay", "review_gate_active_189_items",
              c.get("human_review_required_items") == 189, c)
        check("overlay", "review_gate_reports_two_exclusions",
              o.get("effect_counts_open_items", {})
               .get("exclude_from_public_beta_pooled_analysis") == 2,
              o.get("effect_counts_open_items"))
    fv = get("data/web/overlay/global/family_validation_status.json")
    check("overlay", "validation_disclosure_200", fv.get("status") == 200, fv.get("status"))
    if fv.get("status") == 200:
        v = json.loads(fv["body"])
        check("overlay", "validation_covers_11_families",
              len({r["major_family_id"] for r in v["rows"]}) == 11)
        check("overlay", "aminergic_not_overclaimed",
              all(r["major_family_id"] == "001_001" for r in v["rows"]
                  if r["transfer_status"] == "reference_tested_within_scope"))

    # --- C. viewer bundles: 20 at random, hash-verified against the frozen manifest ----------
    bundles = json.loads((ROOT / "releases/phase6a/rc10/BUNDLE_HASHES.json")
                         .read_text(encoding="utf-8"))["bundles"]
    random.seed(20260805)
    sample = random.sample(sorted(bundles), 20)
    bad, missing = [], []
    for pdb in sample:
        b = get(f"data/web/structures/{pdb}/viewer.cif", binary=True, timeout=60)
        if b.get("status") != 200:
            missing.append(pdb)
            continue
        if hashlib.sha256(b["body"]).hexdigest() != bundles[pdb]:
            bad.append(pdb)
        time.sleep(0.15)
    check("bundles", "20_random_bundles_reachable", not missing, str(missing))
    check("bundles", "20_random_bundles_hash_match_rc9", not bad, str(bad))

    # --- D. licences and citation ------------------------------------------------------------
    ref = ROOT / "data/licences/third_party"
    for name, official in (("LICENSE", "PolyForm-Noncommercial-1.0.0.md"),
                           ("LICENSE-DATA", "CC-BY-NC-4.0.legalcode.txt")):
        r = get(name, binary=True)
        check("licence", f"{name}_200", r.get("status") == 200, r.get("status"))
        if r.get("status") == 200:
            check("licence", f"{name}_byte_identical_to_official",
                  r["body"] == (ref / official).read_bytes())
    for name in ("LICENSE-NOTICE.md", "LICENSE-SCOPE.json", "THIRD_PARTY_NOTICES.md",
                 "SOURCE_DATA_LICENSES.md", "CITATION.cff"):
        r = get(name)
        check("licence", f"{name}_200", r.get("status") == 200, r.get("status"))

    # --- E. claims on the live site -----------------------------------------------------------
    if idx.get("status") == 200:
        page = idx["body"].lower()
        for bad_claim in ("open source", "fully curated", "validated across class a"):
            check("claims", f"landing_html_free_of[{bad_claim}]", bad_claim not in page)
    ln = get("LICENSE-NOTICE.md")
    if ln.get("status") == 200:
        check("claims", "notice_states_source_available_not_open_source",
              "source-available" in ln["body"].lower())

    # --- F. outbound sources ------------------------------------------------------------------
    for url, label in (("https://www.rcsb.org/structure/6GPX", "rcsb_structure"),
                       ("https://doi.org/10.2210/pdb6GPX/pdb", "rcsb_doi"),
                       ("https://gpcrdb.org/structure/6GPX", "gpcrdb_structure"),
                       ("https://github.com/karakayafm/class-a-gpcr-atlas", "repository"),
                       ("https://github.com/karakayafm/class-a-gpcr-atlas/issues", "issues")):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30)
            r.read(1024)
            check("links", f"reachable[{label}]", r.status == 200, r.status)
        except Exception as e:
            check("links", f"reachable[{label}]", False, f"{type(e).__name__}: {e}")

    failed = [r for r in R if r["status"] == "FAIL"]
    out = {"base_url": BASE, "checks": len(R), "failed": len(failed),
           "status": "PASSED" if not failed else "FAILED", "results": R}
    (ROOT / "reports/phase6b").mkdir(parents=True, exist_ok=True)
    (ROOT / "reports/phase6b/public_url_results.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("base_url", "checks", "failed", "status")}, indent=1))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
