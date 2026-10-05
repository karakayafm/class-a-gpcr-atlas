#!/usr/bin/env python3
"""Register the search indices and the affinity file in global/manifest.json.

build_payloads.py lists every global file it writes itself, and the loader refuses a global file
the manifest does not list - loadGlobalChecked() raises a schema error, which the page shows as
"schema version mismatch". The four search indices and the affinity side file are written after
that manifest, by scripts of their own, so they have to be added to it here or the Find motif,
Contact map and search pages fail on a build where the files are in fact present.

    python3 pipeline/phase5/register_side_files.py [--web data/web]

The manifest is rewritten with the same serialisation build_payloads.py uses, so a rebuild stays
byte-identical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIDE_FILES = ["receptor_search.json", "pocket_search.json", "generic_numbering.json",
              "supersessions.json", "binding_affinity.json"]


def dumps(obj) -> str:
    """The serialisation build_payloads.wj() uses."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--web", type=Path, default=ROOT / "data/web")
    args = ap.parse_args()
    args.web = args.web.resolve()      # --web may be given relative to the working directory

    manifest_path = args.web / "global/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.setdefault("global_files", {})

    added, missing = [], []
    for name in SIDE_FILES:
        path = args.web / "global" / name
        if not path.is_file():
            missing.append(name)
            continue
        raw = path.read_bytes()
        entry = {"url": "global/" + name, "bytes": len(raw),
                 "sha256": hashlib.sha256(raw).hexdigest()}
        if entries.get(name) != entry:
            entries[name] = entry
            added.append(name)

    if missing:
        print("missing, not registered: " + ", ".join(missing))
        return 1

    manifest_path.write_text(dumps(manifest), encoding="utf-8")
    print(f"registered {len(SIDE_FILES)} side file(s) in {manifest_path.relative_to(ROOT)}"
          f"{'; updated: ' + ', '.join(added) if added else '; already current'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
