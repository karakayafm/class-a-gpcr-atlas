#!/usr/bin/env python3
"""Phase 3B — GPCRdb generic numbering for every receptor that has a structure."""
from __future__ import annotations
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.canonical import write_json          # noqa: E402
from common.http import Fetcher, utc_now         # noqa: E402

BASE = "https://gpcrdb.org/services/residues/extended/{entry}/"

def main() -> int:
    S = [json.loads(l) for l in (ROOT / "data/intermediate/structures.normalized.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]
    entries = sorted({s["receptor_entry_name"] for s in S if s["receptor_entry_name"]})
    f = Fetcher(ROOT / "data/cache/gpcrdb_residues", "GPCRdb", timeout=120, retries=3,
                delay=0.0, refresh=False)
    def get(e):
        return e, f.get_json(BASE.format(entry=e), f"residues_{e}")
    out, failed = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for e, d in pool.map(get, entries):
            if d is None:
                failed.append(e); continue
            out[e] = [{"sequence_number": r["sequence_number"], "amino_acid": r["amino_acid"],
                       "protein_segment": r.get("protein_segment"),
                       "display_generic_number": r.get("display_generic_number"),
                       "canonical_generic_number": next(
                           (a["label"] for a in (r.get("alternative_generic_numbers") or [])
                            if a.get("scheme") == "GPCRdb(A)"), None)}
                      for r in d]
    art = write_json(ROOT / "data/raw/gpcrdb/receptor_residues.json", {
        "generated_at": utc_now(), "source": BASE,
        "licence": "GPCRdb data: CC BY 4.0",
        "counts": {"receptors_requested": len(entries), "receptors_returned": len(out),
                   "failed": len(failed),
                   "residues": sum(len(v) for v in out.values()),
                   "residues_with_generic_number":
                       sum(1 for v in out.values() for r in v if r["display_generic_number"])},
        "failed_entries": sorted(failed), "receptors": out})
    print(json.dumps({"receptors": len(out), "failed": len(failed),
                      "residues": sum(len(v) for v in out.values()),
                      "sha": art["content_sha256"][:16]}, indent=1))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
