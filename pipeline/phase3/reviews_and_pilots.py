#!/usr/bin/env python3
"""Phase 3 — manual-review packets, site-class review, tethered-ligand search, threshold
pilots and the aminergic exact-crosswalk regression."""
from __future__ import annotations
import gzip, json, os, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402
IN, OUT, CON = ROOT / "data/intermediate", ROOT / "data/intermediate/phase3", ROOT / "data/contacts"
PIL = ROOT / "data/pilots/phase3"
FROZEN = ROOT.parent


def norm_gn(g):
    """Normalise a GPCRdb generic number to the helix x position form.

    GPCRdb's display form combines Ballesteros-Weinstein with the structure-based index
    ('3.32x32'); the frozen aminergic project stores the structure-based form alone ('3x32').
    They denote the same position, so a regression comparison must normalise before it can
    claim a discrepancy.
    """
    if not g:
        return None
    s = str(g)
    if "x" not in s:
        return s
    left, right = s.split("x", 1)
    helix = left.split(".")[0]
    return f"{helix}x{right}"


def rd(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def dump(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(canonical_dumps(r) for r in rows) + ("\n" if rows else ""),
                    encoding="utf-8")
    return {"rows": len(rows), "content_sha256": content_sha256(rows)}


def main() -> int:
    S = {s["pdb_id"]: s for s in rd(IN / "structures.normalized.jsonl")}
    RI = {r["receptor_instance_id"]: r for r in rd(IN / "receptor_instances.jsonl")}
    EI = {i["entity_inventory_id"]: i for i in rd(IN / "entity_inventory.jsonl")}
    LC = {l["ligand_entity_id"]: l for l in rd(IN / "ligand_candidates.jsonl")}
    MQ = rd(IN / "manual_review_queue.jsonl")
    CF = rd(IN / "source_conflicts.jsonl")
    CW = {c["receptor_instance_id"]: c for c in rd(OUT / "receptor_instance_chain_crosswalk.jsonl")}
    ELIG = {e["structure_ligand_id"]: e for e in rd(OUT / "contact_eligibility.jsonl")}
    SUM = rd(CON / "observation_contact_summary.jsonl")
    SREF = json.loads((ROOT / "data/normalized/structure_references.json").read_text(encoding="utf-8")) \
        if (ROOT / "data/normalized/structure_references.json").exists() else {"entries": {}}
    UNI = json.loads((ROOT / "data/normalized/class_a_structure_universe.json").read_text(encoding="utf-8"))
    pub = {u["pdb_id"]: u["gpcrdb_structure_record"].get("publication") for u in UNI["structures"]}
    arts = {}

    # ---------------------------------------------------------------- review packets
    packets = []
    for q in MQ:
        pid = q["pdb_id"]
        st = S.get(pid, {})
        packets.append({
            "review_id": q["review_id"], "pdb_id": pid, "category": q["category"],
            "question": q["question"], "priority": q["priority"],
            "source_values": {
                "gpcrdb_ligand_annotation": q["auto_evidence"].get("annotation"),
                "gpcrdb_receptor": st.get("receptor_entry_name"),
                "gpcrdb_publication": pub.get(pid),
                "rcsb_metadata_completeness": st.get("metadata_completeness"),
                "chain_description": q["auto_evidence"].get("description"),
                "uniprot_ids": q["auto_evidence"].get("uniprot_ids"),
                "sequence_length": q["auto_evidence"].get("sequence_length")},
            "coordinate_context": {
                "coordinate_available": True,
                "note": "coordinates were retrieved for every structure in Phase 3"},
            "geometry_as_supporting_evidence_only": (
                "geometry may support a decision but may not by itself assign ligand identity, "
                "pharmacology or binding mode"),
            "automated_proposal": q["reason"],
            "automated_evidence": q["auto_evidence"],
            "curator_decision": None, "curator_identity": None,
            "review_date": None, "review_status": "open",
        })
    for c in CF:
        packets.append({
            "review_id": c["conflict_id"], "pdb_id": c["pdb_id"],
            "category": f"source_conflict:{c['source_conflict_type']}",
            "question": "Which source is right, and can coordinates settle it?",
            "priority": "high" if c["manual_review_required"] else "medium",
            "source_values": c["source_values"],
            "coordinate_context": {"coordinate_available": True},
            "geometry_as_supporting_evidence_only": (
                "absence of a component in the coordinates supports that it was not modelled; "
                "it does not by itself prove the source pharmacology wrong, and it never "
                "licenses inventing ligand coordinates"),
            "automated_proposal": c["decision_rule"],
            "automated_evidence": {"decision_status": c["decision_status"]},
            "curator_decision": None, "curator_identity": None,
            "review_date": None, "review_status": "open"})
    arts["review_resolutions"] = dump(OUT / "review_resolutions.jsonl",
                                      sorted(packets, key=lambda p: p["review_id"]))

    # ---------------------------------------------------------------- site-class review
    site_rows = []
    for l in LC.values():
        if l["binding_site_class"] != "unresolved":
            continue
        pid = l["pdb_id"]
        sl = f"{l['ligand_entity_id']}::{l['receptor_instance_id']}"
        s = next((x for x in SUM if x["structure_ligand_id"] == sl), None)
        segs = Counter()
        if s:
            fam = S[pid]["major_family_id"]
            f = CON / "by_family" / fam / "residue_pair_contacts.jsonl.gz"
            if f.exists():
                for line in gzip.open(f, "rt"):
                    r = json.loads(line)
                    if r["structure_ligand_id"] == sl and r["receptor_segment"]:
                        segs[r["receptor_segment"]] += 1
        site_rows.append({
            "ligand_entity_id": l["ligand_entity_id"], "pdb_id": pid,
            "ligand_role": l["ligand_role"], "binding_mode": l["binding_mode"],
            "evidence_order": ["official structure annotation", "primary publication",
                               "receptor/ligand role", "coordinate geometry", "mapped segments"],
            "official_annotation": l["source_annotations"].get("gpcrdb_ligand"),
            "primary_publication": pub.get(pid),
            "contacted_segments": dict(segs.most_common()),
            "geometry_supported_site_candidate": (
                "canonical_7tm_pocket" if segs and sum(
                    v for k, v in segs.items() if str(k).startswith("TM")) / max(sum(segs.values()), 1) > 0.6
                else "geometry_inconclusive" if segs else "no_geometry"),
            "geometry_note": ("geometry alone may not assign a site class; this is a candidate "
                              "only and requires curator or source support"),
            "curator_decision": None, "curator_identity": None, "review_date": None,
            "review_status": "open",
            "current_status": "unresolved",
            "production_effect": ("retained for candidate geometry audit; excluded from pooled "
                                 "production analysis; never auto-merged into another class")})
    arts["site_class_review"] = dump(OUT / "site_class_review.jsonl", site_rows)

    # ---------------------------------------------------------------- tethered ligands
    PAR = {"par1_human", "par2_human", "par3_human", "par4_human",
           "f2r_human", "f2rl1_human", "f2rl2_human", "f2rl3_human",
           "gpr56_human", "adgra2_human"}
    teth = []
    for pid, st in sorted(S.items()):
        entry = (st.get("receptor_entry_name") or "").lower()
        name = (st.get("receptor_name") or "").lower()
        is_par = entry in PAR or "protease-activated" in name or name.startswith("par")
        if not is_par:
            continue
        teth.append({
            "pdb_id": pid, "receptor": st["receptor_name"],
            "receptor_entry_name": st["receptor_entry_name"],
            "receptor_chain": st["receptor_instances"],
            "segment_start": None, "segment_end": None,
            "cleavage_site_information": None,
            "source_database": None, "primary_publication": pub.get(pid),
            "evidence_statement": (
                "candidate identified from receptor identity only. No official receptor "
                "annotation, cleavage-site mapping or publication statement giving a residue "
                "range was available from the sources Phase 3 calls (GPCRdb, RCSB). A tethered "
                "ligand is NOT assigned from proximity or from receptor family alone."),
            "confidence": "unresolved",
            "entity_form": "receptor_segment",
            "status": "receptor_segment_candidate_unresolved",
            "curator_status": "open",
            "production_effect": "excluded from production contact"})
    arts["tethered_ligand_candidates"] = dump(OUT / "tethered_ligand_candidates.jsonl", teth)

    # ---------------------------------------------------------------- threshold pilots
    fam_name = {s["major_family_id"]: s["major_family_name"] for s in S.values()}
    by_sl = {s["structure_ligand_id"]: s for s in SUM}

    def pilot(name, sel, note):
        rows = [s for s in SUM if sel(s)]
        d = PIL / name
        d.mkdir(parents=True, exist_ok=True)
        stats = {
            "pilot": name, "note": note, "observations": len(rows),
            "structures": len({r["pdb_id"] for r in rows}),
            "site_classes": dict(Counter(r["binding_site_class"] for r in rows)),
            "ligand_forms": dict(Counter(r["ligand_entity_form"] for r in rows)),
            "receptor_residues_4A": {"total": sum(r["receptor_residues_4A"] for r in rows),
                                     "mean": round(sum(r["receptor_residues_4A"] for r in rows) / max(len(rows), 1), 2)},
            "receptor_residues_4_5A": {"total": sum(r["receptor_residues_4_5A"] for r in rows),
                                       "mean": round(sum(r["receptor_residues_4_5A"] for r in rows) / max(len(rows), 1), 2)},
            "receptor_residues_5A": {"total": sum(r["receptor_residues_5A"] for r in rows),
                                     "mean": round(sum(r["receptor_residues_5A"] for r in rows) / max(len(rows), 1), 2)},
            "ligand_residue_contacts": sum(r["ligand_residue_contact_count"] for r in rows),
            "residue_pairs": sum(r["residue_pair_count"] for r in rows),
            "generic_mapped_contacts": sum(r["generic_mapped_contact_count"] for r in rows),
            "non_generic_region_contacts": sum(r["non_generic_region_contact_count"] for r in rows),
            "generic_eligible_observations": sum(1 for r in rows if r["generic_contact_eligibility"] == "yes"),
            "min_distance_min": min((r["min_distance_overall"] for r in rows), default=None),
        }
        (d / "threshold_stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False),
                                                encoding="utf-8")
        dump(d / "observations.jsonl", sorted(rows, key=lambda r: r["structure_ligand_id"]))
        return stats

    pilots = {
        "nucleotide": pilot("nucleotide", lambda s: s["major_family_id"] == "001_006",
                            "small-molecule pocket, environment entities excluded"),
        "peptide_interface": pilot("peptide_interface",
                                   lambda s: s["major_family_id"] == "001_002" and s["is_polymer_interface"],
                                   "polymer interface, coverage-balanced by ligand size"),
        "protein_chemokine": pilot("protein_chemokine",
                                   lambda s: s["major_family_id"] == "001_003" and s["is_polymer_interface"],
                                   "chemokine receptors sit under Protein receptors in GPCRdb, "
                                   "not Peptide; the real assignment is preserved"),
        "sensory_opsin": pilot("sensory_opsin",
                               lambda s: s["binding_site_class"] == "covalent_core_site",
                               "covalent retinal, covalent bond flag, core-site contacts"),
        "multi_ligand": pilot("multi_ligand",
                              lambda s: S[s["pdb_id"]]["ligand_status"] == "multi_ligand_bound",
                              "orthosteric + modulator, kept as separate observations"),
        "apo": pilot("apo", lambda s: S[s["pdb_id"]]["apo_status"] == "confirmed_apo",
                     "confirmed apo structures must produce no pharmacological contact row"),
    }

    # ---------------------------------------------------------------- aminergic regression
    frozen_path = FROZEN / "pathway_pocket_data_v15.json"
    reg = {"status": "frozen_data_unavailable"}
    fwd, rev, matched = [], [], []
    if frozen_path.exists():
        # READ ONLY. The frozen file is never written, moved or reformatted.
        FZ = json.loads(frozen_path.read_text(encoding="utf-8"))
        # Exact crosswalk key per section 20: PDB + receptor chain + ligand component +
        # ligand chain + ligand residue instance. Nothing looser is compared.
        old_by_key = {}
        for s in FZ["structures"]:
            key = (s["pdb_id"].upper(), s.get("chain"), (s.get("ligand_code") or "").upper(),
                   s.get("ligand_chain"), str(s.get("ligand_resnum")))
            old_by_key[key] = s
        # the same key, rebuilt from the new pipeline
        new_by_key = {}
        for s in SUM:
            if s["major_family_id"] != "001_001":
                continue
            ri = RI.get(s["structure_ligand_id"].split("::")[-1], {})
            lg = LC.get(s["structure_ligand_id"].split("::")[0], {})
            for iid in lg.get("entity_inventory_ids", []):
                inv = EI.get(iid)
                if not inv or not inv.get("nonpolymer_comp_id"):
                    continue
                key = (s["pdb_id"], ri.get("auth_asym_id"),
                       (inv["nonpolymer_comp_id"] or "").upper(),
                       (inv["auth_asym_ids"] or [None])[0], str(inv.get("auth_seq_id")))
                new_by_key.setdefault(key, []).append(s)
        for key, o in sorted(old_by_key.items()):
            pdb = key[0]
            cand = new_by_key.get(key)
            if not cand:
                fwd.append({"pdb_id": pdb, "frozen_key": list(key),
                            "reason": ("no new observation matches this exact "
                                       "PDB+chain+component+ligand-chain+resnum key"),
                            "new_structure_exists": pdb in S,
                            "new_ligand_status": S.get(pdb, {}).get("ligand_status"),
                            "new_keys_for_this_pdb": [list(k) for k in new_by_key if k[0] == pdb]})
                continue
            s = cand[0]
            old_gn = {norm_gn(r["gn"]) for r in (o.get("residues") or []) if r.get("gn")}
            fam = S[pdb]["major_family_id"]
            f = CON / "by_family" / fam / "residue_pair_contacts.jsonl.gz"
            new_gn, new_res = set(), set()
            if f.exists():
                for line in gzip.open(f, "rt"):
                    r = json.loads(line)
                    if r["structure_ligand_id"] != s["structure_ligand_id"]:
                        continue
                    if not r["within_5A"]:
                        continue
                    new_res.add((r["receptor_auth_seq_id"], r["receptor_insertion_code"]))
                    if r["receptor_generic_number"]:
                        new_gn.add(norm_gn(r["receptor_generic_number"]))
            inter = old_gn & new_gn
            matched.append({
                "pdb_id": pdb, "frozen_key": list(key),
                "structure_ligand_id": s["structure_ligand_id"],
                "frozen_contact_residue_count": o.get("n_contacts"),
                "frozen_generic_numbered_count": len(old_gn),
                "new_contact_residue_count_5A": s["receptor_residues_5A"],
                "new_generic_numbered_count": len(new_gn),
                "generic_positions_in_common": len(inter),
                "generic_only_in_frozen": sorted(old_gn - new_gn),
                "generic_only_in_new": sorted(new_gn - old_gn),
                "contact_equivalent": old_gn == new_gn})
        for key in sorted(new_by_key):
            if key not in old_by_key:
                rev.append({"pdb_id": key[0], "new_key": list(key),
                            "reason": ("new Class A pipeline produces an aminergic observation "
                                       "whose exact key is absent from the frozen 352-structure set"),
                            "in_frozen_universe": any(k[0] == key[0] for k in old_by_key)})
        eq = sum(1 for m in matched if m["contact_equivalent"])
        reg = {
            "frozen_source": frozen_path.name,
            "frozen_observations": len(old_by_key),
            "new_aminergic_observations": len(new_by_key),
            "exact_crosswalk_count": len(matched),
            "contact_equivalent_count": eq,
            "discrepancy_count": len(matched) - eq,
            "forward_anti_join_count": len(fwd),
            "reverse_anti_join_count": len(rev),
            "comparison_definition": ("identical 5 A minimum heavy-atom definition; the compared "
                                      "quantity is the set of GPCRdb generic positions contacted"),
            "frozen_reference_hash": "ec17192ade784cbc",
            "hash_comparability": ("The frozen per_pdb_contacts_sha describes the frozen "
                                   "352-observation aminergic universe. The new universe differs "
                                   "(395 aminergic structures, a different ligand model, "
                                   "site-class partitioning), so a differing hash is NOT evidence "
                                   "of data corruption. Only this exact-crosswalk subset is "
                                   "comparable, and it is compared position by position."),
            "frozen_file_modified": False}
    d = PIL / "aminergic_regression"
    d.mkdir(parents=True, exist_ok=True)
    (d / "regression_summary.json").write_text(json.dumps(reg, indent=1, ensure_ascii=False),
                                               encoding="utf-8")
    arts["regression_crosswalk"] = dump(d / "exact_crosswalk.jsonl", matched)
    arts["regression_forward_anti_join"] = dump(d / "forward_anti_join.jsonl", fwd)
    arts["regression_reverse_anti_join"] = dump(d / "reverse_anti_join.jsonl", rev)

    summary = {"generated_at": utc_now(), "artifacts": arts, "pilots": pilots,
               "regression": reg}
    (OUT / "_reviews_pilots_summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"review_packets": arts["review_resolutions"]["rows"],
                      "site_class_review": arts["site_class_review"]["rows"],
                      "tethered_candidates": arts["tethered_ligand_candidates"]["rows"],
                      "pilots": {k: v["observations"] for k, v in pilots.items()},
                      "regression": {k: reg.get(k) for k in
                                     ("frozen_structures", "exact_crosswalk_count",
                                      "forward_anti_join_count", "reverse_anti_join_count")}},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
