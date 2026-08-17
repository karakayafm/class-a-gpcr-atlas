#!/usr/bin/env python3
"""Whole-receptor index: every generic position, in the shape the other two pools already use.

The panel could ask about twenty-one microswitch positions and about the two hundred and thirty a
ligand touches. Both are answers to "where is the interesting part", chosen by the pipeline. A
reader who wants the run 3x32-3x37 along TM3, or anything else the two pools happen to exclude,
had nowhere to ask.

This is the pool with no such choice in it: every position GPCRdb defines a structure-based number
for, across the receptors the atlas covers. Which of them is worth reading is then a runtime
decision, made against `coverage` — the share of receptors that have the position at all — because
the far end of that distribution is real but thin: a bulge position such as 5x461 exists in a
minority of receptors, and a panel that showed it beside 3x50 without saying so would invite a
reader to compare a near-universal position with a rare one as though they were the same kind of
thing.

Everything except the pool and its metadata is imported from `build_pocket_search`, deliberately.
The encoding is load-bearing — uppercase is the receptor's wild type, lowercase means the deposited
construct carries a mutation there, `-` is expected-but-unresolved, `?` is numbering unresolved and
a space is not-applicable — and a second implementation of it would be a second thing to get wrong.

    python3 pipeline/phase5/build_receptor_search.py \
        --contacts site/data/web/structures \
        --mapping  ../class_a_gpcr_atlas/data/intermediate/phase3/receptor_residue_mapping.jsonl \
        --gpcrdb   ../class_a_gpcr_atlas/data/raw/gpcrdb/receptor_residues.json \
        --validate site/data/web/global/motif_search.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_pocket_search as P                                     # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def build_pool(gpcrdb_path: Path):
    """Every structure-based position GPCRdb numbers, with how many receptors carry it."""
    receptors = json.loads(gpcrdb_path.read_text(encoding="utf-8"))["receptors"]
    coverage = collections.Counter()
    segments: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for rows in receptors.values():
        seen = set()
        for row in rows:
            position = P.short(row.get("canonical_generic_number"))
            if not position:
                continue
            if row.get("protein_segment"):
                segments[position][row["protein_segment"]] += 1
            if position not in seen:
                seen.add(position)
                coverage[position] += 1
    total = len(receptors) or 1
    pool = sorted(coverage, key=P.position_sort_key)
    # The modal segment, not the first one seen: a position at a helix boundary is assigned
    # differently in different receptors, and the majority is the honest single answer.
    modal_segment = {p: c.most_common(1)[0][0] for p, c in segments.items()}
    return pool, {p: round(coverage[p] / total, 4) for p in pool}, modal_segment, total


def build_groups(pool_set, scan, segments, motif_reference):
    """Cards a reader can actually use.

    Not the per-segment groups the pocket pool derives: a card holding all forty-seven positions
    of TM5 writes a query nobody asked. Two kinds are offered instead — the named microswitch
    motifs, taken from the payload that defines them rather than restated here, and the per-class
    consensus sets, which are the same rule the pocket pool uses.
    """
    groups = []
    for motif in (motif_reference or {}).get("motifs", []):
        positions = [p for p in motif.get("positions", []) if p in pool_set]
        if len(positions) < 2:
            continue
        groups.append(dict(motif, positions=positions,
                           segments=sorted({segments.get(p, "") for p in positions} - {""}),
                           rule=motif.get("rule") or "named microswitch motif"))
    for site_class, positions in scan["contact_receptors"].items():
        denominator = len(scan["receptors_in_class"][site_class]) or 1
        consensus = sorted((p for p, rs in positions.items()
                            if p in pool_set and len(rs) / denominator > 0.50),
                           key=P.position_sort_key)
        if len(consensus) < 2:
            continue
        groups.append({
            "motif_id": "consensus_" + site_class,
            "positions": consensus,
            "segments": sorted({segments.get(p, "") for p in consensus} - {""}),
            "site_class": site_class,
            "rule": "contacts a ligand in more than 50% of the receptors of " + site_class})
    return groups


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contacts", type=Path, default=ROOT / "site/data/web/structures")
    parser.add_argument("--mapping", type=Path,
                        default=ROOT.parent / "class_a_gpcr_atlas/data/intermediate/phase3/"
                                              "receptor_residue_mapping.jsonl")
    parser.add_argument("--gpcrdb", type=Path,
                        default=ROOT.parent / "class_a_gpcr_atlas/data/raw/gpcrdb/"
                                              "receptor_residues.json")
    parser.add_argument("--families", type=Path, default=ROOT / "site/data/web/families")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "site/data/web/global/receptor_search.json")
    parser.add_argument("--cutoff", type=float, default=4.5)
    parser.add_argument("--validate", type=Path, default=None,
                        help="motif_search.json to reproduce on the positions the two share")
    args = parser.parse_args()

    pool, coverage, segments, receptor_total = build_pool(args.gpcrdb)
    pool_set = set(pool)
    print("pool: %d positions over %d receptors" % (len(pool), receptor_total), file=sys.stderr)

    scan = P.scan_contacts(args.contacts, args.cutoff)

    family_of, receptor_family = {}, {}
    for path in sorted(args.families.glob("*/receptors.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        slug = "ca-" + data["family_id"].replace("_", "-")
        for receptor in data["receptors"]:
            receptor_family[receptor["receptor_entry_name"]] = slug
    mapping_status = {}
    for path in sorted(args.families.glob("*/structures.json")):
        for record in json.loads(path.read_text(encoding="utf-8"))["structures"]:
            mapping_status[record["pdb_id"]] = record.get("generic_mapping_status")
    names = {}
    for path in sorted(args.contacts.glob("*/viewer_meta.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        pdb = meta.get("pdb_id") or path.parent.name
        slug = receptor_family.get(meta.get("receptor_entry_name") or "")
        if slug:
            family_of[pdb] = slug
        names[pdb] = meta.get("receptor_name") or ""

    wild_type, by_uniprot = P.load_wild_type(args.gpcrdb, pool_set)
    bw_of = P.load_bw(args.gpcrdb, pool_set)
    observed, unresolved = P.read_mapping(args.mapping, pool_set, scan["receptor_of"], by_uniprot)
    structures = sorted(family_of)
    cells, mutations = P.encode(pool, structures, wild_type, observed, unresolved,
                                scan["receptor_of"], mapping_status)
    index = {p: i for i, p in enumerate(pool)}

    reference = json.loads(args.validate.read_text(encoding="utf-8")) if args.validate else None
    if reference:
        # The whole-receptor pool contains the microswitch pool, so every cell the two share must
        # agree. If it does not, this payload is wrong and says so before anyone reads it.
        shared = [p for p in reference["positions"] if p in index]
        ref_index = {p: i for i, p in enumerate(reference["positions"])}
        checked = mismatched = 0
        examples = []
        for pdb, record in reference["structures"].items():
            if pdb not in cells:
                continue
            for position in shared:
                checked += 1
                theirs, ours = record["s"][ref_index[position]], cells[pdb][index[position]]
                if theirs != ours:
                    mismatched += 1
                    if len(examples) < 8:
                        examples.append("%s %s: motif=%r receptor=%r" % (pdb, position, theirs, ours))
        print("validate: %d cells over %d shared positions, %d differ"
              % (checked, len(shared), mismatched), file=sys.stderr)
        for line in examples:
            print("   " + line, file=sys.stderr)

    variation = P.build_variation(pool, structures, cells, scan["receptor_of"], family_of, index)
    mutation_summary = P.build_mutation_summary(pool, structures, cells, mutations, family_of, index)

    class_receptors = {c: len(rs) for c, rs in scan["receptors_in_class"].items()}
    position_meta = {}
    for position in pool:
        frequency, receptors = {}, {}
        for site_class, positions in scan["contact_receptors"].items():
            hit = len(positions.get(position, ()))
            if hit:
                frequency[site_class] = round(hit / (class_receptors.get(site_class) or 1), 4)
                receptors[site_class] = hit
        pairs = (variation.get("class_a", {}).get(position, {}) or {}).get("by_receptor", [])
        position_meta[position] = {
            "segment": segments.get(position, scan["segments"].get(position, "")),
            # What this pool is filtered on: how many receptors have the position at all. The
            # contact frequencies are kept beside it because they still say something useful —
            # whether a position is in anyone's pocket — but they are not the threshold here.
            "coverage": coverage[position],
            "coverage_receptors": round(coverage[position] * receptor_total),
            "frequency": frequency,
            "receptors": receptors,
            "entropy": P.entropy_of(pairs),
            "bw": bw_of.get(position),
        }

    payload = {
        "schema": "motif_search",
        "schema_version": "1.0.0",
        "encoding": ("One character per generic position, in the order of `positions`. The letter "
                     "is the receptor's wild-type residue there; lowercase means the deposited "
                     "construct carries a mutation at that position. '-': expected but unresolved. "
                     "'?': generic numbering unresolved. Space: not applicable."),
        "pool": {
            "kind": "whole_receptor",
            "contact_cutoff_angstrom": args.cutoff,
            "receptors_considered": receptor_total,
            "filter": "coverage",
            "rule": ("every position GPCRdb assigns a structure-based generic number to, across "
                     "the receptors the atlas covers. No selection by function or by contact: "
                     "`coverage` carries the share of receptors that have each position, and the "
                     "panel filters on it at read time."),
            "site_classes": {c: {"observations": scan["obs_count"][c],
                                 "receptors": class_receptors[c]} for c in scan["obs_count"]},
            "numbering": ("GPCRdb structure-based numbering. This is not Ballesteros-Weinstein "
                          "where a helix carries a bulge: BW 5.42 is 5x43 here, BW 7.39 is 7x38."),
        },
        "positions": pool,
        "position_meta": position_meta,
        "segments": {p: segments.get(p, "") for p in pool},
        "motifs": build_groups(pool_set, scan, segments, reference),
        "variation": variation,
        "mutations": mutation_summary,
        "structures": {pdb: dict({"f": family_of[pdb], "r": scan["receptor_of"].get(pdb, ""),
                                  "n": names.get(pdb, ""), "s": cells[pdb]},
                                 **({"m": mutations[pdb]} if pdb in mutations else {}))
                       for pdb in structures},
        "structure_count": len(structures),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")), encoding="utf-8")
    print("wrote %s (%.2f MB, %d positions, %d structures)"
          % (args.out, args.out.stat().st_size / 1e6, len(pool), len(structures)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
