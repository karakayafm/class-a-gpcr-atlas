#!/usr/bin/env python3
"""Phase 2 — structure-anchored normalization and ligand-entity modelling.

Produces, for all 1358 Class A structures:

  structures.normalized.jsonl          one row per structure
  receptor_instances.jsonl             one row per receptor chain instance
  entity_inventory.jsonl               one row per modelled entity (water excluded, summarised)
  ligand_candidates.jsonl              one row per ligand entity, whatever its form
  structure_ligand_observations.jsonl  structure x receptor instance x ligand entity
  source_conflicts.jsonl               where sources disagree
  manual_review_queue.jsonl            what a human must decide

Design rules this file implements, all of which are testable:

* A ligand is never selected by frequency, size or proximity. The only positive evidence for
  pharmacological relevance is a per-structure source annotation.
* Apo is never inferred from "no non-polymer component". It requires positive source evidence
  or an exhaustive exclusion over every ligand form.
* Nothing is dropped: every entity the source reports gets an inventory row, and role
  classification happens afterwards.
* Every unresolved case is emitted as unresolved and queued, not guessed.

    python3 pipeline/phase2/normalize.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))

from common.canonical import canonical_dumps, content_sha256, PARSER_VERSION   # noqa: E402
from common.http import utc_now                                                # noqa: E402

RULE_VERSION = "phase2-rules-1.0.0"
OUT = ROOT / "data/intermediate"

CFG = {n: json.loads((ROOT / f"config/{n}.json").read_text(encoding="utf-8")) for n in
       ("entity_forms", "biological_types", "ligand_roles", "site_classes",
        "analysis_eligibility", "component_reference", "polymer_role_reference")}
COMP = CFG["component_reference"]
POLY = CFG["polymer_role_reference"]

# Source ligand function -> (role, site class hint). Mapping is explicit, never inferred.
FUNCTION_ROLE = {
    "Agonist": ("pharmacological_orthosteric_ligand", "canonical_7tm_pocket"),
    "Agonist (partial)": ("pharmacological_orthosteric_ligand", "canonical_7tm_pocket"),
    "Antagonist": ("pharmacological_orthosteric_ligand", "canonical_7tm_pocket"),
    "Inverse agonist": ("pharmacological_orthosteric_ligand", "canonical_7tm_pocket"),
    "PAM": ("positive_allosteric_modulator", "unresolved"),
    "Ago-PAM": ("positive_allosteric_modulator", "unresolved"),
    "NAM": ("negative_allosteric_modulator", "unresolved"),
    "Allosteric agonist": ("pharmacological_allosteric_ligand", "unresolved"),
    "Allosteric antagonist": ("pharmacological_allosteric_ligand", "unresolved"),
    "Cofactor": ("cofactor", "unresolved"),
    "unknown": ("unresolved", "unresolved"),
    "Apo (no ligand)": (None, None),          # handled as apo evidence, not as a ligand
}
APO_FUNCTIONS = {"Apo (no ligand)"}


def jdump(path: Path, rows: list[dict]) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(canonical_dumps(r) for r in rows) + ("\n" if rows else "")
    path.write_text(text, encoding="utf-8")
    return {"path": str(path.relative_to(ROOT)), "rows": len(rows),
            "content_sha256": content_sha256(rows)}


def prov(source: str, field: str, **kw) -> dict:
    """Provenance for a derived field. A missing source is named, never silently null."""
    return {"source": source, "source_field": field, "rule_version": RULE_VERSION,
            "script": "pipeline/phase2/normalize.py", "parser_version": PARSER_VERSION, **kw}


# --------------------------------------------------------------------- component classification
def classify_component(comp_id: str, chem: dict, heavy: int | None) -> tuple[str, str, str, str]:
    """-> (biological_type, default_role, basis, evidence_detail). Never selects a ligand."""
    name = (chem.get("name") or "").upper()
    ctype = (chem.get("type") or "").lower()

    cur = COMP["curated_components"].get(comp_id)
    if cur:
        return cur[0], cur[1], "curated_component_id", cur[2]

    for r in COMP["ccd_type_rules"]:
        if r["match_ccd_type_contains"].lower() in ctype:
            return (r["biological_type"], r["default_role"], "ccd_type_rule",
                    f"CCD type '{chem.get('type')}': {r['rationale']}")

    ion = COMP["ion_rule"]
    if (heavy == 1 and name.endswith(" ION") and comp_id not in ion["excluded_ids"]):
        return "ion", "environment_ion", "ion_rule", ion["rationale"]

    for r in COMP["name_pattern_rules"]:
        if r["pattern"] in name:
            return (r["biological_type"], r["default_role"], "name_pattern_rule",
                    f"name contains '{r['pattern']}': {r['rationale']}")

    return "unknown", "unresolved", "unmatched", COMP["unmatched_policy"]


# ------------------------------------------------------------------------ polymer classification
def classify_polymer(desc: str, accs: list[str], receptor_acc: str | None,
                     length: int | None) -> tuple[str, str, str]:
    """-> (role, basis, evidence_detail). Length is reported but never decides."""
    d = (desc or "").lower()
    if receptor_acc and receptor_acc in (accs or []):
        return ("receptor", "uniprot_accession_match",
                f"entity carries the structure's receptor accession {receptor_acc}")
    for role, table in (("transducer_component", POLY["uniprot_accessions"]["transducer_component"]),
                        ("fusion_partner", POLY["uniprot_accessions"]["fusion_partner"])):
        for a in (accs or []):
            if a in table:
                return role, "curated_uniprot_accession", f"{a} = {table[a]}"
    for group in POLY["description_patterns"]:
        for pat in group["patterns"]:
            if pat in d:
                return (group["role"], "description_pattern",
                        f"description matches '{pat}' (case-insensitive)")
    for group in POLY.get("description_regex_rules", []):
        if re.match(group["regex"], d.strip()):
            return (group["role"], "description_regex",
                    f"description matches /{group['regex']}/: {group['rationale']}")
    return "unresolved", "no_identity_evidence", (
        "no receptor accession, no curated accession, no description pattern; "
        f"sequence length {length} is recorded but is not a classification criterion")


def main() -> int:
    uni = json.loads((ROOT / "data/normalized/class_a_structure_universe.json")
                     .read_text(encoding="utf-8"))
    tax = json.loads((ROOT / "data/normalized/class_a_taxonomy.json").read_text(encoding="utf-8"))
    payload = json.loads((ROOT / "data/raw/rcsb/entity_payload.json").read_text(encoding="utf-8"))
    ENTRIES = payload["entries"]
    by_entry = {r["receptor_entry_name"]: r for r in tax["receptors"]}

    structures, instances, inventory, ligands, observations = [], [], [], [], []
    conflicts, review = [], []

    for s in uni["structures"]:
        pid = s["pdb_id"]
        e = ENTRIES.get(pid)
        rec = by_entry.get(s["receptor_entry"])
        receptor_acc = rec["accession"] if rec else None
        gp = s["gpcrdb_structure_record"]
        annotations = gp["raw_ligand_annotation"] or []

        # ---------- metadata completeness, stated rather than papered over -------------------
        if e is None:
            completeness = "rcsb_metadata_absent"
            source_state = {"rcsb": "source_not_loaded", "gpcrdb": "loaded"}
        else:
            completeness = "complete"
            source_state = {"rcsb": "loaded", "gpcrdb": "loaded"}

        pe_list = (e.get("polymer_entities") or []) if e else []
        ne_list = (e.get("nonpolymer_entities") or []) if e else []
        be_list = (e.get("branched_entities") or []) if e else []
        info = (e.get("rcsb_entry_info") or {}) if e else {}

        # ---------- receptor instances ------------------------------------------------------
        receptor_instance_ids = []
        for pe in pe_list:
            ci = pe.get("rcsb_polymer_entity_container_identifiers") or {}
            accs = ci.get("uniprot_ids") or []
            desc = (pe.get("rcsb_polymer_entity") or {}).get("pdbx_description") or ""
            poly = pe.get("entity_poly") or {}
            length = poly.get("rcsb_sample_sequence_length")
            role, basis, detail = classify_polymer(desc, accs, receptor_acc, length)
            if role != "receptor":
                continue
            for auth in (ci.get("auth_asym_ids") or [None]):
                rid = f"{pid}:RI:{ci.get('entity_id')}:{auth}"
                receptor_instance_ids.append(rid)
                mutation = (pe.get("rcsb_polymer_entity") or {}).get("pdbx_mutation")
                muts = [m.strip() for m in re.split(r"[,;]", mutation) if m.strip()] if mutation else []
                fusion_accs = [a for a in accs
                               if a in POLY["uniprot_accessions"]["fusion_partner"]]
                instances.append({
                    "receptor_instance_id": rid, "pdb_id": pid,
                    "auth_asym_id": auth, "label_asym_id": (ci.get("asym_ids") or [None])[0],
                    "polymer_entity_id": ci.get("entity_id"),
                    "receptor_entry_name": s["receptor_entry"],
                    "receptor_accession": receptor_acc,
                    "species": s["species"],
                    "wild_type_accession": receptor_acc,
                    "construct_sequence_available": bool(poly.get("pdbx_seq_one_letter_code_can")),
                    "sequence_length": length,
                    "mutation_count": len(muts),
                    "mutation_list": muts,
                    "mutation_source": "rcsb:pdbx_mutation" if mutation else None,
                    "mutation_mapping_status": ("depositor_reported" if muts else
                                                "none_reported"),
                    "fusion_accessions": fusion_accs,
                    "is_chimeric_construct": bool(fusion_accs),
                    "construct_description": desc,
                    "receptor_mapping_source": basis,
                    "mapping_confidence": ("high" if basis == "uniprot_accession_match"
                                           else "chain_annotation_only"),
                    "mapping_flags": [] if basis == "uniprot_accession_match" else [basis],
                    "provenance": prov("RCSB PDB", "polymer_entities", evidence=detail),
                })
        if not receptor_instance_ids:
            # GPCRdb preferred chain is the documented fallback (polymer_role_reference)
            rid = f"{pid}:RI:fallback:{s['receptor_chain']}"
            receptor_instance_ids.append(rid)
            instances.append({
                "receptor_instance_id": rid, "pdb_id": pid,
                "auth_asym_id": s["receptor_chain"], "label_asym_id": None,
                "polymer_entity_id": None,
                "receptor_entry_name": s["receptor_entry"], "receptor_accession": receptor_acc,
                "species": s["species"], "wild_type_accession": receptor_acc,
                "construct_sequence_available": False, "sequence_length": None,
                "mutation_count": 0, "mutation_list": [], "mutation_source": None,
                "mutation_mapping_status": "source_not_loaded" if e is None else "unresolved",
                "fusion_accessions": [], "is_chimeric_construct": False,
                "construct_description": None,
                "receptor_mapping_source": "gpcrdb_preferred_chain",
                "mapping_confidence": "chain_annotation_only",
                "mapping_flags": ["no_polymer_accession_match"],
                "provenance": prov("GPCRdb", "preferred_chain",
                                   evidence="RCSB polymer entities unavailable or unmatched"),
            })
            review.append({"review_id": f"{pid}:receptor_mapping", "pdb_id": pid,
                           "category": "receptor_mapping",
                           "question": "Which polymer entity is the receptor chain?",
                           "reason": "no polymer entity carried the GPCRdb receptor accession",
                           "auto_evidence": {"gpcrdb_preferred_chain": s["receptor_chain"],
                                             "receptor_accession": receptor_acc},
                           "priority": "high" if e is not None else "blocked_source_absent"})

        primary_ri = receptor_instance_ids[0]

        # ---------- complete entity inventory ------------------------------------------------
        inv_ids_nonpoly: dict[str, list[str]] = {}
        for pe in pe_list:
            ci = pe.get("rcsb_polymer_entity_container_identifiers") or {}
            desc = (pe.get("rcsb_polymer_entity") or {}).get("pdbx_description") or ""
            poly = pe.get("entity_poly") or {}
            length = poly.get("rcsb_sample_sequence_length")
            accs = ci.get("uniprot_ids") or []
            role, basis, detail = classify_polymer(desc, accs, receptor_acc, length)
            ptype = (poly.get("rcsb_entity_polymer_type") or "").lower()
            btype = ("peptide" if ptype == "protein" and (length or 0) <
                     POLY["peptide_length_threshold"]["value"]
                     else "protein" if ptype == "protein" else "other")
            iid = f"{pid}:EI:poly:{ci.get('entity_id')}"
            inventory.append({
                "entity_inventory_id": iid, "pdb_id": pid,
                "entity_form": "polymer_chain", "biological_type": btype,
                "polymer_entity_id": ci.get("entity_id"), "nonpolymer_comp_id": None,
                "auth_asym_ids": ci.get("auth_asym_ids") or [],
                "label_asym_ids": ci.get("asym_ids") or [],
                "auth_seq_id": None, "insertion_code": None,
                "sequence_range": None, "sequence_length": length,
                "entity_description": desc, "chemical_name": None,
                "molecular_weight": (pe.get("rcsb_polymer_entity") or {}).get("formula_weight"),
                "formula": None, "ccd_type": poly.get("rcsb_entity_polymer_type"),
                "covalent_connection_status": "not_applicable_polymer",
                "source_identifiers": {"uniprot_ids": accs,
                                       "source_organism": [o.get("ncbi_scientific_name") for o in
                                                           (pe.get("rcsb_entity_source_organism") or [])]},
                "provisional_polymer_role": role,
                "role_basis": basis, "role_evidence": detail,
                "inventory_provenance": prov("RCSB PDB", "polymer_entities",
                                             rcsb_id=pe.get("rcsb_id")),
            })
        for ne in ne_list:
            ci = ne.get("rcsb_nonpolymer_entity_container_identifiers") or {}
            comp_id = ci.get("nonpolymer_comp_id")
            npc = ne.get("nonpolymer_comp") or {}
            chem = npc.get("chem_comp") or {}
            heavy = (npc.get("rcsb_chem_comp_info") or {}).get("atom_count_heavy")
            btype, drole, basis, detail = classify_component(comp_id, chem, heavy)
            insts = ne.get("nonpolymer_entity_instances") or []
            if not insts:
                insts = [{"rcsb_nonpolymer_entity_instance_container_identifiers":
                          {"auth_asym_id": (ci.get("auth_asym_ids") or [None])[0],
                           "asym_id": None, "auth_seq_id": None, "comp_id": comp_id},
                          "rcsb_nonpolymer_instance_annotation": None}]
            for inst in insts:
                ic = inst.get("rcsb_nonpolymer_entity_instance_container_identifiers") or {}
                ann = [a.get("type") for a in (inst.get("rcsb_nonpolymer_instance_annotation") or [])]
                covalent = ("covalent" if "HAS_COVALENT_LINKAGE" in ann else
                            "metal_coordination" if "HAS_METAL_COORDINATION_LINKAGE" in ann else
                            "none" if "HAS_NO_COVALENT_LINKAGE" in ann else "unknown")
                # Deterministic instance key: PDB + comp + auth chain + auth seq + icode
                iid = (f"{pid}:EI:np:{comp_id}:{ic.get('auth_asym_id')}:"
                       f"{ic.get('auth_seq_id')}:")
                inventory.append({
                    "entity_inventory_id": iid, "pdb_id": pid,
                    "entity_form": ("covalent_adduct" if covalent == "covalent"
                                    else "nonpolymer_residue"),
                    "biological_type": btype,
                    "polymer_entity_id": None, "nonpolymer_comp_id": comp_id,
                    "auth_asym_ids": [ic.get("auth_asym_id")],
                    "label_asym_ids": [ic.get("asym_id")],
                    "auth_seq_id": ic.get("auth_seq_id"), "insertion_code": None,
                    "sequence_range": None, "sequence_length": None,
                    "entity_description": (ne.get("rcsb_nonpolymer_entity") or {}).get("pdbx_description"),
                    "chemical_name": chem.get("name"),
                    "molecular_weight": chem.get("formula_weight"),
                    "formula": chem.get("formula"), "ccd_type": chem.get("type"),
                    "covalent_connection_status": covalent,
                    "covalent_annotation_types": ann,
                    "source_identifiers": {"comp_id": comp_id,
                                           "inchikey": (npc.get("rcsb_chem_comp_descriptor") or {}).get("InChIKey"),
                                           "heavy_atom_count": heavy},
                    "provisional_component_role": drole,
                    "role_basis": basis, "role_evidence": detail,
                    "inventory_provenance": prov("RCSB PDB", "nonpolymer_entity_instances",
                                                 rcsb_id=ne.get("rcsb_id"),
                                                 ccd_source="PDB Chemical Component Dictionary"),
                })
                inv_ids_nonpoly.setdefault(comp_id, []).append(iid)
        for be in be_list:
            ci = be.get("rcsb_branched_entity_container_identifiers") or {}
            iid = f"{pid}:EI:br:{ci.get('entity_id')}"
            inventory.append({
                "entity_inventory_id": iid, "pdb_id": pid,
                "entity_form": "nonpolymer_entity", "biological_type": "carbohydrate",
                "polymer_entity_id": None, "nonpolymer_comp_id": None,
                "auth_asym_ids": ci.get("auth_asym_ids") or [],
                "label_asym_ids": ci.get("asym_ids") or [],
                "auth_seq_id": None, "insertion_code": None, "sequence_range": None,
                "sequence_length": None,
                "entity_description": (be.get("rcsb_branched_entity") or {}).get("pdbx_description"),
                "chemical_name": None,
                "molecular_weight": (be.get("rcsb_branched_entity") or {}).get("formula_weight"),
                "formula": None, "ccd_type": "branched",
                "covalent_connection_status": "not_applicable_branched",
                "source_identifiers": {"branched_entity_id": ci.get("entity_id")},
                "provisional_component_role": "glycan_or_post_translational_component",
                "role_basis": "branched_entity", "role_evidence":
                    "RCSB models this as a branched (oligosaccharide) entity",
                "inventory_provenance": prov("RCSB PDB", "branched_entities",
                                             rcsb_id=be.get("rcsb_id")),
            })

        # ---------- ligand entities from positive source evidence only ----------------------
        n_pharm = 0
        unresolved_candidates = 0
        apo_annotation = any((a.get("function") in APO_FUNCTIONS) or a.get("type") == "none"
                             for a in annotations)
        unclassified_polymers = [
            inv for inv in inventory
            if inv["pdb_id"] == pid and inv["entity_form"] == "polymer_chain"
            and inv.get("provisional_polymer_role") in ("unresolved", None)]

        for idx, a in enumerate(annotations):
            fn = a.get("function")
            if fn in APO_FUNCTIONS or a.get("type") == "none":
                continue
            role, site_hint = FUNCTION_ROLE.get(fn, ("unresolved", "unresolved"))
            het = a.get("PDB")
            atype = a.get("type")
            lig_id = None
            form = "unresolved"; conf = "unresolved"; sel_ev = []; excl_ev = []
            inv_refs: list[str] = []
            mr = "not_required"; ambiguity: list[str] = []

            if het and het in inv_ids_nonpoly:
                inv_refs = inv_ids_nonpoly[het]
                covalent = any(i["covalent_connection_status"] == "covalent"
                               for i in inventory
                               if i["entity_inventory_id"] in inv_refs)
                form = "covalent_adduct" if covalent else "nonpolymer_residue"
                if covalent and role.startswith("pharmacological"):
                    role = "pharmacological_covalent_ligand"
                    site_hint = "covalent_core_site"
                conf = "source_annotated_component_match"
                # A source may annotate one component under two modes (e.g. 7CFN annotates
                # INT-777 as both Agonist and PAM). Those are two pharmacological claims about
                # the same chemistry, so both are kept and the id carries the mode.
                same_component = [x for x in annotations if x.get("PDB") == het]
                mode_suffix = (":" + str(fn).lower().replace(" ", "_")
                               if len(same_component) > 1 else "")
                sel_ev = [{"source": "GPCRdb", "field": "ligands[].PDB",
                           "value": het, "statement":
                           f"GPCRdb annotates component {het} as this structure's ligand "
                           f"with function '{fn}'"},
                          {"source": "RCSB PDB", "field": "nonpolymer_entity_instances",
                           "value": inv_refs,
                           "statement": "component is present in the deposition"}]
                lig_id = f"{pid}:LE:np:{het}{mode_suffix}"
                if mode_suffix:
                    ambiguity = ambiguity + ["component_annotated_under_multiple_modes"]
            elif het:
                form = "unresolved"; conf = "annotated_component_absent_from_deposition"
                excl_ev = [{"source": "RCSB PDB", "field": "nonpolymer_entities",
                            "statement": f"GPCRdb names component {het} but it is not among "
                                         f"the entry's non-polymer entities"}]
                ambiguity = ["annotated_component_not_in_entry"]
                mr = "required"
                lig_id = f"{pid}:LE:np:{het}"
            elif atype in ("peptide", "protein"):
                cands = unclassified_polymers
                if len(cands) == 1:
                    c = cands[0]
                    inv_refs = [c["entity_inventory_id"]]
                    form = "polymer_chain"
                    conf = "single_candidate_match"
                    role = ("endogenous_polymer_ligand" if role.startswith("pharmacological")
                            else role)
                    site_hint = "extracellular_polymer_interface"
                    sel_ev = [{"source": "GPCRdb", "field": "ligands[].type",
                               "value": atype, "statement":
                               f"GPCRdb annotates a {atype} ligand '{a.get('name')}' "
                               f"with function '{fn}'"},
                              {"source": "RCSB PDB", "field": "polymer_entities",
                               "value": c["polymer_entity_id"], "statement":
                               "exactly one polymer chain remained unclassified after receptor, "
                               "transducer, antibody and fusion identification"}]
                    lig_id = f"{pid}:LE:poly:{c['polymer_entity_id']}"
                    if sum(1 for x in annotations
                           if x.get("type") in ("peptide", "protein")) > 1:
                        lig_id += f":{idx}"
                        ambiguity = ambiguity + ["multiple_polymer_annotations_one_chain"]
                elif len(cands) > 1:
                    inv_refs = [c["entity_inventory_id"] for c in cands]
                    form = "polymer_chain"; conf = "ambiguous_multiple_candidates"
                    role = ("endogenous_polymer_ligand" if role.startswith("pharmacological")
                            else role)
                    site_hint = "extracellular_polymer_interface"
                    ambiguity = ["multiple_unclassified_polymer_chains"]
                    mr = "required"
                    sel_ev = [{"source": "GPCRdb", "field": "ligands[].type", "value": atype,
                               "statement": f"GPCRdb annotates a {atype} ligand; "
                                            f"{len(cands)} chains remain unclassified so the "
                                            f"pipeline does not choose between them"}]
                    lig_id = f"{pid}:LE:poly:ambiguous:{idx}"
                else:
                    form = "unresolved"; conf = "no_polymer_candidate"
                    ambiguity = ["annotated_polymer_ligand_without_candidate_chain"]
                    mr = "required"
                    excl_ev = [{"source": "RCSB PDB", "field": "polymer_entities",
                                "statement": "every polymer chain was identified as receptor, "
                                             "transducer, antibody or fusion; no chain remains "
                                             "for the annotated polymer ligand"}]
                    lig_id = f"{pid}:LE:poly:unmatched:{idx}"
            else:
                form = "unresolved"; conf = "unmatchable_annotation"
                ambiguity = ["source_annotation_without_identifier"]
                mr = "required"
                lig_id = f"{pid}:LE:unresolved:{idx}"

            # An annotation that could not be attached to any entity carries no evidence about
            # an entity, so it may not claim a pharmacological role. The annotation itself is
            # preserved in source_annotations and the reason in exclusion_evidence.
            if conf in ("annotated_component_absent_from_deposition", "unmatchable_annotation",
                        "no_polymer_candidate"):
                role = "unresolved"
                site_hint = "unresolved"

            pharm = role in {
                "pharmacological_orthosteric_ligand", "pharmacological_allosteric_ligand",
                "pharmacological_bitopic_ligand", "pharmacological_covalent_ligand",
                "endogenous_polymer_ligand", "tethered_ligand", "pharmacological_co_ligand",
                "positive_allosteric_modulator", "negative_allosteric_modulator",
                "silent_allosteric_modulator"}
            if pharm and conf not in ("unresolved",):
                n_pharm += 1
            if mr == "required":
                unresolved_candidates += 1
            if idx > 0 and pharm:
                ambiguity = ambiguity + ["co_occurring_pharmacological_entity"]

            elig = ("unresolved_manual_review" if mr == "required" or role == "unresolved"
                    else "eligible" if site_hint != "unresolved" else "eligible_with_warning")
            ligands.append({
                "ligand_entity_id": lig_id, "pdb_id": pid,
                "receptor_instance_id": primary_ri,
                "entity_inventory_ids": inv_refs,
                "entity_form": form,
                "biological_type": ("peptide" if atype == "peptide" else
                                    "protein" if atype == "protein" else
                                    "lipid" if atype == "lipid" else "small_molecule"),
                "ligand_role": role,
                "pharmacological_relevance": "relevant" if pharm else "not_relevant",
                "binding_mode": fn,
                "binding_site_class": site_hint or "unresolved",
                "covalent_status": ("covalent" if form == "covalent_adduct" else "none"),
                "polymer_chain_or_segment": ("whole_chain_assumed_segment_unresolved"
                                             if form == "polymer_chain" else None),
                "source_annotations": {"gpcrdb_ligand": a},
                "selection_evidence": sel_ev,
                "exclusion_evidence": excl_ev,
                "classification_confidence": conf,
                "analysis_eligibility": elig,
                "manual_review_status": mr,
                "ambiguity_flags": ambiguity,
                "provenance": prov("GPCRdb", "structure.ligands",
                                   rcsb_cross_check="RCSB PDB entity inventory",
                                   annotation_index=idx),
            })
            observations.append({
                "structure_ligand_id": f"{lig_id}::{primary_ri}",
                "pdb_id": pid, "receptor_instance_id": primary_ri,
                "ligand_entity_id": lig_id,
                "site_occurrence": len(inv_refs) if inv_refs else 0,
                "structural_state_annotation": gp.get("state"),
                "structural_transducer_annotation": s["transducer_observed_in_structure_raw"],
                "provisional_pharmacology_annotations": {
                    "source_function": fn, "source_ligand_name": a.get("name"),
                    "source_ligand_type": atype,
                    "binding_mode": None, "efficacy_at_receptor": None,
                    "pathway_specific_activity": None, "allosteric_modulation": None,
                    "database_annotation": {"provider": "GPCRdb", "function": fn},
                    "observed_structural_state": gp.get("state"),
                    "structural_transducer": s["transducer_observed_in_structure_raw"],
                    "functional_pathway_evidence": None},
                "source_conflicts": [],
                "analysis_eligibility": elig,
                "provenance": prov("GPCRdb", "structure.ligands", annotation_index=idx),
            })
            if mr == "required":
                review.append({
                    "review_id": f"{lig_id}:classification", "pdb_id": pid,
                    "category": "ligand_classification",
                    "question": "Which entity is the annotated ligand, and where does it bind?",
                    "reason": conf, "auto_evidence": {"annotation": a,
                                                      "ambiguity_flags": ambiguity},
                    "priority": "high"})

        # ---------- apo / holo, never from a zero count -------------------------------------
        forms_checked = ["nonpolymer_ligand", "peptide_polymer_ligand", "protein_ligand",
                         "covalent_ligand", "tethered_ligand", "receptor_chain_segment",
                         "multiple_pharmacological_entities"]
        if n_pharm > 0:
            ligand_status = "multi_ligand_bound" if n_pharm > 1 else "ligand_bound"
            apo_status = "not_apo"
            basis = "at least one source-annotated pharmacological ligand matched an entity"
        elif apo_annotation and unresolved_candidates == 0:
            ligand_status = "no_pharmacological_ligand_detected"
            apo_status = "confirmed_apo"
            basis = ("GPCRdb positively annotates this structure as 'Apo (no ligand)' and no "
                     "candidate of any ligand form remained unresolved")
        elif apo_annotation:
            ligand_status = "no_pharmacological_ligand_detected"
            apo_status = "probable_apo"
            basis = ("GPCRdb annotates apo, but unresolved candidates remain; apo is not "
                     "confirmed until they are reviewed")
        elif not annotations:
            ligand_status = "unresolved"; apo_status = "unresolved"
            basis = ("no source ligand annotation of any kind; absence of an annotation is not "
                     "evidence of absence of a ligand")
        else:
            ligand_status = "unresolved"; apo_status = "unresolved"
            basis = ("source annotates a ligand but no entity could be matched; apo may NOT be "
                     "inferred from this")
        if apo_status in ("probable_apo", "unresolved"):
            review.append({"review_id": f"{pid}:apo_status", "pdb_id": pid,
                           "category": "apo_assignment",
                           "question": "Is this structure genuinely apo?",
                           "reason": apo_status, "auto_evidence": {"basis": basis,
                                                                   "annotations": annotations},
                           "priority": "medium"})

        # ---------- source conflicts ---------------------------------------------------------
        for a in annotations:
            het = a.get("PDB")
            if het and e is not None and het not in inv_ids_nonpoly:
                conflicts.append({
                    "conflict_id": f"{pid}:conflict:component:{het}",
                    "pdb_id": pid, "source_conflict_type": "annotated_component_absent",
                    "source_values": {"GPCRdb": f"ligand component {het}",
                                      "RCSB PDB": sorted(inv_ids_nonpoly.keys())},
                    "chosen_value": None,
                    "decision_rule": "no automatic resolution; sources are both retained",
                    "decision_status": "unresolved",
                    "manual_review_required": True,
                    "provenance": prov("GPCRdb+RCSB", "cross_check")})
        gp_trans = s["transducer_observed_in_structure_raw"]
        rcsb_trans = [i for i in inventory if i["pdb_id"] == pid
                      and i.get("provisional_polymer_role") == "transducer_component"]
        if bool(gp_trans) != bool(rcsb_trans):
            conflicts.append({
                "conflict_id": f"{pid}:conflict:transducer",
                "pdb_id": pid, "source_conflict_type": "transducer_presence_disagreement",
                "source_values": {"GPCRdb": bool(gp_trans),
                                  "RCSB PDB": [i["entity_description"] for i in rcsb_trans]},
                "chosen_value": None,
                "decision_rule": ("both retained; GPCRdb annotates signalling proteins, RCSB "
                                  "reports deposited chains, and the two need not agree"),
                "decision_status": "recorded_not_resolved",
                "manual_review_required": False,
                "provenance": prov("GPCRdb+RCSB", "cross_check")})

        structures.append({
            "pdb_id": pid,
            "gpcrdb_structure_id": s["pdb_id"],
            "major_family_id": s["major_family_id"], "major_family_name": s["major_family_name"],
            "receptor_family_id": s["receptor_family_id"],
            "receptor_family_name": s["receptor_family_name"],
            "receptor_name": s["receptor_display_name"], "receptor_entry_name": s["receptor_entry"],
            "species": s["species"],
            "experimental_method": s["experimental_method"],
            "resolution": s["nominal_resolution"],
            "release_date": s["release_date"], "deposition_date": s["deposition_date"],
            "receptor_instances": receptor_instance_ids,
            "receptor_instance_count": len(receptor_instance_ids),
            "construct_engineering_status": (
                "chimeric_fusion" if any(i["is_chimeric_construct"] for i in instances
                                         if i["pdb_id"] == pid)
                else "mutations_reported" if any(i["mutation_count"] > 0 for i in instances
                                                 if i["pdb_id"] == pid)
                else "none_reported" if e is not None else "source_not_loaded"),
            "entity_counts": {
                "polymer": len(pe_list), "nonpolymer_entities": len(ne_list),
                "branched": len(be_list),
                "inventory_rows": sum(1 for i in inventory if i["pdb_id"] == pid)},
            "solvent_summary": {
                "solvent_entity_count": info.get("solvent_entity_count"),
                "deposited_solvent_atom_count": info.get("deposited_solvent_atom_count"),
                "note": "water is summarised at structure level, never inventoried per molecule"},
            "ligand_status": ligand_status,
            "apo_status": apo_status,
            "apo_assignment_basis": basis,
            "apo_forms_checked": forms_checked,
            "pharmacological_ligand_count": n_pharm,
            "unresolved_candidate_count": unresolved_candidates,
            "metadata_completeness": completeness,
            "structure_source_provenance": {
                "gpcrdb": s["source_urls"]["gpcrdb"], "rcsb": s["source_urls"]["rcsb"],
                "rcsb_graphql": "https://data.rcsb.org/graphql",
                "source_state": source_state},
            "structure_status": s["pdb_status"],
            "phase1_qc_flags": s["qc_flags"],
        })

    # ---------- back-annotation: what the chain finally is -------------------------------
    # provisional_polymer_role records identity evidence alone (accession / description). A
    # chain that carries no such evidence can still be established as a ligand by the
    # per-structure source annotation, which is a different kind of evidence. Both are kept:
    # the provisional field stays untouched so the reasoning remains auditable, and
    # final_polymer_role answers "what is this chain".
    lig_by_inv: dict[str, dict] = {}
    for lg in ligands:
        for iid in lg["entity_inventory_ids"]:
            lig_by_inv[iid] = lg
    for inv in inventory:
        lg = lig_by_inv.get(inv["entity_inventory_id"])
        if inv["entity_form"] != "polymer_chain":
            # A component's chemical class is its default role; a per-structure source
            # annotation overrides it. Oleic acid is membrane_lipid in 1,123 instances and the
            # annotated agonist in the four where a source says so. Both facts are kept: the
            # provisional field holds the chemistry, final_role holds the answer.
            if lg and lg["pharmacological_relevance"] == "relevant":
                inv["final_role"] = lg["ligand_role"]
                inv["final_role_basis"] = (
                    f"source_ligand_annotation:{lg['classification_confidence']}")
            else:
                inv["final_role"] = inv.get("provisional_component_role")
                inv["final_role_basis"] = inv.get("role_basis")
            continue
        if lg and lg["pharmacological_relevance"] == "relevant":
            inv["final_role"] = lg["ligand_role"]
            inv["final_role_basis"] = f"source_ligand_annotation:{lg['classification_confidence']}"
        else:
            inv["final_role"] = inv["provisional_polymer_role"]
            inv["final_role_basis"] = inv["role_basis"]
    for inv in inventory:
        if inv["entity_form"] == "polymer_chain" and inv["final_role"] == "unresolved":
            review.append({
                "review_id": f"{inv['entity_inventory_id']}:chain_role", "pdb_id": inv["pdb_id"],
                "category": "polymer_chain_role",
                "question": "What is this polymer chain?",
                "reason": "no identity evidence and no source ligand annotation matched it",
                "auto_evidence": {"description": inv["entity_description"],
                                  "uniprot_ids": inv["source_identifiers"].get("uniprot_ids"),
                                  "sequence_length": inv["sequence_length"]},
                "priority": "medium"})

    arts = {
        "structures.normalized.jsonl": jdump(OUT / "structures.normalized.jsonl", structures),
        "receptor_instances.jsonl": jdump(OUT / "receptor_instances.jsonl", instances),
        "entity_inventory.jsonl": jdump(OUT / "entity_inventory.jsonl", inventory),
        "ligand_candidates.jsonl": jdump(OUT / "ligand_candidates.jsonl", ligands),
        "structure_ligand_observations.jsonl": jdump(
            OUT / "structure_ligand_observations.jsonl", observations),
        "source_conflicts.jsonl": jdump(OUT / "source_conflicts.jsonl", conflicts),
        "manual_review_queue.jsonl": jdump(OUT / "manual_review_queue.jsonl",
                                           sorted(review, key=lambda r: r["review_id"])),
    }
    summary = {"generated_at": utc_now(), "rule_version": RULE_VERSION,
               "counts": {k: v["rows"] for k, v in arts.items()}, "artifacts": arts}
    (OUT / "_normalize_summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary["counts"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
