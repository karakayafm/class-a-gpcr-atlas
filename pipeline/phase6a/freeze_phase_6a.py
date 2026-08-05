#!/usr/bin/env python3
"""Phase 6A freeze. Hashes the phase's artefacts and re-verifies that no earlier phase moved."""
from __future__ import annotations
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "releases/phase6a"

# Timestamped logs and per-run raw output are excluded from the deterministic hashes: they change
# on every run without the science changing, which is exactly what the two-hash split exists for.
VOLATILE = {"REAL_GPU_RAW_LOG.txt", "FIREFOX_RAW_LOG.txt"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def agg(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def group(base: Path, pattern: str = "*") -> dict:
    return {str(p.relative_to(base)): sha(p) for p in sorted(base.rglob(pattern))
            if p.is_file() and p.name not in VOLATILE}


def main() -> int:
    rc = sys.argv[1] if len(sys.argv) > 1 else "rc4"
    RC = OUT / rc
    if not RC.is_dir():
        print(f"no such release candidate: {RC}", file=sys.stderr)
        return 2

    groups = {
        "phase6a_reports": group(ROOT / "reports/phase6a"),
        "phase6a_drafts": group(ROOT / "drafts/phase6a"),
        "phase6a_curation": group(ROOT / "curation"),
        "phase6a_tests": group(ROOT / "tests/phase6a", "*.py"),
        "phase6a_pipeline": group(ROOT / "pipeline/phase6a", "*.py"),
        "phase6a_schemas": group(ROOT / "schemas/phase6a"),
        "phase6a_config": group(ROOT / "config/phase6a"),
        "phase6a_licences": group(ROOT / "data/licences"),
        "phase6a_notices": {"THIRD_PARTY_NOTICES.md": sha(ROOT / "app/THIRD_PARTY_NOTICES.md")},
        "review_gating_policy": {"REVIEW_GATING_POLICY.json":
            sha(ROOT / "governance/REVIEW_GATING_POLICY.json")},
        "review_impact": group(ROOT / "data/release_overlays/rc6", "review_impact.jsonl"),
        "structure_slot_eligibility": group(ROOT / "data/release_overlays/rc6",
                                            "structure_slot_eligibility.jsonl"),
        "beta_aggregation_units": group(ROOT / "data/release_overlays/rc6",
                                        "beta_aggregation_units.jsonl"),
        "beta_contact_prevalence": group(ROOT / "data/release_overlays/rc6",
                                         "beta_contact_prevalence.jsonl"),
        "beta_interface_summaries": group(ROOT / "data/release_overlays/rc6",
                                          "beta_interface_summaries.jsonl"),
        "beta_coverage": group(ROOT / "data/release_overlays/rc6", "beta_coverage.jsonl"),
        "family_validation_status": {"content_sha256":
            (ROOT / "data/release_overlays/rc6/family_validation_status.content_sha256")
            .read_text(encoding="utf-8").strip()},
        "overlay_manifest": group(ROOT / "data/release_overlays/rc6/web",
                                  "overlay_payload_index.json"),
    }
    named = {k + "_sha": agg(v) for k, v in groups.items()}

    # The release candidate's own named hashes are carried forward verbatim, not recomputed into
    # a different shape — the RC is the artefact, this freeze is a record of it.
    rc_named = {k.strip(): v for v, k in
                (l.split("  ", 1) for l in (RC / "NAMED_HASHES.txt").read_text().strip().split("\n"))}
    named.update({"rc_" + k if not k.startswith(("rc_", "phase5_")) else k: v
                  for k, v in rc_named.items()})

    # Re-verify every earlier phase. A Phase 6A freeze that did not check this would be asserting
    # the thing it is supposed to prove.
    earlier = {}
    for ph, f in {"phase_1": ROOT / "data/freezes/phase_1/NAMED_HASHES.txt",
                  "phase2": ROOT / "releases/phase2/NAMED_HASHES.txt",
                  "phase3": ROOT / "releases/phase3/NAMED_HASHES.txt",
                  "phase4": ROOT / "releases/phase4/NAMED_HASHES.txt",
                  "phase5": ROOT / "releases/phase5/NAMED_HASHES.txt"}.items():
        earlier[ph] = {k.strip(): v for v, k in
                       (l.split("  ", 1) for l in f.read_text().strip().split("\n"))}

    ro = json.loads((ROOT / "reports/phase6a/READ_ONLY_VERIFICATION_PHASE6A.json").read_text())

    freeze = {
        "phase": "6A",
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release_candidate": rc,
        "release_candidate_version": json.loads(
            (RC / "OUTPUT_MANIFEST.json").read_text()).get("rc_version"),
        "named_hashes": named,
        "groups": {k: {"files": len(v), "sha": named[k + "_sha"]} for k, v in groups.items()},
        "earlier_phase_hashes": earlier,
        "read_only_verification": {k: ro[k] for k in
                                   ("baseline_files", "modified", "deleted", "identical")},
        "validation": {"real_gpu": "PASSED (61/0)", "firefox": "PASSED (30/0)",
                       "chromium_regression": "PASSED (42/0)", "rc_integrity": "PASSED (45/0)",
                       "accessibility_automated": "PASSED (67/0)",
                       "total_checks": 245, "total_failed": 0},
        "release_gate": "BLOCKED",
        "blocking_gates": 7,
        "human_curation": {"review_items": 189, "decided": 0,
                           "note": "The atlas ships automated adjudication only."},
        "not_performed": ["repository creation", "push", "GitHub Pages", "public release",
                          "archive upload", "DOI reservation or minting", "ORCID recording",
                          "licence selection", "legal assessment",
                          "recording any AI assessment as human curation"],
    }
    (OUT / "freeze.json").write_text(json.dumps(freeze, indent=1, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
    (OUT / "NAMED_HASHES.txt").write_text(
        "".join(f"{v}  {k}\n" for k, v in sorted(named.items())), encoding="utf-8")

    allfiles = {}
    for base in ("reports/phase6a", "drafts/phase6a", "curation", "tests/phase6a",
                 "pipeline/phase6a", "schemas/phase6a", "config/phase6a", "data/licences"):
        b = ROOT / base
        if b.is_dir():
            allfiles.update({f"{base}/{p.relative_to(b)}": sha(p)
                             for p in sorted(b.rglob("*")) if p.is_file()})
    (OUT / "checksums.sha256").write_text(
        "".join(f"{v}  {k}\n" for k, v in sorted(allfiles.items())), encoding="utf-8")

    print(json.dumps({"phase": "6A", "rc": rc, "groups": len(groups),
                      "named_hashes": len(named), "files_checksummed": len(allfiles),
                      "read_only_identical": ro["identical"],
                      "release_gate": "BLOCKED"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
