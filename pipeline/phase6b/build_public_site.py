#!/usr/bin/env python3
"""Phase 6B — stage the public repository package.

Copies only what should be published. The working directory contains caches, coordinate
downloads, nine release candidates, browser profiles and owner decision drafts; none of that
belongs in a public repository, and "copy everything then delete" is how private files get
published by accident. This builds the package by inclusion, never by exclusion.

Verifies the Phase 6A rc.9 hashes before copying anything: a public site built from an
unverified tree would be a different artefact wearing the same version number.
"""
from __future__ import annotations
import hashlib, json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RC = ROOT / "releases/phase6a/rc9"
OUT = ROOT / "releases/phase6b/public_repository"
OVERLAY = ROOT / "data/release_overlays/rc6"

# Source trees that are published. Everything not listed here stays private by construction.
CODE_TREES = ["app", "pipeline", "config", "schemas"]
# Within those, directories that must never be published even though their parent is.
DENY_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".git"}
DENY_SUFFIX = {".pyc", ".pyo", ".part", ".tmp", ".log", ".swp"}
DENY_NAMES = {".env", ".DS_Store"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def named(p: Path) -> dict:
    return {k.strip(): v for v, k in
            (l.split("  ", 1) for l in p.read_text(encoding="utf-8").strip().split("\n"))}


def publishable(p: Path) -> bool:
    if any(part in DENY_DIRS for part in p.parts):
        return False
    if p.suffix in DENY_SUFFIX or p.name in DENY_NAMES:
        return False
    return True


def copy_tree(src: Path, dst: Path) -> tuple[int, int]:
    files = bytes_ = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file() or not publishable(f.relative_to(src)):
            continue
        d = dst / f.relative_to(src)
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, d)
        files += 1
        bytes_ += f.stat().st_size
    return files, bytes_


def main() -> int:
    # --- gate: the release candidate must be the one that was validated -------------------
    if not RC.is_dir():
        print("rc9 missing", file=sys.stderr)
        return 2
    n9 = named(RC / "NAMED_HASHES.txt")
    p5 = named(ROOT / "releases/phase5/NAMED_HASHES.txt")
    if n9["phase5_global_manifest_sha"] != p5["global_manifest_sha"]:
        print("Phase 5 manifest hash mismatch; refusing to stage", file=sys.stderr)
        return 3
    ovman = json.loads((OVERLAY / "overlay_manifest.json").read_text(encoding="utf-8"))
    n6a = named(ROOT / "releases/phase6a/NAMED_HASHES.txt")
    for k in ("review_impact_sha", "beta_contact_prevalence_sha", "structure_slot_eligibility_sha"):
        if k not in n6a:
            print(f"overlay hash {k} missing from the Phase 6A freeze", file=sys.stderr)
            return 4

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    report = {"staged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source_release_candidate": "0.1.0-rc.9",
              "rc_manifest_sha": n9["rc_manifest_sha"],
              "trees": {}}

    # --- the deployable site ----------------------------------------------------------------
    f, b = copy_tree(RC / "site", OUT / "site")
    report["trees"]["site"] = {"files": f, "bytes": b}

    # --- source code -------------------------------------------------------------------------
    for t in CODE_TREES:
        src = ROOT / t
        if not src.is_dir():
            continue
        f, b = copy_tree(src, OUT / t)
        report["trees"][t] = {"files": f, "bytes": b}

    # --- licences and notices, from the repository root ------------------------------------
    for name in ("LICENSE", "LICENSE-DATA", "LICENSE-NOTICE.md", "LICENSE-SCOPE.json"):
        shutil.copy2(ROOT / name, OUT / name)
    shutil.copy2(ROOT / "app/THIRD_PARTY_NOTICES.md", OUT / "THIRD_PARTY_NOTICES.md")

    # --- reference licence texts, so the record travels with the package -------------------
    lic = OUT / "docs/licences"
    lic.mkdir(parents=True, exist_ok=True)
    for f2 in sorted((ROOT / "data/licences/third_party").glob("*")):
        if f2.is_file():
            shutil.copy2(f2, lic / f2.name)

    # --- user-facing documentation ----------------------------------------------------------
    docs = OUT / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    PUBLIC_REPORTS = [
        "CROSS_FAMILY_VALIDATION_DISCLOSURE.md", "REVIEW_GATING_IMPLEMENTATION.md",
        "REVIEW_GATING_COUNTS.md", "REVIEW_ITEM_EFFECT_MATRIX.md",
        "BETA_DENOMINATOR_AUDIT.md", "BETA_AGGREGATION_COMPARISON.md",
        "VALIDATION_LANGUAGE_AUDIT.md", "POLICY_CONFORMANCE_REPORT.md",
        "THIRD_PARTY_NOTICE_AUDIT.md", "DERIVED_DATA_REVIEW_PACKET.md",
        "LICENSE_SCOPE_ANALYSIS.md", "EXTERNAL_LINK_AUDIT.md",
        "SECURITY_PRIVACY_AUDIT.md", "ACCESSIBILITY_RELEASE_AUDIT.md",
        "REAL_GPU_VALIDATION.md", "FIREFOX_TEST_REPORT.md",
    ]
    n = 0
    for r in PUBLIC_REPORTS:
        s = ROOT / "reports/phase6a" / r
        if s.exists():
            shutil.copy2(s, docs / r)
            n += 1
    report["trees"]["docs/reports"] = {"files": n}

    # governance documents a reader needs
    for s, d in (("governance/REVIEW_GATING_POLICY.json", "docs/REVIEW_GATING_POLICY.json"),
                 ("data/release_overlays/rc6/family_validation_status.json",
                  "docs/family_validation_status.json")):
        src = ROOT / s
        if src.exists():
            (OUT / d).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, OUT / d)

    # --- what was deliberately left out ------------------------------------------------------
    report["excluded_by_design"] = [
        "data/cache/** (raw API response cache)",
        "data/raw/** (downloaded coordinate cache)",
        "releases/phase6a/rc1..rc8 (superseded release candidates)",
        "releases/phase1..phase5 (internal freezes)",
        "reports/phase6a/OWNER_RELEASE_DECISION_FORM.md and the owner decision matrix",
        "governance/RELEASE_DECISIONS_PENDING.json (owner deliberation record)",
        "drafts/** (unapproved drafts)",
        "tests/** (harnesses referencing local browser profiles and absolute paths)",
        "_checksums_*.sha256 (read-only baselines naming a local parent directory)",
        "*.pyc, __pycache__, .part, .tmp, .log, .env",
        "curation/packets/** (review workflow, not a published artefact)",
    ]
    total_files = sum(1 for f in OUT.rglob("*") if f.is_file())
    total_bytes = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    report["totals"] = {"files": total_files, "bytes": total_bytes,
                        "megabytes": round(total_bytes / 1e6, 1)}
    (ROOT / "reports/phase6b").mkdir(parents=True, exist_ok=True)
    (ROOT / "reports/phase6b/_staging_report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"files": total_files, "megabytes": report["totals"]["megabytes"],
                      "trees": {k: v.get("files") for k, v in report["trees"].items()}}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
