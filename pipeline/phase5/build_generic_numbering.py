#!/usr/bin/env python3
"""Ballesteros-Weinstein numbers for the positions the panels ask about.

The atlas labels a position with GPCRdb's structure-based number — the part after the `x` in
GPCRdb's own combined form, so `5.42x43` is stored as `5x43`. The literature, and anyone typing a
position from memory, uses Ballesteros-Weinstein: the part before the `x`. The two agree in most
of the helix bundle and part company wherever a helix carries a bulge, which is not a rare corner:
one of them is the catechol serine every aminergic paper names as 5.42.

Left alone, that is a silent error. A reader asking for `5x42S` gets BW 5.41 — alanine in the
beta-2 adrenoceptor — and nothing on screen says so.

This writes the correspondence out so the panel can show both schemes and accept either. It is a
side file rather than an edit to the payloads: `motif_search.json` is a frozen artefact and is not
regenerated to carry a label.

The correspondence is *not* one number per position. Bulges differ between receptors, so a
structure-based position can sit at different BW numbers in different receptors. Where that
happens the file carries the most common value, how many receptors it holds for, and the
variants — never a single number that would be wrong for a minority nobody counted.

    python3 pipeline/phase5/build_generic_numbering.py
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def short(generic: str | None) -> str | None:
    if not generic or "." not in generic or "x" not in generic:
        return generic
    return generic.split(".")[0] + "x" + generic.split("x")[1]


def bw_of(display: str | None) -> str | None:
    return display.split("x")[0] if display and "x" in display else None


def position_sort_key(position: str):
    m = re.match(r"^(\d+)x(\d+)$", position)
    return (float(m.group(1)), int(m.group(2))) if m else (99.0, 9999)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpcrdb", type=Path,
                        default=ROOT / "data/raw/gpcrdb/receptor_residues.json")
    parser.add_argument("--payloads", type=Path, nargs="*",
                        default=[ROOT / "site/data/web/global/motif_search.json",
                                 ROOT / "site/data/web/global/pocket_search.json"])
    parser.add_argument("--out", type=Path,
                        default=ROOT / "site/data/web/global/generic_numbering.json")
    args = parser.parse_args()

    wanted = set()
    for path in args.payloads:
        if path.is_file():
            wanted |= set(json.loads(path.read_text(encoding="utf-8"))["positions"])

    receptors = json.loads(args.gpcrdb.read_text(encoding="utf-8"))["receptors"]
    seen = collections.defaultdict(collections.Counter)
    for rows in receptors.values():
        for row in rows:
            position = short(row.get("canonical_generic_number"))
            bw = bw_of(row.get("display_generic_number"))
            if position in wanted and bw:
                seen[position][bw] += 1

    positions, index = {}, {}
    bw_to_position = collections.defaultdict(collections.Counter)
    for position, counts in seen.items():
        for bw, n in counts.items():
            bw_to_position[bw][position] += n
    for position, counts in seen.items():
        modal, held = counts.most_common(1)[0]
        total = sum(counts.values())
        # Divergence is a property of the labels, not of the receptor: the two schemes name the
        # same residue differently. Flagged so the panel can mark it rather than let a reader
        # assume the number they know is the number on screen.
        diverges = modal.split(".")[-1] != position.split("x")[1]
        positions[position] = {
            "bw": modal,
            "display": modal + "x" + position.split("x")[1],
            "receptors": held,
            "total": total,
            "variable": len(counts) > 1,
            "diverges": diverges,
            # The share of receptors the modal number is *wrong* for. A position can agree with
            # Ballesteros-Weinstein in the majority and still disagree in half the receptors —
            # 4x63 is 4.63 in 96 of 190 and 4.64 in the rest — and a reader told only about the
            # modal value would have no way to know.
            "minority": round((total - held) / total, 4) if total else 0.0,
            "variants": [[bw, n] for bw, n in counts.most_common()[1:]],
        }
        # For the parser: a BW number a reader types resolves to the structure-based position it
        # is the most common label of. Where two positions claim the same BW number, the one it
        # holds for more receptors wins.
        if modal not in index or held > seen[index[modal]][modal]:
            index[modal] = position

    payload = {
        "schema": "generic_numbering",
        "schema_version": "1.0.0",
        "source": "GPCRdb display_generic_number (Ballesteros-Weinstein x structure-based)",
        "note": ("Positions are keyed by GPCRdb structure-based number, the form the payloads use. "
                 "`bw` is the most common Ballesteros-Weinstein number for that position across "
                 "receptors; where `variable` is true the mapping is not the same in every "
                 "receptor and `variants` lists the rest. `diverges` marks the positions where "
                 "the two schemes disagree."),
        "counts": {
            "positions": len(positions),
            "variable": sum(1 for p in positions.values() if p["variable"]),
            "diverging": sum(1 for p in positions.values() if p["diverges"]),
            "minority_over_5pct": sum(1 for p in positions.values() if p["minority"] > 0.05),
            "flagged": sum(1 for p in positions.values()
                           if p["diverges"] or p["minority"] > 0.05),
            "ambiguous_bw": sum(1 for bw, c in bw_to_position.items() if len(c) > 1),
        },
        "positions": {p: positions[p] for p in sorted(positions, key=position_sort_key)},
        "bw_index": index,
        # The ambiguity in the other direction. A BW number a reader types can name more than one
        # structure-based position — 4.58 is 4x58 in 106 receptors and 4x59 in 94 — so the parser
        # cannot resolve it silently and be honest about it. Listed most-common first.
        "bw_alternatives": {bw: [[p, n] for p, n in c.most_common()]
                            for bw, c in bw_to_position.items() if len(c) > 1},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")), encoding="utf-8")
    print("wrote %s (%d positions, %d variable, %d diverging)"
          % (args.out, len(positions), payload["counts"]["variable"],
             payload["counts"]["diverging"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
