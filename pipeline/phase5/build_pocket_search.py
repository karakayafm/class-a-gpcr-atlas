#!/usr/bin/env python3
"""Ligand-binding pocket index, in the same shape as the microswitch one.

`build_motif_search.py` answers questions about the twenty-one microswitch positions. Those are
the positions that move on activation; they are not where a ligand sits, so a pocket question
cannot be asked of that payload at all. This builds the second half: the positions a ligand is
actually in contact with, over the same structures, in a payload the panel can read without
knowing which of the two it has been given.

The schema is deliberately identical to motif_search 1.0.0 — `positions`, `segments`, `motifs`,
`variation`, `mutations`, `structures` with the same one-character-per-position encoding — plus one
addition, `position_meta`, which the panel needs to filter at runtime:

    uppercase   the receptor's wild-type residue at that position
    lowercase   the same, where the deposited construct carries a mutation there
    -           the position is expected in this receptor but not resolved in the coordinates
    ?           generic numbering could not be resolved for it
    (space)     the position does not apply to this receptor at all

The letter is always the wild type and `m` always holds what the construct carries instead. Both
rules are load-bearing: the panel scores the letter and flags the case, so inverting either one
would make it report thermostabilising mutations as biology, silently.

The pool is the union over binding site classes of every position reaching a receptor-level
contact frequency of at least --min-freq within that class, so a position that matters only to
one class is not lost to a class it does not belong to. Which class and which frequency a reader
then wants is a runtime choice, not a property of the payload: `position_meta` carries the
per-class frequencies and the panel filters on them.

    python3 pipeline/phase5/build_pocket_search.py \
        --contacts site/data/web/structures \
        --mapping  ../class_a_gpcr_atlas/data/intermediate/phase3/receptor_residue_mapping.jsonl \
        --gpcrdb   ../class_a_gpcr_atlas/data/raw/gpcrdb/receptor_residues.json \
        --validate ../class-a-gpcr-atlas/site/data/web/global/motif_search.json
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

AA3 = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
       "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
       "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V"}
UNRESOLVED, UNMAPPED, ABSENT = "-", "?", " "

# Ligand roles that are a binder rather than an artefact of the experiment. The atlas curates its
# observations upstream, so this filter removes little; it stays because the payload it protects
# is the one a reader would not be able to check by eye.
BINDING_ROLES = {
    "pharmacological_orthosteric_ligand", "pharmacological_covalent_ligand",
    "pharmacological_allosteric_ligand", "positive_allosteric_modulator",
    "negative_allosteric_modulator", "pharmacological_co_ligand", "endogenous_polymer_ligand",
}
# Chemical components that are present because of how the crystal was grown, not because anything
# binds there: lipids, sterols, detergents, cryoprotectants, buffers, ions, glycans, and the
# cofactors of fusion partners. Excluded by component code.
ADDITIVE_CODES = set("""
CLR CHS OLA OLB OLC PLM MYR STE PEF PGW POV PC1 LMT LMU DDQ BOG BNG OCT NON D10 D12 UND HTG HEG
C8E P6G 1PE 2PE PE4 PE5 PEG PG4 PGE MPG MHA MES EPE TRS BTB BIS
GOL EDO MPD DMS ACT ACY FMT EOH IPA TFA CIT FLC MLI MAE TAR SIN AKG PYR URE IMD BEN
NA K MG CA ZN CL BR IOD SO4 PO4 NO3 CO3 CAC CD HG MN NI CU FE CS RB SR BA LI F
NAG NDG BMA MAN GAL FUC GLC BGC XYS
ATP ADP AMP GTP GDP GNP GSP FAD NAD NAP COA SAM SAH
""".split())
COMPONENT_CODE = re.compile(r":([A-Z0-9]{1,3})$")


def short(generic: str | None) -> str | None:
    """`3.28x28` -> `3x28`. The atlas labels positions with GPCRdb's structure-based number.

    Worth stating because it does not agree with Ballesteros-Weinstein wherever a helix carries a
    bulge: the catechol serine of the aminergic receptors is BW 5.42 but GPCRdb 5x43, and BW 7.39
    is GPCRdb 7x38. Reading a literature position straight into this payload without converting it
    lands one residue away.
    """
    if not generic or "." not in generic or "x" not in generic:
        return generic
    return generic.split(".")[0] + "x" + generic.split("x")[1]


def position_sort_key(position: str):
    m = re.match(r"^(\d+)x(\d+)$", position)
    return (float(m.group(1)), int(m.group(2))) if m else (99.0, 9999)


# ------------------------------------------------------------------ contacts -> pool

def scan_contacts(contacts_dir: Path, cutoff: float):
    """Every ligand contact in the published viewer bundles, grouped by binding site class."""
    obs_count = collections.Counter()
    receptors_in_class = collections.defaultdict(set)
    contact_receptors = collections.defaultdict(lambda: collections.defaultdict(set))
    segments, receptor_of = {}, {}
    dropped_role = collections.Counter()
    dropped_component = collections.Counter()
    ungeneric = 0

    for path in sorted(contacts_dir.glob("*/viewer_meta.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        pdb = meta.get("pdb_id") or path.parent.name
        receptor = meta.get("receptor_entry_name") or ""
        receptor_of[pdb] = receptor
        for obs in meta.get("observations", []):
            role = obs.get("ligand_role")
            if role not in BINDING_ROLES:
                dropped_role[role] += 1
                continue
            code = COMPONENT_CODE.search(str(obs.get("ligand_entity_id") or ""))
            if code and code.group(1) in ADDITIVE_CODES:
                dropped_component[code.group(1)] += 1
                continue
            site_class = obs.get("binding_site_class") or "unknown"
            obs_count[site_class] += 1
            receptors_in_class[site_class].add(receptor)
            for detail in obs.get("contact_receptor_details") or []:
                distance = detail.get("min_distance_angstrom")
                if distance is None or distance > cutoff:
                    continue
                position = short(detail.get("generic_position"))
                if not position:
                    ungeneric += 1
                    continue
                contact_receptors[site_class][position].add(receptor)
                if detail.get("segment"):
                    segments[position] = detail["segment"]
    return {"obs_count": obs_count, "receptors_in_class": receptors_in_class,
            "contact_receptors": contact_receptors, "segments": segments,
            "receptor_of": receptor_of, "dropped_role": dropped_role,
            "dropped_component": dropped_component, "ungeneric": ungeneric}


def build_pool(scan, min_freq: float):
    """Union across classes: a position kept by any one class is in the pool."""
    pool = set()
    for site_class, positions in scan["contact_receptors"].items():
        denominator = len(scan["receptors_in_class"][site_class]) or 1
        for position, receptors in positions.items():
            if len(receptors) / denominator >= min_freq:
                pool.add(position)
    return sorted(pool, key=position_sort_key)


# ------------------------------------------------------------------ sequences and structures

def load_bw(gpcrdb_path: Path, pool: set[str]):
    """The Ballesteros-Weinstein label for each pool position, and how uniform it is.

    Not one number per position: a bulge that one receptor has and another does not shifts every
    BW number above it, so the same structure-based position can be 5.42 in most receptors and
    5.43 in the rest. The most common value is carried with the count it holds for, and the
    variants beside it, because a single number would be quietly wrong for the minority.
    """
    receptors = json.loads(gpcrdb_path.read_text(encoding="utf-8"))["receptors"]
    seen = collections.defaultdict(collections.Counter)
    for rows in receptors.values():
        for row in rows:
            position = short(row.get("canonical_generic_number"))
            display = row.get("display_generic_number")
            if position in pool and display and "x" in display:
                seen[position][display.split("x")[0]] += 1
    out = {}
    for position, counts in seen.items():
        modal, held = counts.most_common(1)[0]
        out[position] = {
            "bw": modal,
            "display": modal + "x" + position.split("x")[1],
            "receptors": held,
            "total": sum(counts.values()),
            "variable": len(counts) > 1,
            "diverges": modal.split(".")[-1] != position.split("x")[1],
            # Share of receptors the modal BW number does not hold for; see
            # build_generic_numbering.py for why the modal value alone is not enough.
            "minority": round((sum(counts.values()) - held) / sum(counts.values()), 4)
                        if sum(counts.values()) else 0.0,
            "variants": [[bw, n] for bw, n in counts.most_common()[1:]],
        }
    return out


def load_wild_type(gpcrdb_path: Path, pool: set[str]):
    """Per receptor: which pool positions its own sequence has, and the residue at each.

    This is what separates "the structure did not resolve this position" from "this receptor does
    not have this position at all" — a distinction the encoding carries and a score depends on,
    because only the first of the two is evidence of anything.
    """
    payload = json.loads(gpcrdb_path.read_text(encoding="utf-8"))["receptors"]
    wild_type = collections.defaultdict(dict)      # receptor -> position -> residue
    by_uniprot = collections.defaultdict(dict)     # receptor -> uniprot position -> position
    for receptor, residues in payload.items():
        for residue in residues:
            position = short(residue.get("canonical_generic_number"))
            if not position or position not in pool:
                continue
            wild_type[receptor][position] = residue["amino_acid"]
            by_uniprot[receptor][residue["sequence_number"]] = position
    return wild_type, by_uniprot


def read_mapping(mapping_path: Path, pool: set[str], receptor_of: dict, by_uniprot: dict):
    """Stream the phase 3 residue mapping, keeping only what lands on a pool position.

    Rows carrying a generic number are placed by it. Rows without one still matter — they are how
    a position is known to be expected and unresolved rather than absent — so they are placed by
    their UniProt position through the receptor's own sequence.
    """
    observed, unresolved = {}, {}
    with mapping_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            pdb = row.get("pdb_id")
            receptor = receptor_of.get(pdb)
            if not receptor:
                continue
            position = short(row.get("canonical_generic_number"))
            if not position or position not in pool:
                uniprot = row.get("uniprot_position")
                position = by_uniprot.get(receptor, {}).get(uniprot)
                if not position or position not in pool:
                    continue
                # No generic number on the row: the residue is in the sequence but the structure
                # could not be numbered there, or was not modelled there.
                status = row.get("mapping_status")
                key = (pdb, position)
                if key not in observed and key not in unresolved:
                    unresolved[key] = UNMAPPED if status == "expected_generic_but_unmapped" \
                        else UNRESOLVED
                continue
            if row.get("mapping_status") != "mapped_generic":
                continue
            wild = row.get("wild_type_residue")
            if not wild:
                continue
            key = (pdb, position)
            if key in observed:
                continue
            matches = row.get("residue_identity_matches_wild_type")
            construct = AA3.get(str(row.get("residue_name") or "").upper())
            observed[key] = (wild, matches is False, construct)
    return observed, unresolved


def encode(pool, structures, wild_type, observed, unresolved, receptor_of, mapping_status):
    """One fixed-width string per structure, and the construct residues beside it.

    A structure whose generic numbering did not validate as a whole reports nothing: every
    position of it is `?`. The residue mapping still carries rows for such a structure, and taking
    them at face value would put a confident letter on a numbering the atlas itself declined to
    stand behind. The microswitch payload applies the same gate; twelve structures fall under it.
    """
    index = {p: i for i, p in enumerate(pool)}
    cells, mutations = {}, {}
    for pdb in structures:
        receptor = receptor_of.get(pdb, "")
        sequence = wild_type.get(receptor, {})
        if mapping_status.get(pdb) != "validated":
            cells[pdb] = UNMAPPED * len(pool)
            continue
        row = [ABSENT] * len(pool)
        engineered = {}
        for position in pool:
            key = (pdb, position)
            if key in observed:
                wild, is_mutation, construct = observed[key]
                row[index[position]] = wild.lower() if is_mutation else wild
                if is_mutation and construct:
                    engineered[position] = construct
            elif key in unresolved:
                row[index[position]] = unresolved[key]
            elif position in sequence:
                # In this receptor's sequence, absent from this structure's coordinates.
                row[index[position]] = UNRESOLVED
        cells[pdb] = "".join(row)
        if engineered:
            mutations[pdb] = engineered
    return cells, mutations


# ------------------------------------------------------------------ aggregates

def build_variation(pool, structures, cells, receptor_of, family_of, index):
    """Identical in shape to the microswitch payload's, counted the same way.

    Receptors as well as structures, because a receptor solved eighty times would otherwise look
    like eighty independent observations of its own residue and the distribution would describe
    the deposition record rather than the family.
    """
    by_structure = collections.defaultdict(collections.Counter)
    by_receptor = collections.defaultdict(lambda: collections.defaultdict(set))
    for pdb in structures:
        family = family_of.get(pdb)
        if not family:
            continue
        receptor = receptor_of.get(pdb, "")
        for position in pool:
            char = cells[pdb][index[position]]
            if char in (UNRESOLVED, UNMAPPED, ABSENT):
                continue
            wild = char.upper()
            for scope in ("class_a", family):
                by_structure[(scope, position)][wild] += 1
                by_receptor[(scope, position)][wild].add(receptor)
    variation = collections.defaultdict(dict)
    for (scope, position), counts in by_structure.items():
        receptors = {aa: len(rs) for aa, rs in by_receptor[(scope, position)].items()}
        total = sum(receptors.values())
        consensus = max(receptors.items(), key=lambda kv: kv[1])[0] if receptors else None
        variation[scope][position] = {
            "consensus": consensus,
            "by_structure": [[aa, n] for aa, n in counts.most_common()],
            "by_receptor": [[aa, n] for aa, n in sorted(receptors.items(),
                                                        key=lambda kv: (-kv[1], kv[0]))],
            "receptors": total,
            "divergent_receptor_share": round(1 - receptors.get(consensus, 0) / total, 4)
                                        if total else 0.0,
        }
    return variation


def build_mutation_summary(pool, structures, cells, mutations, family_of, index):
    counts = collections.defaultdict(collections.Counter)
    seen = collections.Counter()
    for pdb in structures:
        family = family_of.get(pdb)
        if not family:
            continue
        for position in pool:
            char = cells[pdb][index[position]]
            if char == ABSENT:
                continue
            for scope in ("class_a", family):
                seen[(scope, position)] += 1
                if char.islower():
                    counts[(scope, position)][mutations.get(pdb, {}).get(position, "X")] += 1
    summary = collections.defaultdict(dict)
    for (scope, position), residues in counts.items():
        total = seen[(scope, position)]
        summary[scope][position] = {
            "structures": sum(residues.values()),
            "residues": [[aa, n] for aa, n in residues.most_common()],
            "share": round(sum(residues.values()) / total, 4) if total else 0.0}
    return summary


def entropy_of(pairs):
    total = sum(n for _, n in pairs)
    if not total:
        return 0.0
    return round(-sum((n / total) * math.log2(n / total) for _, n in pairs if n), 4)


def build_groups(pool, scan, segments, min_freq):
    """The `motifs` block, derived rather than written.

    Two rules, both mechanical. A group per transmembrane segment, because a segment is what a
    reader points at when they say where a position is; and one consensus group per binding site
    class, holding the positions that contact a ligand in more than half of that class's
    receptors. No group is a biological claim — each is a statement about where the positions are
    or how often they are touched, and each says which class it came from.
    """
    groups = []
    by_segment = collections.defaultdict(list)
    for position in pool:
        by_segment[segments.get(position, "?")].append(position)
    for segment in sorted(by_segment, key=lambda s: (len(s), s)):
        positions = sorted(by_segment[segment], key=position_sort_key)
        if len(positions) < 2:
            continue
        groups.append({"motif_id": "segment_" + segment, "positions": positions,
                       "segments": [segment], "site_class": None,
                       "rule": "every pool position in " + segment})
    for site_class, positions in scan["contact_receptors"].items():
        denominator = len(scan["receptors_in_class"][site_class]) or 1
        consensus = sorted((p for p, rs in positions.items()
                            if p in pool and len(rs) / denominator > 0.50),
                           key=position_sort_key)
        if len(consensus) < 2:
            continue
        groups.append({
            "motif_id": "consensus_" + site_class,
            "positions": consensus,
            "segments": sorted({segments.get(p, "?") for p in consensus}),
            "site_class": site_class,
            "rule": "contacts a ligand in more than 50% of the receptors of " + site_class})
    return groups


# ------------------------------------------------------------------ main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contacts", type=Path, default=ROOT / "site/data/web/structures")
    parser.add_argument("--mapping", type=Path,
                        default=ROOT / "data/intermediate/phase3/receptor_residue_mapping.jsonl")
    parser.add_argument("--gpcrdb", type=Path,
                        default=ROOT / "data/raw/gpcrdb/receptor_residues.json")
    parser.add_argument("--families", type=Path, default=ROOT / "site/data/web/families")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "data/intermediate/phase5/pocket_search.json")
    parser.add_argument("--cutoff", type=float, default=4.5)
    parser.add_argument("--min-freq", type=float, default=0.01)
    parser.add_argument("--validate", type=Path, default=None,
                        help="motif_search.json to reproduce on the positions the two share")
    args = parser.parse_args()

    scan = scan_contacts(args.contacts, args.cutoff)
    pool = build_pool(scan, args.min_freq)
    pool_set = set(pool)
    print("pool: %d positions from %d site classes" % (len(pool), len(scan["obs_count"])),
          file=sys.stderr)

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
        receptor = meta.get("receptor_entry_name") or ""
        slug = receptor_family.get(receptor)
        if slug:
            family_of[pdb] = slug
        names[pdb] = meta.get("receptor_name") or ""

    wild_type, by_uniprot = load_wild_type(args.gpcrdb, pool_set)
    bw_of = load_bw(args.gpcrdb, pool_set)
    observed, unresolved = read_mapping(args.mapping, pool_set, scan["receptor_of"], by_uniprot)
    structures = sorted(family_of)
    cells, mutations = encode(pool, structures, wild_type, observed, unresolved,
                              scan["receptor_of"], mapping_status)
    index = {p: i for i, p in enumerate(pool)}

    if args.validate:
        reference = json.loads(args.validate.read_text(encoding="utf-8"))
        shared = [p for p in reference["positions"] if p in index]
        ref_index = {p: i for i, p in enumerate(reference["positions"])}
        checked = mismatched = 0
        examples = []
        for pdb, record in reference["structures"].items():
            if pdb not in cells:
                continue
            for position in shared:
                checked += 1
                theirs = record["s"][ref_index[position]]
                ours = cells[pdb][index[position]]
                if theirs != ours:
                    mismatched += 1
                    if len(examples) < 8:
                        examples.append("%s %s: motif=%r pocket=%r" % (pdb, position, theirs, ours))
        print("validate: %d cells over %d shared positions, %d differ"
              % (checked, len(shared), mismatched), file=sys.stderr)
        for line in examples:
            print("   " + line, file=sys.stderr)

    variation = build_variation(pool, structures, cells, scan["receptor_of"], family_of, index)
    mutation_summary = build_mutation_summary(pool, structures, cells, mutations, family_of, index)

    # What the panel filters on. Frequencies per class, so the reader chooses the class and the
    # threshold at read time rather than the pipeline choosing both for them.
    position_meta = {}
    class_receptors = {c: len(rs) for c, rs in scan["receptors_in_class"].items()}
    for position in pool:
        frequency, receptors = {}, {}
        for site_class, positions in scan["contact_receptors"].items():
            denominator = class_receptors.get(site_class) or 1
            hit = len(positions.get(position, ()))
            if hit:
                frequency[site_class] = round(hit / denominator, 4)
                receptors[site_class] = hit
        pairs = (variation.get("class_a", {}).get(position, {}) or {}).get("by_receptor", [])
        position_meta[position] = {
            "segment": scan["segments"].get(position, ""),
            "frequency": frequency,
            "receptors": receptors,
            "entropy": entropy_of(pairs),
            # Ballesteros-Weinstein beside the structure-based label, so the panel can show both
            # and a reader never has to guess which scheme a number is in.
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
            "kind": "ligand_binding_pocket",
            "contact_cutoff_angstrom": args.cutoff,
            "min_receptor_frequency": args.min_freq,
            "rule": ("union over binding site classes of every generic position contacting a "
                     "ligand heavy atom within the cutoff in at least min_receptor_frequency of "
                     "that class's ligand-bound receptors; counted per receptor, not per "
                     "structure"),
            "site_classes": {c: {"observations": scan["obs_count"][c],
                                 "receptors": class_receptors[c]} for c in scan["obs_count"]},
            "numbering": ("GPCRdb structure-based numbering. This is not Ballesteros-Weinstein "
                          "where a helix carries a bulge: BW 5.42 is 5x43 here, BW 7.39 is 7x38."),
        },
        "positions": pool,
        "position_meta": position_meta,
        "segments": {p: scan["segments"].get(p, "") for p in pool},
        "motifs": build_groups(pool, scan, scan["segments"], args.min_freq),
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
    print("wrote %s (%.2f MB)" % (args.out, args.out.stat().st_size / 1e6), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
