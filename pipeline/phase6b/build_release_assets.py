#!/usr/bin/env python3
"""Package the per-family offline exports as release assets.

One zip per family, holding the family's self-contained copy of the atlas, so a reader can work
without the site. Archives are written deterministically — entries sorted, timestamps fixed — so
rebuilding the same export twice produces the same bytes and the recorded checksum means
something.

    python3 pipeline/phase6b/build_release_assets.py --version 0.1.0-beta.2
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "releases/phase5/offline_families"
OUT = ROOT / "releases/phase6b/release_assets"
MANIFEST = ROOT / "releases/phase6b/RELEASE_ASSET_MANIFEST.json"
LANDING = ROOT / "data/web/global/landing.json"
# Fixed timestamp for every entry: the archive describes a release, not the moment it was zipped.
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def family_names() -> dict[str, str]:
    landing = json.loads(LANDING.read_text(encoding="utf-8"))
    return {row["family_slug"]: row["family_name"] for row in landing.get("families", [])}


def write_archive(source: Path, target: Path) -> None:
    files = sorted(p for p in source.rglob("*") if p.is_file())
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            info = zipfile.ZipInfo(str(Path(source.name) / path.relative_to(source)), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    args = ap.parse_args()

    if not EXPORTS.is_dir():
        raise SystemExit("offline exports missing; run pipeline/phase5/build_site.py")
    names = family_names()
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.zip"):
        stale.unlink()

    assets = []
    for source in sorted(p for p in EXPORTS.iterdir() if p.is_dir()):
        target = OUT / f"class-a-gpcr-atlas-{args.version}-offline-{source.name}.zip"
        write_archive(source, target)
        assets.append({
            "file": target.name,
            "family_slug": source.name,
            "family_name": names.get(source.name, source.name),
            "export_type": "offline_family_export",
            "version": args.version,
            "bytes": target.stat().st_size,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        })

    manifest = {"version": args.version, "asset_count": len(assets),
                "total_bytes": sum(a["bytes"] for a in assets), "assets": assets}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"version": args.version, "assets": len(assets),
                      "total_mb": round(manifest["total_bytes"] / 1e6, 1)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
