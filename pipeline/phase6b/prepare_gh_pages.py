#!/usr/bin/env python3
"""Phase 6B — prepare the gh-pages tree and run the deployment gates.

The gh-pages branch carries the deployed site and nothing else. Copying the research workspace
into a Pages branch is how private files become public, so this builds the tree by inclusion from
the staged site directory only.

Every stop condition in the phase brief is checked here, before anything is pushed. A gate that
runs after deployment is not a gate.
"""
from __future__ import annotations
import hashlib, json, re, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "releases/phase6b/public_repository"
PAGES = ROOT / "releases/phase6b/gh_pages"
REPORTS = ROOT / "reports/phase6b"

GB = 1_000_000_000
MIB_100 = 100 * 1024 * 1024
GIB_2 = 2 * 1024 * 1024 * 1024

# Patterns that must never reach a public tree.
SECRET_PATTERNS = [
    (r"gh[pousr]_[A-Za-z0-9]{16,}", "github token"),
    (r"github_pat_[A-Za-z0-9_]{20,}", "github fine-grained token"),
    (r"AKIA[0-9A-Z]{16}", "aws access key"),
    (r"-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----", "private key"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "slack token"),
    (r"(?i)\b(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]",
     "hardcoded credential"),
]
LOCAL_PATH_PATTERNS = [
    (r"/home/[a-z0-9_.-]+/", "local home directory"),
    (r"/media/[a-z0-9_.-]+/", "local mount path"),
    (r"[A-Z]:\\\\Users\\\\", "windows user path"),
    (r"/tmp/claude-[0-9]+", "local scratch path"),
]
TEXT_SUFFIX = {".md", ".json", ".js", ".css", ".html", ".txt", ".yml", ".yaml", ".py", ".cff",
               ".sh", ".gitignore"}
# The owner's own contact address is published deliberately; nothing else may be.
ALLOWED_EMAILS = {"edu.mfatih@gmail.com", "alexander.rose@weirdbyte.de",
                  "roman.bolzern@fhnw.ch"}

R: list[dict] = []


def check(group: str, name: str, ok: bool, detail=""):
    R.append({"group": group, "check": name, "status": "PASS" if ok else "FAIL",
              "detail": str(detail) if not ok else ""})
    if not ok:
        print(f"FAIL  {group} :: {name}  {detail}", file=sys.stderr)
    return ok


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def scan_text(base: Path, label: str) -> dict:
    """Secrets, local paths and stray addresses. Vendored third-party code is scanned for
    secrets but not for author emails, which legitimately appear in its licence headers."""
    secrets, paths, emails = [], [], set()
    email_re = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")
    for f in base.rglob("*"):
        if not f.is_file() or f.suffix not in TEXT_SUFFIX:
            continue
        rel = str(f.relative_to(base))
        if "/structures/" in "/" + rel:
            continue
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pat, what in SECRET_PATTERNS:
            if re.search(pat, t):
                secrets.append(f"{rel}: {what}")
        for pat, what in LOCAL_PATH_PATTERNS:
            if re.search(pat, t):
                paths.append(f"{rel}: {what}")
        emails.update(email_re.findall(t))
    return {"label": label, "secrets": secrets, "local_paths": paths,
            "emails": sorted(emails - ALLOWED_EMAILS)}


