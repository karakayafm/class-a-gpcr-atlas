#!/usr/bin/env python3
"""Motif-centric index: which structures carry a core motif, and where they depart from it.

The family explorers answer "what is in this structure". This answers the other direction —
which structures carry a given motif position in its canonical form, which carry something else,
and how that varies between families and across Class A.

Two different questions live in this data and the payload keeps them apart, because conflating
them would report thermostabilising constructs as biology:

  * **Sequence variation.** Which residue a receptor naturally carries at a motif position. At
    3x39 that is serine in most Class A receptors, but alanine, threonine or glycine in others.
    This is the variation that means something for a receptor whose ligand is unknown.
  * **Engineered mutation.** Whether the deposited construct differs from that receptor's own
    wild type at the position — the Y5x58A of the thermostabilised turkey beta-1, for instance.
    Every non-canonical record in the source carries `mutation_flag`, so this is a property of
    the construct, not of the receptor.

Each structure is one string, one character per generic position, in the order `positions`
declares:

    uppercase   the receptor's wild-type residue at that position
    lowercase   the same, where the deposited construct carries a mutation there
    -           the position is expected but not resolved in the coordinates
    ?           generic numbering could not be resolved for it
    (space)     the position does not apply to this structure

The letter is always the wild type, so reading sequence variation off the payload never has to
account for construct engineering; the case says whether engineering is present.

    python3 pipeline/phase5/build_motif_search.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GPCRDB = ROOT / "data/raw/gpcrdb/receptor_residues.json"
RESIDUES = ROOT / "data/intermediate/phase4/motif_residues.jsonl"
STRUCTURES = ROOT / "data/intermediate/structures.normalized.jsonl"
# Written to the intermediate tree and emitted by build_payloads, which registers it in the
# manifest with its checksum like every other payload the loader verifies.
OUT = ROOT / "data/intermediate/phase5/motif_search.json"

AA3 = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
       "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
       "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V"}
UNRESOLVED, UNMAPPED, ABSENT = "-", "?", " "


def segment_of(position: str) -> str:
    """TM1–TM7 from a generic position; loop positions carry a two-part helix number."""
    head = position.split("x")[0]
    return "TM" + head if head.isdigit() and len(head) == 1 else head


def short(generic):
    """GPCRdb's combined form `5.42x43` carries both schemes; the pool keys on the second."""
    if not generic or "x" not in str(generic):
        return None
    return str(generic).split(".")[0] + "x" + str(generic).split("x")[1]


