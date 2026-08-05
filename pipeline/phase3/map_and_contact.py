#!/usr/bin/env python3
"""Phase 3B–3D — residue mapping, ligand coordinate mapping and site-aware contacts.

Mapping chain, every step from a source rather than a guess:

    auth_seq_id --(mmCIF _pdbx_poly_seq_scheme)--> label_seq_id
                --(RCSB rcsb_polymer_entity_align.aligned_regions)--> UniProt position
                --(GPCRdb /services/residues/extended)--> generic number + segment

The alignment step also gives the construct/fusion boundary for free: a residue whose entity
position falls in the fusion accession's aligned region is a fusion residue, not a receptor
residue, and its atoms never enter the receptor contact table.

Geometry is one measurement — exact minimum heavy-atom distance — from which the 4.0 / 4.5 /
5.0 A flags are derived. Nothing is rounded at generation time.

    python3 pipeline/phase3/map_and_contact.py [--limit N]
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from phase3.mmcif import read, atoms, PARSER_VERSION           # noqa: E402
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402

IN = ROOT / "data/intermediate"
OUT = IN / "phase3"
CON = ROOT / "data/contacts"
RULE_VERSION = "phase3-rules-1.0.0"
CUT = 5.0
PHARM = {"pharmacological_orthosteric_ligand", "pharmacological_allosteric_ligand",
         "pharmacological_bitopic_ligand", "pharmacological_covalent_ligand",
         "endogenous_polymer_ligand", "tethered_ligand", "pharmacological_co_ligand",
         "positive_allosteric_modulator", "negative_allosteric_modulator",
         "silent_allosteric_modulator"}
POLYMER_SITES = {"extracellular_polymer_interface", "tethered_ligand_interface"}


def rd(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def fnum(x: float) -> float:
    """Deterministic float serialisation: 6 decimals is far below coordinate precision."""
    return round(x, 6)


AA3 = {"ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E","GLY":"G",
       "HIS":"H","ILE":"I","LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P","SER":"S",
       "THR":"T","TRP":"W","TYR":"Y","VAL":"V","MSE":"M","SEP":"S","TPO":"T","PTR":"Y"}


def pick_altloc(res_atoms: list[dict]) -> list[dict]:
    """Blank altloc wins; else highest occupancy; else alphabetically first. No mixing."""
    alts = {a["alt"] for a in res_atoms}
    if alts <= {""}:
        return res_atoms
    named = sorted(a for a in alts if a)
    best, best_occ = None, -1.0
    for alt in named:
        occ = max((a["occ"] for a in res_atoms if a["alt"] == alt), default=0.0)
        if occ > best_occ + 1e-9:
            best, best_occ = alt, occ
    return [a for a in res_atoms if a["alt"] in ("", best)]


def grid_pairs(recv, lig, cutoff):
    """Minimum distance per (receptor residue, ligand residue) pair via a uniform grid."""
    if not recv or not lig:
        return {}
    cell = cutoff
    g = defaultdict(list)
    for a in lig:
        g[(int(a["x"] // cell), int(a["y"] // cell), int(a["z"] // cell))].append(a)
    best: dict[tuple, tuple[float, dict, dict]] = {}
    c2 = cutoff * cutoff
    for r in recv:
        cx, cy, cz = int(r["x"] // cell), int(r["y"] // cell), int(r["z"] // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for l in g.get((cx + dx, cy + dy, cz + dz), ()):
                        d2 = ((r["x"] - l["x"]) ** 2 + (r["y"] - l["y"]) ** 2
                              + (r["z"] - l["z"]) ** 2)
                        if d2 > c2:
                            continue
                        key = (r["auth_asym"], r["auth_seq"], r["ins"], r["comp"],
                               l["auth_asym"], l["auth_seq"], l["ins"], l["comp"])
                        cur = best.get(key)
                        if cur is None or d2 < cur[0]:
                            best[key] = (d2, r, l)
    return {k: (math.sqrt(v[0]), v[1], v[2]) for k, v in best.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    S = {s["pdb_id"]: s for s in rd(IN / "structures.normalized.jsonl")}
    RI = rd(IN / "receptor_instances.jsonl")
    EI = rd(IN / "entity_inventory.jsonl")
    LC = {l["ligand_entity_id"]: l for l in rd(IN / "ligand_candidates.jsonl")}
    OB = rd(IN / "structure_ligand_observations.jsonl")
    CW = {c["receptor_instance_id"]: c for c in rd(OUT / "receptor_instance_chain_crosswalk.jsonl")}
    COORD = {c["pdb_id"]: c for c in rd(OUT / "coordinate_manifest.jsonl")}
    PAY = json.loads((ROOT / "data/raw/rcsb/entity_payload.json").read_text(encoding="utf-8"))
    GEN = json.loads((ROOT / "data/raw/gpcrdb/receptor_residues.json").read_text(encoding="utf-8"))
    generic = {e: {r["sequence_number"]: r for r in v} for e, v in GEN["receptors"].items()}

    ri_by_pdb = defaultdict(list)
    for r in RI:
        ri_by_pdb[r["pdb_id"]].append(r)
    inv_by_id = {i["entity_inventory_id"]: i for i in EI}
    obs_by_pdb = defaultdict(list)
    for o in OB:
        obs_by_pdb[o["pdb_id"]].append(o)

    res_map_rows, lig_map_rows, ctx_rows, elig_rows, excl_rows = [], [], [], [], []
    contacts_by_family = defaultdict(list)
    summaries = []
    pdb_ids = sorted(S)
    if args.limit:
        pdb_ids = pdb_ids[:args.limit]

    for n, pid in enumerate(pdb_ids, 1):
        st = S[pid]
        fam = st["major_family_id"]
        cm = COORD.get(pid, {})
        if cm.get("coordinate_availability") != "available":
            for o in obs_by_pdb[pid]:
                excl_rows.append({"structure_ligand_id": o["structure_ligand_id"], "pdb_id": pid,
                                  "status": "excluded_coordinate_unavailable",
                                  "reason": cm.get("failure_reason") or "no coordinate file"})
            continue

        cif = read(ROOT / "data/cache/coordinates" / f"{pid}.cif.gz",
                   {"_atom_site", "_pdbx_poly_seq_scheme", "_struct_conn", "_exptl",
                    "_pdbx_struct_assembly"})
        A = atoms(cif["_atom_site"])
        models = sorted({a["model"] for a in A})
        method = (cif["_exptl"][0].get("method") if cif["_exptl"] else "") or ""
        is_nmr = "NMR" in method.upper()
        use_models = models if is_nmr else models[:1]
        A = [a for a in A if a["model"] in use_models]

        # auth_seq -> label_seq per chain, from the deposition's own scheme
        scheme = {}
        for r in cif["_pdbx_poly_seq_scheme"]:
            key = (r.get("pdb_strand_id"), r.get("pdb_seq_num"),
                   "" if r.get("pdb_ins_code", ".") in (".", "?") else r.get("pdb_ins_code"))
            scheme[key] = {"label_seq": r.get("seq_id"), "asym": r.get("asym_id"),
                           "entity": r.get("entity_id"), "mon": r.get("mon_id")}

        # aligned regions per entity: entity position -> (accession, ref position)
        align = {}
        pay = PAY["entries"].get(pid)
        for pe in ((pay or {}).get("polymer_entities") or []):
            eid = pe["rcsb_polymer_entity_container_identifiers"]["entity_id"]
            regs = []
            for al in (pe.get("rcsb_polymer_entity_align") or []):
                if al.get("reference_database_name") != "UniProt":
                    continue
                acc = al.get("reference_database_accession")
                for rg in (al.get("aligned_regions") or []):
                    regs.append((int(rg["entity_beg_seq_id"]), int(rg["length"]),
                                 int(rg["ref_beg_seq_id"]), acc))
            align[eid] = regs

        covalent_pairs = set()
        for c in cif["_struct_conn"]:
            if (c.get("conn_type_id") or "").lower() == "covale":
                covalent_pairs.add((c.get("ptnr1_auth_asym_id"), c.get("ptnr1_auth_seq_id"),
                                    c.get("ptnr2_auth_asym_id"), c.get("ptnr2_auth_seq_id")))
        assemblies = cif["_pdbx_struct_assembly"]

        # ---------------- receptor residues -------------------------------------------------
        rec_atoms_by_instance: dict[str, list[dict]] = {}
        for ri in ri_by_pdb[pid]:
            cw = CW.get(ri["receptor_instance_id"], {})
            chain = ri["auth_asym_id"]
            acc = ri["receptor_accession"]
            entry = ri["receptor_entry_name"]
            gmap = generic.get(entry, {})
            regs = align.get(str(ri["polymer_entity_id"]), []) if ri["polymer_entity_id"] else []
            keep = []
            by_res = defaultdict(list)
            # A fusion partner is frequently deposited as its OWN entity on the SAME author
            # chain as the receptor (4GBR: entity 1 = ADRB2, entity 2 = T4 lysozyme, both in
            # chain A). Filtering by chain alone therefore pulls fusion residues into the
            # receptor, which both corrupts the sequence-identity check and would put fusion
            # atoms into the receptor contact table. The entity id is the discriminator.
            want_entity = str(ri["polymer_entity_id"]) if ri["polymer_entity_id"] else None
            for a in A:
                if a["auth_asym"] != chain or a["group"] != "ATOM":
                    continue
                if want_entity and a["entity"] and a["entity"] != want_entity:
                    continue
                by_res[(a["auth_seq"], a["ins"], a["comp"])].append(a)
            # ---- mapping route arbitration -------------------------------------------
            # Two sourced hypotheses map a coordinate residue onto a UniProt position:
            #   A) RCSB rcsb_polymer_entity_align.aligned_regions via label_seq_id
            #   B) the author numbering, which for most GPCR depositions IS the native
            #      UniProt numbering
            # Neither is assumed. Both are scored against the observed residue identity using
            # the GPCRdb wild-type sequence, and the better-agreeing route is used. Depositor
            # mutations legitimately break identity, so a small disagreement is expected; a
            # large one means the route is wrong. 2YCW is the case that exposed this: its
            # single aligned region does not reflect the construct's deletions and produced a
            # 30-position shift in TM6, silently renaming 7x38 as 6x44.
            def route_a(aseq_, ins_):
                sc_ = scheme.get((chain, aseq_, ins_))
                ls = int(sc_["label_seq"]) if sc_ and (sc_["label_seq"] or "").isdigit() else None
                if ls is None:
                    return None, None, None
                for beg, length, refbeg, racc in regs:
                    if beg <= ls < beg + length:
                        return racc, refbeg + (ls - beg), ls
                return None, None, ls

            def route_b(aseq_, ins_):
                if not aseq_.lstrip("-").isdigit():
                    return None, None, None
                sc_ = scheme.get((chain, aseq_, ins_))
                ls = int(sc_["label_seq"]) if sc_ and (sc_["label_seq"] or "").isdigit() else None
                return acc, int(aseq_), ls

            # Residues the RCSB alignment attributes to another accession are the fusion
            # partner. Both routes are scored only on the remainder, otherwise a chimera's
            # fusion segment would unfairly penalise whichever route does not model it.
            fusion_res = set()
            for (aseq_, ins_, comp_) in by_res:
                a_, _, _ = route_a(aseq_, ins_)
                if a_ and a_ != acc:
                    fusion_res.add((aseq_, ins_, comp_))

            # Route C: piecewise-constant offset, decided by residue identity.
            # Many engineered constructs delete a loop and continue the author numbering
            # across the gap, so a single global offset cannot be right. 4GBR is the case
            # that exposed this: chain A is genuine ADRB2 throughout, but positions 29-235
            # sit at offset 0 while 236-314 sit at offset +28 (98.6% and 100% identity
            # respectively). A single-region alignment scores 72% and hides the shift.
            # The segmentation is a Viterbi pass over a small candidate-offset set with a
            # switch penalty, so it is deterministic and cannot invent an offset that the
            # observed sequence does not support.
            ordered = sorted((k for k in by_res if k[0].lstrip("-").isdigit()),
                             key=lambda k: (int(k[0]), k[1]))
            offset_map: dict[tuple, int] = {}
            n_segments = 0
            if gmap and ordered:
                votes = Counter()
                for k in ordered:
                    obs = AA3.get(k[2])
                    if not obs:
                        continue
                    a_ = int(k[0])
                    for d in range(-120, 121):
                        g_ = gmap.get(a_ + d)
                        if g_ and g_.get("amino_acid") == obs:
                            votes[d] += 1
                cands = [d for d, _ in votes.most_common(6)] or [0]
                MISMATCH, SWITCH = 1.0, 6.0
                prev = {d: (0.0, None) for d in cands}
                back = []
                for k in ordered:
                    obs = AA3.get(k[2])
                    cur = {}
                    step = {}
                    for d in cands:
                        g_ = gmap.get(int(k[0]) + d)
                        cost = 0.0 if (g_ and obs and g_.get("amino_acid") == obs) else MISMATCH
                        best_prev, best_cost = None, None
                        for d0 in cands:
                            c = prev[d0][0] + cost + (0.0 if d0 == d else SWITCH)
                            if best_cost is None or c < best_cost - 1e-9:
                                best_cost, best_prev = c, d0
                        cur[d] = (best_cost, best_prev)
                        step[d] = best_prev
                    back.append(step)
                    prev = cur
                d_end = min(prev, key=lambda d: (prev[d][0], d))
                path = [d_end]
                for step in reversed(back[1:]):
                    d_end = step[d_end]
                    path.append(d_end)
                path.reverse()
                offset_map = dict(zip(ordered, path))
                n_segments = 1 + sum(1 for i in range(1, len(path)) if path[i] != path[i - 1])

            def route_c(aseq_, ins_):
                for k, d in offset_map.items():
                    if k[0] == aseq_ and k[1] == ins_:
                        return acc, int(aseq_) + d, None
                return None, None, None

            def score(fn):
                ok = bad = 0
                for k in by_res:
                    if k in fusion_res:
                        continue
                    a_, p_, _ = fn(k[0], k[1])
                    if a_ != acc or not p_:
                        continue
                    g_ = gmap.get(p_)
                    if not g_:
                        continue
                    if AA3.get(k[2]) == g_.get("amino_acid"):
                        ok += 1
                    else:
                        bad += 1
                return ok, bad

            ok_a, bad_a = score(route_a)
            ok_b, bad_b = score(route_b)
            ok_c, bad_c = score(route_c)
            rate_a = ok_a / (ok_a + bad_a) if (ok_a + bad_a) else -1.0
            rate_b = ok_b / (ok_b + bad_b) if (ok_b + bad_b) else -1.0
            rate_c = ok_c / (ok_c + bad_c) if (ok_c + bad_c) else -1.0
            # A route must actually agree with the observed sequence to be used. Below the
            # floor no route is trusted, the residues stay unresolved, and the observation
            # loses generic-aggregate eligibility rather than acquiring a plausible-looking
            # but unvalidated numbering.
            VALIDATION_FLOOR = 0.80
            # A simpler route wins ties: only take the segmented route when it is clearly
            # better, so a construct that really is continuous is not split for nothing.
            best_rate = max(rate_a, rate_b, rate_c)
            if best_rate < VALIDATION_FLOOR:
                chosen_route, route_fn = "no_validated_route", route_a
            elif rate_a >= best_rate - 1e-9:
                chosen_route, route_fn = "rcsb_aligned_regions", route_a
            elif rate_b >= best_rate - 1e-9:
                chosen_route, route_fn = "author_numbering_equals_uniprot", route_b
            else:
                chosen_route, route_fn = "identity_validated_piecewise_offset", route_c
            route_agreement = round(best_rate, 4)

            for (aseq, ins, comp), ats in sorted(by_res.items(),
                                                 key=lambda kv: (int(kv[0][0]) if kv[0][0].lstrip('-').isdigit() else 0, kv[0][1])):
                ats = pick_altloc(ats)
                sc = scheme.get((chain, aseq, ins))
                up_acc, up_pos, lseq = route_fn(aseq, ins)
                if chosen_route == "no_validated_route":
                    up_acc = up_pos = None
                # a fusion residue is one the RCSB alignment attributes to another accession
                fa_acc, _, _ = route_a(aseq, ins)
                if fa_acc and fa_acc != acc:
                    up_acc = fa_acc
                grec = gmap.get(up_pos) if (up_acc == acc and up_pos) else None
                identity_ok = (AA3.get(comp) == grec.get("amino_acid")) if grec else None
                if up_acc and up_acc != acc:
                    status = "construct_or_fusion_region"
                elif grec and grec.get("display_generic_number"):
                    status = "mapped_generic"
                elif grec:
                    status = "non_generic_numberable_region"
                elif up_acc == acc and up_pos:
                    status = "expected_generic_but_unmapped"
                elif lseq is not None:
                    status = "mapped_sequence_only"
                else:
                    status = "unresolved"
                if chosen_route == "no_validated_route":
                    status = "unresolved"
                muts = ri["mutation_list"]
                row = {
                    "pdb_id": pid, "receptor_instance_id": ri["receptor_instance_id"],
                    "auth_asym_id": chain, "label_asym_id": (sc or {}).get("asym"),
                    "polymer_entity_id": ri["polymer_entity_id"],
                    "auth_seq_id": aseq, "insertion_code": ins, "label_seq_id": lseq,
                    "residue_name": comp,
                    "uniprot_accession": up_acc, "uniprot_position": up_pos,
                    "display_generic_number": (grec or {}).get("display_generic_number"),
                    "canonical_generic_number": (grec or {}).get("canonical_generic_number"),
                    "protein_segment": (grec or {}).get("protein_segment"),
                    "wild_type_residue": (grec or {}).get("amino_acid"),
                    "mapping_status": status,
                    "mapping_source": (f"{chosen_route}+gpcrdb_residues" if grec else
                                       chosen_route if up_acc else
                                       "pdbx_poly_seq_scheme" if lseq else "none"),
                    "mapping_route": chosen_route,
                    "mapping_route_segments": n_segments if chosen_route == "identity_validated_piecewise_offset" else 1,
                    "route_sequence_agreement": route_agreement,
                    "residue_identity_matches_wild_type": identity_ok,
                    "mapping_confidence": ("high" if status == "mapped_generic" and route_agreement >= 0.9
                                           else "medium" if status in ("mapped_generic",
                                                                       "non_generic_numberable_region",
                                                                       "mapped_sequence_only") else "low"),
                    "depositor_reported_mutation": bool(muts) and identity_ok is False,
                    "mutation_mapping_confidence": (
                        "sequence_identity_differs_from_wild_type" if identity_ok is False
                        else "matches_wild_type" if identity_ok else "unresolved"),
                    "wild_type_identity_available": grec is not None,
                    "construct_region": status == "construct_or_fusion_region",
                    "observed_atom_count": len(ats),
                    "mapping_flags": [] if status in ("mapped_generic",
                                                      "non_generic_numberable_region") else [status],
                }
                res_map_rows.append(row)
                if status != "construct_or_fusion_region":
                    for a in ats:
                        a["_res"] = row
                    keep.extend(ats)
            rec_atoms_by_instance[ri["receptor_instance_id"]] = keep

        # ---------------- observations ------------------------------------------------------
        for o in obs_by_pdb[pid]:
            lg = LC[o["ligand_entity_id"]]
            sl = o["structure_ligand_id"]
            rid = o["receptor_instance_id"]
            cw = CW.get(rid, {})
            site = lg["binding_site_class"]
            base = {"structure_ligand_id": sl, "pdb_id": pid, "major_family_id": fam,
                    "receptor_instance_id": rid, "ligand_entity_id": lg["ligand_entity_id"]}

            def exclude(status, reason):
                excl_rows.append({**base, "status": status, "reason": reason})
                elig_rows.append({**base, "production_status": status, "reason": reason,
                                  "raw_contact_eligibility": "raw_geometry_only"
                                  if status in ("excluded_site_class_unresolved",) else "no",
                                  "generic_contact_eligibility": "no"})

            if st["apo_status"] == "confirmed_apo":
                exclude("excluded_confirmed_apo", "structure is confirmed apo")
                continue
            if lg["ligand_role"] not in PHARM:
                exclude("excluded_non_pharmacological_entity" if lg["ligand_role"] != "unresolved"
                        else "excluded_ligand_identity_unresolved",
                        f"ligand_role={lg['ligand_role']}")
                continue
            if cw.get("contact_eligibility") != "eligible":
                exclude("excluded_receptor_mapping_unresolved",
                        cw.get("reason", "receptor instance not mapped to a coordinate chain"))
                continue
            recv = rec_atoms_by_instance.get(rid) or []
            if not recv:
                exclude("excluded_receptor_mapping_unresolved",
                        "receptor chain carries no usable coordinate atoms")
                continue

            # ligand coordinate mapping
            lig_atoms, lig_desc = [], None
            if lg["entity_form"] in ("nonpolymer_residue", "covalent_adduct"):
                comps = {inv_by_id[i]["nonpolymer_comp_id"] for i in lg["entity_inventory_ids"]
                         if i in inv_by_id}
                want = {(inv_by_id[i]["auth_asym_ids"][0], str(inv_by_id[i]["auth_seq_id"]))
                        for i in lg["entity_inventory_ids"] if i in inv_by_id}
                for a in A:
                    if a["comp"] in comps and (a["auth_asym"], a["auth_seq"]) in want:
                        lig_atoms.append(a)
                lig_desc = sorted(comps)
            elif lg["entity_form"] == "polymer_chain":
                eids = {str(inv_by_id[i]["polymer_entity_id"]) for i in lg["entity_inventory_ids"]
                        if i in inv_by_id}
                chains = set()
                for i in lg["entity_inventory_ids"]:
                    if i in inv_by_id:
                        chains |= set(inv_by_id[i]["auth_asym_ids"])
                for a in A:
                    if a["auth_asym"] in chains and a["entity"] in eids:
                        lig_atoms.append(a)
                lig_desc = sorted(chains)
            if not lig_atoms:
                lig_map_rows.append({**base, "coordinate_status": "annotated_not_observed",
                                     "entity_form": lg["entity_form"], "atoms": 0,
                                     "reason": "annotated ligand has no atoms in the deposited coordinates"})
                exclude("excluded_ligand_identity_unresolved",
                        "annotated_not_observed: ligand absent from the coordinates")
                continue
            lig_atoms = [a for a in lig_atoms if a["model"] in use_models]
            by_lres = defaultdict(list)
            for a in lig_atoms:
                by_lres[(a["auth_asym"], a["auth_seq"], a["ins"], a["comp"])].append(a)
            lig_atoms = [a for k, v in by_lres.items() for a in pick_altloc(v)]
            lig_map_rows.append({**base, "coordinate_status": "observed",
                                 "entity_form": lg["entity_form"],
                                 "chains_or_components": lig_desc,
                                 "ligand_residues": len(by_lres), "atoms": len(lig_atoms)})

            ctx = {**base, "coordinate_context": "deposited_asymmetric_unit",
                   "assembly_id": (assemblies[0].get("id") if assemblies else None),
                   "assembly_operator": None,
                   "receptor_coordinate_chain": cw.get("auth_asym_id"),
                   "ligand_coordinate_chains": lig_desc,
                   "model_id": use_models[0], "models_total": len(models),
                   "is_nmr_ensemble": is_nmr,
                   "selection_evidence": ("annotated receptor and ligand entities are both "
                                          "present in the deposited coordinates and their chains "
                                          "agree with the source annotation"),
                   "ambiguity": []}

            pairs = grid_pairs(recv, lig_atoms, CUT)
            if not pairs:
                ctx["ambiguity"].append("no_receptor_ligand_atom_pair_within_5A")
                ctx["coordinate_context"] = "unresolved_coordinate_context"
                ctx["selection_evidence"] = ("ligand is present in the deposited coordinates but "
                                             "no heavy-atom pair falls within 5 A of the receptor "
                                             "chain; an assembly audit is required before any "
                                             "contact may be claimed")
                ctx_rows.append(ctx)
                exclude("excluded_coordinate_context_unresolved",
                        "ligand present but not adjacent to the receptor in the deposited "
                        "asymmetric unit; assembly audit required")
                continue
            ctx_rows.append(ctx)

            rows = []
            for (rch, rseq, rins, rcomp, lch, lseq_, lins, lcomp), (dist, ra, la) in sorted(
                    pairs.items(), key=lambda kv: (kv[0][0], int(kv[0][1]) if kv[0][1].lstrip('-').isdigit() else 0,
                                                   kv[0][2], kv[0][4], kv[0][5])):
                rm = ra["_res"]
                cov = any((rch, rseq, lch, lseq_) == p or (lch, lseq_, rch, rseq) == p
                          for p in covalent_pairs)
                rows.append({
                    "contact_id": f"{sl}|{rch}:{rseq}{rins}|{lch}:{lseq_}{lins}",
                    "structure_ligand_id": sl, "pdb_id": pid, "major_family_id": fam,
                    "receptor_instance_id": rid, "ligand_entity_id": lg["ligand_entity_id"],
                    "binding_site_class": site,
                    "coordinate_context": ctx["coordinate_context"],
                    "assembly_id": ctx["assembly_id"], "model_id": ra["model"],
                    "receptor_auth_asym_id": rch, "receptor_auth_seq_id": rseq,
                    "receptor_insertion_code": rins, "receptor_residue_name": rcomp,
                    "receptor_uniprot_position": rm["uniprot_position"],
                    "receptor_generic_number": rm["display_generic_number"],
                    "receptor_segment": rm["protein_segment"],
                    "receptor_mapping_status": rm["mapping_status"],
                    "receptor_mutation_flag": rm["depositor_reported_mutation"],
                    "ligand_entity_form": lg["entity_form"],
                    "ligand_auth_asym_id": lch, "ligand_auth_seq_id": lseq_,
                    "ligand_insertion_code": lins, "ligand_residue_name": lcomp,
                    "min_distance_angstrom": fnum(dist),
                    "within_4A": dist <= 4.0, "within_4_5A": dist <= 4.5, "within_5A": dist <= 5.0,
                    "closest_receptor_atom": ra["atom_id"], "closest_ligand_atom": la["atom_id"],
                    "covalent_connection": cov,
                    "altloc_policy_result": ra["alt"] or "blank",
                    "provenance": {"source": "RCSB mmCIF", "parser_version": PARSER_VERSION,
                                   "rule_version": RULE_VERSION,
                                   "mapping_source": rm["mapping_source"]},
                })
            contacts_by_family[fam].extend(rows)

            core_unmapped = sum(1 for r in rows
                                if r["receptor_mapping_status"] == "expected_generic_but_unmapped")
            mapped_generic = sum(1 for r in rows if r["receptor_generic_number"])
            non_generic = sum(1 for r in rows
                              if r["receptor_mapping_status"] == "non_generic_numberable_region")
            site_unresolved = site == "unresolved"
            gen_ok = core_unmapped == 0 and not site_unresolved
            prod = ("raw_geometry_only" if site_unresolved else "production_contact_eligible")
            elig_rows.append({**base, "production_status": prod,
                              "reason": ("binding_site_class unresolved: raw geometry retained, "
                                         "excluded from pooled production analysis"
                                         if site_unresolved else "all requirements met"),
                              "raw_contact_eligibility": "yes",
                              "generic_contact_eligibility": "yes" if gen_ok else "no",
                              "generic_mapping_coverage": fnum(
                                  mapped_generic / len(rows)) if rows else 0.0,
                              "expected_generic_contact_count": mapped_generic + core_unmapped,
                              "mapped_generic_contact_count": mapped_generic,
                              "unmapped_expected_generic_contacts": core_unmapped,
                              "non_generic_region_contacts": non_generic,
                              "mapping_exclusion_reason": (
                                  None if gen_ok else
                                  "contacted core residue in a generic-numberable segment carries "
                                  "no generic number" if core_unmapped else
                                  "binding_site_class unresolved")})
            if site_unresolved:
                excl_rows.append({**base, "status": "excluded_site_class_unresolved",
                                  "reason": "site class unresolved; raw geometry retained only"})
            summaries.append({
                "structure_ligand_id": sl, "pdb_id": pid, "major_family_id": fam,
                "binding_site_class": site, "ligand_entity_form": lg["entity_form"],
                "is_polymer_interface": site in POLYMER_SITES,
                "raw_receptor_contact_count": len({(r["receptor_auth_asym_id"],
                                                    r["receptor_auth_seq_id"],
                                                    r["receptor_insertion_code"]) for r in rows}),
                "receptor_residues_4A": len({(r["receptor_auth_seq_id"], r["receptor_insertion_code"])
                                             for r in rows if r["within_4A"]}),
                "receptor_residues_4_5A": len({(r["receptor_auth_seq_id"], r["receptor_insertion_code"])
                                               for r in rows if r["within_4_5A"]}),
                "receptor_residues_5A": len({(r["receptor_auth_seq_id"], r["receptor_insertion_code"])
                                             for r in rows if r["within_5A"]}),
                "ligand_residue_contact_count": len({(r["ligand_auth_asym_id"],
                                                      r["ligand_auth_seq_id"]) for r in rows}),
                "residue_pair_count": len(rows),
                "generic_mapped_contact_count": mapped_generic,
                "non_generic_region_contact_count": non_generic,
                "unmapped_expected_generic_contacts": core_unmapped,
                "mutated_contact_count": sum(1 for r in rows if r["receptor_mutation_flag"]),
                "covalent_contact_count": sum(1 for r in rows if r["covalent_connection"]),
                "min_distance_overall": fnum(min(r["min_distance_angstrom"] for r in rows)),
                "raw_contact_eligibility": "yes",
                "generic_contact_eligibility": "yes" if gen_ok else "no",
                "production_status": prod,
                "model_id": use_models[0], "models_total": len(models),
                "contact_hash": content_sha256(rows),
            })
        if n % 150 == 0:
            print(f"  {n}/{len(pdb_ids)}", file=sys.stderr)

    def dump(path: Path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(canonical_dumps(r) for r in rows) + ("\n" if rows else ""),
                        encoding="utf-8")
        return {"rows": len(rows), "content_sha256": content_sha256(rows)}

    arts = {
        "receptor_residue_mapping.jsonl": dump(OUT / "receptor_residue_mapping.jsonl", res_map_rows),
        "ligand_coordinate_mapping.jsonl": dump(OUT / "ligand_coordinate_mapping.jsonl", lig_map_rows),
        "observation_coordinate_context.jsonl": dump(OUT / "observation_coordinate_context.jsonl", ctx_rows),
        "contact_eligibility.jsonl": dump(OUT / "contact_eligibility.jsonl", elig_rows),
        "excluded_observations.jsonl": dump(OUT / "excluded_observations.jsonl", excl_rows),
        "observation_contact_summary.jsonl": dump(CON / "observation_contact_summary.jsonl", summaries),
    }
    fam_hashes = {}
    for fam, rows in sorted(contacts_by_family.items()):
        rows.sort(key=lambda r: r["contact_id"])
        d = CON / "by_family" / fam
        d.mkdir(parents=True, exist_ok=True)
        text = "\n".join(canonical_dumps(r) for r in rows) + "\n"
        with gzip.GzipFile(d / "residue_pair_contacts.jsonl.gz", "wb", mtime=0) as fh:
            fh.write(text.encode("utf-8"))
        fam_hashes[fam] = {"rows": len(rows), "content_sha256": content_sha256(rows)}
    total = [r for rows in contacts_by_family.values() for r in rows]
    manifest = {"generated_at": utc_now(), "rule_version": RULE_VERSION,
                "parser_version": PARSER_VERSION,
                "format": "sorted JSONL, gzip (mtime=0 for determinism)",
                "counts": {"residue_pair_contacts": len(total),
                           "observations_with_contacts": len(summaries),
                           "families": len(fam_hashes)},
                "per_family": fam_hashes,
                "raw_exact_distance_contacts_sha": content_sha256(
                    sorted(total, key=lambda r: r["contact_id"])),
                "contacts_4A_sha": content_sha256(
                    sorted([r for r in total if r["within_4A"]], key=lambda r: r["contact_id"])),
                "contacts_4_5A_sha": content_sha256(
                    sorted([r for r in total if r["within_4_5A"]], key=lambda r: r["contact_id"])),
                "contacts_5A_sha": content_sha256(
                    sorted([r for r in total if r["within_5A"]], key=lambda r: r["contact_id"]))}
    (CON / "global_contact_manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"artifacts": {k: v["rows"] for k, v in arts.items()},
                      "contacts": manifest["counts"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