def measure(base: Path) -> dict:
    files = [f for f in base.rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    big = sorted(((f.stat().st_size, str(f.relative_to(base))) for f in files), reverse=True)[:5]
    return {"files": len(files), "bytes": total, "megabytes": round(total / 1e6, 1),
            "largest": [{"bytes": s, "path": p} for s, p in big]}


def main() -> int:
    if not PKG.is_dir():
        print("public_repository staging missing; run build_public_site.py first", file=sys.stderr)
        return 2

    # ---------------------------------------------------------------- gh-pages tree
    if PAGES.exists():
        shutil.rmtree(PAGES)
    shutil.copytree(PKG / "site", PAGES)

    # Licences and citation travel with the deployed site, not only with the repository.
    for f in ("LICENSE", "LICENSE-DATA", "LICENSE-NOTICE.md", "LICENSE-SCOPE.json",
              "THIRD_PARTY_NOTICES.md", "SOURCE_DATA_LICENSES.md", "CITATION.cff",
              "DATA_LICENSE.md"):
        src = PKG / f
        if src.exists():
            shutil.copy2(src, PAGES / f)

    (PAGES / ".nojekyll").write_text("", encoding="utf-8")

    # A 404 that keeps the deep-link router working: unknown paths land on the atlas rather
    # than on a dead end.
    (PAGES / "404.html").write_text("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Not found — Class A GPCR Contact Atlas</title>
<style>
 body{font:15px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;margin:0;padding:48px 20px;
      background:#f4f5f6;color:#1e2124}
 main{max-width:640px;margin:0 auto}
 a{color:#2f6f8f}
 @media (prefers-color-scheme:dark){body{background:#15171a;color:#e6e8ea}a{color:#69b3d6}}
</style>
</head>
<body>
<main>
<h1>Page not found</h1>
<p>That address is not part of this atlas.</p>
<p><a href="./">Go to the Class A GPCR Contact Atlas</a></p>
<p style="color:#5b6169;font-size:13px">
Bu adres bu atlasa ait değil. <a href="./">Atlasa dön</a>.
</p>
</main>
</body>
</html>
""", encoding="utf-8")

    # ---------------------------------------------------------------- size gates
    repo = measure(PKG)
    pages = measure(PAGES)
    bundles = measure(PKG / "site/data/web/structures")
    fam = measure(PKG / "site/data/web/families")
    offline_dir = ROOT / "releases/phase6a/rc10/offline_families"
    offline = measure(offline_dir) if offline_dir.is_dir() else {"bytes": 0, "files": 0}

    size = {"repository_working_tree": repo, "pages_site": pages,
            "viewer_bundles": bundles, "family_payloads": fam,
            "offline_family_exports": offline}

    check("size", "pages_site_under_1GB", pages["bytes"] < GB,
          f"{pages['megabytes']} MB")
    check("size", "repository_under_1GB", repo["bytes"] < GB, f"{repo['megabytes']} MB")
    biggest = max((f.stat().st_size for f in PKG.rglob("*") if f.is_file()), default=0)
    check("size", "no_file_over_100MiB", biggest < MIB_100, f"largest {biggest/1e6:.1f} MB")
    check("size", "initial_push_under_2GiB", repo["bytes"] < GIB_2, f"{repo['megabytes']} MB")
    # Offline exports would push the site over the limit; they belong in release assets.
    combined = pages["bytes"] + offline["bytes"]
    check("size", "offline_exports_correctly_excluded_from_pages",
          (PAGES / "offline_families").exists() is False,
          "offline exports must not be in the Pages tree")
    size["offline_in_pages_would_total_bytes"] = combined
    size["offline_in_pages_would_exceed_1GB"] = combined >= GB

    # No Git LFS pointers may be mistaken for content.
    lfs = []
    for f in PAGES.rglob("*"):
        if f.is_file() and f.stat().st_size < 200:
            try:
                head = f.read_text(encoding="utf-8", errors="ignore")[:80]
                if head.startswith("version https://git-lfs"):
                    lfs.append(str(f.relative_to(PAGES)))
            except Exception:
                pass
    check("size", "no_git_lfs_pointers_in_pages", not lfs, str(lfs[:3]))

    # ---------------------------------------------------------------- privacy gates
    s_repo = scan_text(PKG, "repository")
    s_pages = scan_text(PAGES, "pages")
    for s in (s_repo, s_pages):
        check("privacy", f"no_secrets[{s['label']}]", not s["secrets"], str(s["secrets"][:3]))
        check("privacy", f"no_local_paths[{s['label']}]", not s["local_paths"],
              str(s["local_paths"][:3]))
        check("privacy", f"no_unexpected_email[{s['label']}]", not s["emails"],
              str(s["emails"][:5]))

    for forbidden in ("_checksums_before.sha256", "OWNER_RELEASE_DECISION_FORM.md",
                      "RELEASE_DECISIONS_PENDING.json", "OWNER_DECISION_MATRIX.csv"):
        hits = [str(p.relative_to(PKG)) for p in PKG.rglob(forbidden)]
        check("privacy", f"private_artefact_excluded[{forbidden}]", not hits, str(hits))
    for d in ("data/cache", "data/raw", "curation/packets", "drafts", "tests"):
        check("privacy", f"private_tree_excluded[{d}]", not (PKG / d).exists())
    rcs = [p.name for p in PKG.rglob("rc[1-8]") if p.is_dir()]
    check("privacy", "superseded_release_candidates_excluded", not rcs, str(rcs))

    # ---------------------------------------------------------------- required files
    for f in ("README.md", "LICENSE", "LICENSE-DATA", "LICENSE-NOTICE.md", "LICENSE-SCOPE.json",
              "THIRD_PARTY_NOTICES.md", "SOURCE_DATA_LICENSES.md", "CITATION.cff", "AUTHORS.md",
              "PROJECT_GOVERNANCE.md", "DATA_PROVENANCE.md", "DATA_LICENSE.md", "CHANGELOG.md",
              "CONTRIBUTING.md", "SECURITY.md", ".gitignore"):
        check("files", f"present[{f}]", (PKG / f).exists())
    for f in (".nojekyll", "404.html", "index.html"):
        check("files", f"pages_has[{f}]", (PAGES / f).exists())

    # licence texts must still be byte-identical to the official ones
    ref = ROOT / "data/licences/third_party"
    for shipped, official in (("LICENSE", "PolyForm-Noncommercial-1.0.0.md"),
                              ("LICENSE-DATA", "CC-BY-NC-4.0.legalcode.txt")):
        for base, label in ((PKG, "repo"), (PAGES, "pages")):
            check("licence", f"text_unmodified[{label}/{shipped}]",
                  (base / shipped).read_bytes() == (ref / official).read_bytes())

    # ---------------------------------------------------------------- scientific integrity
    rc10 = {k.strip(): v for v, k in
           (l.split("  ", 1) for l in
            (ROOT / "releases/phase6a/rc10/NAMED_HASHES.txt").read_text().strip().split("\n"))}
    bundles_manifest = json.loads(
        (ROOT / "releases/phase6a/rc10/BUNDLE_HASHES.json").read_text(encoding="utf-8"))["bundles"]
    bad = []
    for pdb, h in bundles_manifest.items():
        p = PKG / "site/data/web/structures" / pdb / "viewer.cif"
        if not p.exists() or sha(p) != h:
            bad.append(pdb)
    check("science", "all_1358_viewer_bundles_match_rc10", not bad and len(bundles_manifest) == 1358,
          f"{len(bad)} mismatched of {len(bundles_manifest)}")
    gm = PKG / "site/data/web/global/manifest.json"
    check("science", "phase5_global_manifest_unchanged",
          sha(gm) == rc10["phase5_global_manifest_sha"], sha(gm)[:16])
    ov = PKG / "site/data/web/overlay/global/review_gate_index.json"
    check("science", "review_gate_overlay_present_in_public_site", ov.exists())
    if ov.exists():
        o = json.loads(ov.read_text(encoding="utf-8"))
        check("science", "review_gate_active",
              o.get("counts", {}).get("human_review_required_items") == 189,
              str(o.get("counts")))
    fv = PKG / "site/data/web/overlay/global/family_validation_status.json"
    check("science", "validation_disclosure_present_in_public_site", fv.exists())

    # ---------------------------------------------------------------- claim gates
    # Two document classes are meta-documents whose SUBJECT is the forbidden wording: the
    # language audit lists the phrases it searches for, and the licence reference texts are
    # third-party. Scanning them for the phrases they exist to discuss reports the safeguard as
    # the violation. Exempted by name, not by pattern, so the exemption stays visible.
    META_DOCS = {"docs/VALIDATION_LANGUAGE_AUDIT.md"}
    claim_files = [p for p in PKG.rglob("*") if p.is_file() and p.suffix in {".md", ".cff", ".yml"}
                   and "docs/licences" not in str(p)
                   and str(p.relative_to(PKG)) not in META_DOCS]
    FORBIDDEN = [("open source", "open source claim"), ("osi-approved", "OSI claim"),
                 ("fully curated", "curation claim"),
                 ("validated across class a", "validation claim"),
                 ("v1.0.0", "stable version claim")]
    NEGATORS = ("not", "never", "no", "cannot", "neither", "nor", "without", "instead",
                "rather than", "forbidden", "avoid", "must not", "değil", "yok", "yasak")
    bad_claims = []
    for f in claim_files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        # Strip markdown emphasis first: "**not** open source" must read as a negation, and it
        # does not if the asterisks are left glued to the negating word.
        t = re.sub(r"[*_`>#]", " ", raw).lower()
        t = re.sub(r"\s+", " ", t)
        for phrase, what in FORBIDDEN:
            for m in re.finditer(re.escape(phrase), t):
                ctx = t[max(0, m.start() - 120):m.start() + 80]
                words = set(re.findall(r"[a-zçğıöşü]+", ctx))
                if words & set(NEGATORS) or any(n in ctx for n in NEGATORS if " " in n):
                    continue
                # A quoted phrase in a "must not claim" list is a prohibition, not a claim.
                if f'"{phrase}"' in raw.lower() or f"'{phrase}'" in raw.lower():
                    continue
                bad_claims.append(f"{f.relative_to(PKG)}: {what} — …{ctx.strip()[:80]}…")
    check("claims", "no_unqualified_forbidden_claim", not bad_claims, str(bad_claims[:5]))

    beta_needed = ["189", "potency", "review"]
    rd = (PKG / "README.md").read_text(encoding="utf-8").lower()
    for w in beta_needed:
        check("claims", f"readme_states[{w}]", w in rd)

    failed = [r for r in R if r["status"] == "FAIL"]
    out = {"checks": len(R), "failed": len(failed),
           "status": "PASSED" if not failed else "FAILED",
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "size": size, "results": R}
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "gh_pages_preflight.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"checks": out["checks"], "failed": out["failed"], "status": out["status"],
                      "repo_MB": repo["megabytes"], "pages_MB": pages["megabytes"],
                      "largest_file_MB": round(biggest / 1e6, 2)}, indent=1))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