def positions_held(path, wanted):
    """Which of the pool's positions each receptor's own sequence actually has.

    The upstream residue table says `expected_but_unresolved` for a position it believes the
    receptor should have and the coordinates did not resolve. For a handful of positions that
    belief is wrong: forty-three rows, all at 6x30, name receptors whose TM6 starts at 6x31 or
    later and which therefore have no 6x30 to be missing. Encoded as unresolved, those receptors
    were reported as failing to cover a position they do not possess, which cost them coverage in
    every query that asked for it — the ionic lock among them. GPCRdb is the authority on which
    positions a receptor has, and the pocket and whole-receptor pools already ask it.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))["receptors"]
    held = {}
    for receptor, residues in payload.items():
        held[receptor] = {short(r.get("canonical_generic_number")) for r in residues} & wanted
    return held


def main() -> int:
    rows = [json.loads(line) for line in RESIDUES.read_text(encoding="utf-8").splitlines() if line.strip()]

    family_of, receptor_of, name_of = {}, {}, {}
    for line in STRUCTURES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        family = record.get("major_family_id")
        if not family:
            continue
        family_of[record["pdb_id"]] = "ca-" + family.replace("_", "-")
        receptor_of[record["pdb_id"]] = record.get("receptor_entry_name") or ""
        name_of[record["pdb_id"]] = record.get("receptor_name") or ""

    positions = sorted({r["generic_position"] for r in rows},
                       key=lambda p: (float(p.split("x")[0]), int(p.split("x")[1])))
    index = {p: i for i, p in enumerate(positions)}

    held = positions_held(GPCRDB, set(positions))

    motifs = collections.defaultdict(set)
    for row in rows:
        for motif in row["motif_memberships"]:
            motifs[motif].add(row["generic_position"])

    cells = collections.defaultdict(lambda: [ABSENT] * len(positions))
    # Sequence variation is counted once per receptor as well as once per structure: a receptor
    # solved eighty times would otherwise look like eighty independent observations of its own
    # residue, and the distribution would describe the deposition record rather than the family.
    wild_by_structure = collections.defaultdict(lambda: collections.Counter())
    wild_by_receptor = collections.defaultdict(lambda: collections.defaultdict(set))
    mutated = collections.defaultdict(lambda: collections.Counter())
    # What the construct actually carries where it was engineered. The cell alone says only that
    # the position is mutated, which leaves a reader unable to tell the wild type from the
    # substitution; both are needed to read the row.
    observed_mutation = collections.defaultdict(dict)
    resolution = collections.defaultdict(lambda: collections.Counter())
    for row in rows:
        pdb, position = row["pdb_id"], row["generic_position"]
        if pdb not in family_of:
            continue
        status = row["observation_status"]
        # A position the receptor does not have is not a position it is missing. The cell keeps the
        # default — not applicable — and the row is counted nowhere, including the denominator of
        # the engineered-mutation share, where it would otherwise dilute a real figure.
        if status == "expected_but_unresolved" and \
                position not in held.get(receptor_of[pdb], frozenset()):
            continue
        wild = row.get("wild_type_residue_identity")
        is_mutation = bool(row.get("mutation_flag"))
        if status.startswith("observed") and wild:
            char = wild.lower() if is_mutation else wild
        elif status == "expected_but_unresolved":
            char = UNRESOLVED
        else:
            char = UNMAPPED
        cells[pdb][index[position]] = char

        for scope in ("class_a", family_of[pdb]):
            resolution[(scope, position)][
                "observed" if status.startswith("observed") else "unresolved"] += 1
            if wild and status.startswith("observed"):
                wild_by_structure[(scope, position)][wild] += 1
                wild_by_receptor[(scope, position)][wild].add(receptor_of[pdb])
            if is_mutation:
                mutated[(scope, position)][AA3.get(row["residue_identity"], "X")] += 1
                observed_mutation[pdb][position] = AA3.get(row["residue_identity"], "X")

    variation, mutations = collections.defaultdict(dict), collections.defaultdict(dict)
    for (scope, position), counts in wild_by_structure.items():
        by_receptor = {aa: len(rs) for aa, rs in wild_by_receptor[(scope, position)].items()}
        receptors = sum(by_receptor.values())
        consensus = max(by_receptor.items(), key=lambda kv: kv[1])[0] if by_receptor else None
        variation[scope][position] = {
            "consensus": consensus,
            # Pairs, not an object: the payload writer sorts object keys, which would put these
            # back in alphabetical order and lose the ranking that makes the row readable.
            "by_structure": [[aa, n] for aa, n in counts.most_common()],
            "by_receptor": [[aa, n] for aa, n in sorted(by_receptor.items(),
                                                        key=lambda kv: (-kv[1], kv[0]))],
            "receptors": receptors,
            # Share of receptors carrying something other than the most common residue. This is
            # sequence variation between receptors, not a count of engineered constructs.
            "divergent_receptor_share": round(1 - by_receptor.get(consensus, 0) / receptors, 4)
                                        if receptors else 0.0,
        }
    for (scope, position), counts in mutated.items():
        seen = resolution[(scope, position)]
        total = seen["observed"] + seen["unresolved"]
        mutations[scope][position] = {
            "structures": sum(counts.values()),
            "residues": [[aa, n] for aa, n in counts.most_common()],
            "share": round(sum(counts.values()) / total, 4) if total else 0.0}

    payload = {
        "schema": "motif_search",
        "schema_version": "1.0.0",
        "encoding": ("One character per generic position, in the order of `positions`. The letter "
                     "is the receptor's wild-type residue there; lowercase means the deposited "
                     "construct carries a mutation at that position. '-': expected but unresolved. "
                     "'?': generic numbering unresolved. Space: not applicable."),
        "positions": positions,
        "segments": {p: segment_of(p) for p in positions},
        "motifs": [{"motif_id": motif, "positions": sorted(members, key=lambda p: index[p]),
                    "segments": sorted({segment_of(p) for p in members})}
                   for motif, members in sorted(motifs.items())],
        "variation": variation,
        "mutations": mutations,
        "structures": {pdb: dict({"f": family_of[pdb], "r": receptor_of[pdb],
                                  "n": name_of[pdb], "s": "".join(chars)},
                                 **({"m": observed_mutation[pdb]} if observed_mutation.get(pdb) else {}))
                       for pdb, chars in sorted(cells.items())},
        "structure_count": len(cells),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    print(json.dumps({"positions": len(positions), "motifs": len(motifs),
                      "structures": len(cells), "bytes": OUT.stat().st_size}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
