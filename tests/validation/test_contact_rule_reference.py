#!/usr/bin/env python3
"""Compare the computed contact shell against the residues the primary papers state.

This is the test DD-07 asks for. It reads `curation/contact_rule_reference.csv`, where a reader
has written, per sampled structure, the residues the paper states as the binding site or
interface, and reports agreement per cell.

It scores nothing it was not given. Rows whose `paper_residues` column is empty are reported as
outstanding, not passed, and a worksheet with no filled rows reports SKIPPED — a test that
announces success over an empty sample is worse than no test.

    python3 tests/validation/test_contact_rule_reference.py
"""
from __future__ import annotations

import collections
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKSHEET = ROOT / "curation/contact_rule_reference.csv"
# A paper naming most of the shell but not every peripheral residue is agreement, not failure;
# papers state the residues they discuss. Recall below this is what deserves a look.
RECALL_FLOOR = 0.70

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail and not ok else ""))
    if not ok:
        failures.append(name)


def numbers(text: str) -> set[int]:
    """Residue numbers from either column.

    Accepts `ASP114`, `D114`, `114`, `Asp114(3.32x32)` and comma or space separated lists. The
    generic number in parentheses is ignored: the two columns are compared on author numbering,
    which is what a paper states.
    """
    out = set()
    for token in re.split(r"[\s,;]+", text or ""):
        token = re.sub(r"\(.*?\)", "", token).strip()
        if not token:
            continue
        found = re.search(r"(-?\d+)", token)
        if found:
            out.add(int(found.group(1)))
    return out


def main() -> int:
    print("Contact rule reference test")

    if not WORKSHEET.is_file():
        print("  SKIPPED  no worksheet at %s" % WORKSHEET.relative_to(ROOT))
        print("           run pipeline/validation/build_contact_rule_worksheet.py")
        return 0

    rows = list(csv.DictReader(WORKSHEET.open(encoding="utf-8")))
    check("worksheet has rows", bool(rows), str(len(rows)))
    if not rows:
        return 1 if failures else 0

    filled = [r for r in rows if (r.get("paper_residues") or "").strip()]
    stated_no = [r for r in rows
                 if (r.get("paper_states_residues") or "").strip().lower() == "no"]
    outstanding = [r for r in rows if r not in filled and r not in stated_no]

    if not filled:
        print("  SKIPPED  no row carries paper residues yet")
        print("           %d of %d rows outstanding; %d marked as stating none"
              % (len(outstanding), len(rows), len(stated_no)))
        print()
        print("contact rule reference: not yet testable")
        return 0

    per_cell = collections.defaultdict(lambda: {"rows": 0, "recall": [], "missed": 0})
    for row in filled:
        atlas = numbers(row.get("atlas_residues", ""))
        paper = numbers(row.get("paper_residues", ""))
        if not paper:
            continue
        agreed = atlas & paper
        recall = len(agreed) / len(paper)
        cell = per_cell[(row["site_class"], row["family"])]
        cell["rows"] += 1
        cell["recall"].append(recall)
        cell["missed"] += len(paper - atlas)
        check("%s: shell contains the residues %s states" % (row["pdb_id"], row["doi"] or "the paper"),
              recall >= RECALL_FLOOR,
              "recall %.0f%%, missing %s" % (100 * recall, sorted(paper - atlas)))

    print()
    print("  Per cell")
    for (site_class, family), cell in sorted(per_cell.items()):
        mean = sum(cell["recall"]) / len(cell["recall"])
        print("    %-34s %-12s rows %d  mean recall %.0f%%  residues missed %d"
              % (site_class, family, cell["rows"], 100 * mean, cell["missed"]))

    print()
    print("  %d of %d rows carry paper residues; %d state none; %d outstanding"
          % (len(filled), len(rows), len(stated_no), len(outstanding)))
    if failures:
        print("total %d checks, %d failed" % (len(rows) + 1, len(failures)))
        return 1
    print("contact rule reference: all filled rows agree within the floor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
