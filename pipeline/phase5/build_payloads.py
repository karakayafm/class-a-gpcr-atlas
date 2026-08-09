#!/usr/bin/env python3
"""Phase 5A — web payload generation from the Phase 4 and enrichment freezes.

No science is recomputed. Payload values are copied from the two validated freezes (or existing
Phase 4 aggregates), and their manifests record the exact provenance.

    python3 pipeline/phase5/build_payloads.py
"""
from __future__ import annotations
import hashlib, json, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
IN,P3,P4=ROOT/"data/intermediate",ROOT/"data/intermediate/phase3",ROOT/"data/intermediate/phase4"
ENRICH=ROOT/"data/freezes/enrichment-1.0.0"
AGG=ROOT/"data/aggregates"; WEB=ROOT/"data/web"
SCHEMA_VERSION="5.0.0"; DATA_VERSION="phase4-freeze-1.0.0+enrichment-1.0.0"
POLYMER={"extracellular_polymer_interface","tethered_ligand_interface"}
SUPERSEDED_PDB={"7XOX":"8IA7"}
CURATED_APO_STRUCTURES={"7VUY","7VUZ","7VV3","8IW1","8IW9",
  "7BW0","8XOH","8XOI","8XOJ","5WB1","8K4P"}
CURATED_APO_STRUCTURES.update({"7F1Q","7F1R","7F1T","8TLM","7T9M","7T9N","7XW7"})
# 8G94 chains F/G are CD69 antigen molecules, not pharmacological S1P1 ligands.
# Keep the receptor structure available, but do not expose the source's mistaken
# polymer-ligand/agonist annotation in filters, summaries, or the viewer.
CURATED_APO_STRUCTURES.add("8G94")
CURATED_NON_LIGAND_STRUCTURES={"8G94"}
CURATED_OBSERVED_LIGANDS={"9D3E:LE:np:A1A1W","9D3E:LE:np:EBX",
  "9D3G:LE:np:A1A2A","9D3G:LE:np:EBX",
  "6MET:LE:poly:ambiguous:0","7FIG:LE:poly:ambiguous:0","7FIG:LE:poly:ambiguous:1",
  "7FIH:LE:poly:ambiguous:0","7FIH:LE:poly:ambiguous:1",
  "7FII:LE:poly:ambiguous:0","7FII:LE:poly:ambiguous:1",
  "7T9I:LE:poly:ambiguous:0","7T9I:LE:poly:ambiguous:1",
  "7XW5:LE:poly:ambiguous:0","7XW5:LE:poly:ambiguous:1",
  "8I2G:LE:poly:ambiguous:0","8I2G:LE:poly:ambiguous:1","7UTZ:LE:np:Z41"}
CURATED_STRUCTURE_LIGANDS={
  "7XBX":{"ligand_name":"CX3CL1-like N-terminal fusion segment",
           "ligand_role":"tethered_ligand","entity_form":"tethered_ligand",
           "biological_type":"peptide","binding_mode":"Not specified",
           "binding_site_class":"tethered_ligand_interface"},
  "8U1U":{"ligand_name":"CCL1–CCR8 N-terminal fusion segment",
           "ligand_role":"tethered_ligand","entity_form":"tethered_ligand",
           "biological_type":"peptide","binding_mode":"Not specified",
           "binding_site_class":"tethered_ligand_interface"},
  "8K2X":{"ligand_name":"C-X-C motif chemokine 10","ligand_role":"endogenous_polymer_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "6MEO":{"ligand_name":"Envelope glycoprotein gp160","ligand_role":"endogenous_polymer_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "8U4Q":{"ligand_name":"REGN7663 Fab","ligand_role":"pharmacological_allosteric_ligand",
           "entity_form":"polymer_chain","binding_mode":"Not specified",
           "binding_site_class":"extracellular_polymer_interface"},
  "8U4R":{"ligand_name":"REGN7663 Fab","ligand_role":"pharmacological_allosteric_ligand",
           "entity_form":"polymer_chain","binding_mode":"Not specified",
           "binding_site_class":"extracellular_polymer_interface"},
  "8U4S":{"ligand_name":"REGN7663 Fab","ligand_role":"pharmacological_allosteric_ligand",
           "entity_form":"polymer_chain","binding_mode":"Not specified",
           "binding_site_class":"extracellular_polymer_interface"},
  "8U4T":{"ligand_name":"REGN7663 Fab","ligand_role":"pharmacological_allosteric_ligand",
           "entity_form":"polymer_chain","binding_mode":"Not specified",
           "binding_site_class":"extracellular_polymer_interface"},
  "5WB2":{"ligand_name":"CX3CL1","ligand_role":"endogenous_polymer_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "8K4O":{"ligand_name":"Growth-regulated alpha protein","ligand_role":"endogenous_polymer_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "4J4Q":{"ligand_name":"B-Octylglucoside","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_components":["BOG"]},
  "4PXF":{"ligand_name":"B-Octylglucoside","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_components":["BOG"]},
  "4X1H":{"ligand_name":"B-Nonylglucoside","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_components":["BNG"]},
  "5TE3":{"ligand_name":"B-Octylglucoside","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_components":["BOG"]},
  "5WKT":{"ligand_name":"B-Octylglucoside","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_components":["BOG"]},
  "6NWE":{"ligand_name":"B-Octylglucoside","entity_form":"nonpolymer_residue",
           "binding_site_class":"canonical_7tm_pocket","ligand_components":["BOG"]},
  "6PEL":{"ligand_name":"Citronellol","entity_form":"nonpolymer_residue",
           "ligand_components":["ODM"]},
  "6PGS":{"ligand_name":"Geraniol","entity_form":"nonpolymer_residue",
           "ligand_components":["64Z"]},
  "6PH7":{"ligand_name":"Nerol","entity_form":"nonpolymer_residue",
           "ligand_components":["NZZ"]},
  "7F6G":{"ligand_name":"SAR1-AngII","ligand_role":"endogenous_polymer_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "7X1T":{"ligand_name":"taltirelin","ligand_role":"endogenous_polymer_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "7XJL":{"ligand_name":"spexin","ligand_role":"endogenous_polymer_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "8HCQ":{"ligand_name":"Endothelin-1","ligand_role":"endogenous_polymer_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "8HCX":{"ligand_name":"Endothelin-1","ligand_role":"endogenous_polymer_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "8QJ2":{"ligand_name":"pN162","ligand_role":"pharmacological_co_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_polymer_interface"},
  "8TH4":{"ligand_name":"LSN","ligand_role":"pharmacological_orthosteric_ligand",
           "entity_form":"nonpolymer_residue","binding_site_class":"canonical_7tm_pocket"},
  "8TH3":{"ligand_name":"AT118-H Nanobody","ligand_role":"pharmacological_allosteric_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_allosteric_pocket"},
  "8QOT":{"ligand_name":"Nanobody-E","ligand_role":"pharmacological_allosteric_ligand",
           "entity_form":"polymer_chain","binding_site_class":"extracellular_allosteric_pocket"},
  "8E0G":{"ligand_name":"BU72 covalent adduct","ligand_role":"pharmacological_covalent_ligand",
           "entity_form":"covalent_adduct","binding_site_class":"covalent_core_site"},
  "8YNT":{"ligand_name":"CHEMBL242004","ligand_role":"pharmacological_orthosteric_ligand",
           "entity_form":"nonpolymer_residue","binding_site_class":"canonical_7tm_pocket"},
  "8YN7":{"ligand_name":"immethridine","ligand_role":"pharmacological_orthosteric_ligand",
           "entity_form":"nonpolymer_residue","biological_type":"small_molecule",
           "binding_mode":"Agonist","ligand_components":["A1LY2"],
           "binding_site_class":"canonical_7tm_pocket"},
  "7B6W":{"ligand_name":"(+)-cyclazosin","ligand_role":"pharmacological_orthosteric_ligand",
           "entity_form":"nonpolymer_residue","biological_type":"small_molecule",
           "binding_mode":"Inverse agonist","ligand_components":["T0B"],
           "binding_site_class":"canonical_7tm_pocket"},
  "8IRU":{"ligand_name":"rotigotine","ligand_role":"pharmacological_orthosteric_ligand",
           "entity_form":"nonpolymer_residue","biological_type":"small_molecule",
           "binding_mode":"Agonist","ligand_components":["R5F"],
           "binding_site_class":"canonical_7tm_pocket"},
}
CURATED_SITE_CLASSES={
  "5LWE:LE:np:79K":"intracellular_allosteric_pocket",
  "5T1A:LE:np:VT5":"intracellular_allosteric_pocket",
  "6LFL:LE:np:EBX":"intracellular_allosteric_pocket",
  "9D3E:LE:np:EBX":"intracellular_allosteric_pocket",
  "9D3G:LE:np:EBX":"intracellular_allosteric_pocket",
  "6QZH:LE:np:JLW":"intracellular_allosteric_pocket",
  "7FIH:LE:np:55Z":"extracellular_allosteric_pocket",
  "7XW5:LE:np:HOI":"extracellular_allosteric_pocket",
  "7XW6:LE:np:HOI":"extracellular_allosteric_pocket",
  "8I2G:LE:np:O6F":"extracellular_allosteric_pocket",
  "8JHY:LE:np:IX8":"lipid_facing_site",
  "8JII:LE:np:IX8":"lipid_facing_site",
  "7CFN:LE:np:FX0:pam":"lipid_facing_site",
  "4XNV:LE:np:BUR":"lipid_facing_site",
  "7LD3:LE:np:XTD":"lipid_facing_site",
  "7EJX:LE:np:J5F":"bitopic_or_multi_region_site",
  "8DWG:LE:np:U39":"extracellular_allosteric_pocket",
  "5NDZ:LE:np:8UN":"lipid_facing_site",
  "6C1Q:LE:np:9P2":"lipid_facing_site",
  "6C1R:LE:np:EFD":"lipid_facing_site",
  "8FN0:LE:np:SRW":"intracellular_allosteric_pocket",
  "8JPB:LE:np:SRW":"intracellular_allosteric_pocket",
  "8JPC:LE:np:SRW":"intracellular_allosteric_pocket",
  "8JPF:LE:np:SRW":"intracellular_allosteric_pocket",
  "8K9L:LE:np:VV9":"intracellular_allosteric_pocket",
  "9BJK:LE:np:A1APU":"extracellular_allosteric_pocket",
  "4MQT:LE:np:2CU":"extracellular_allosteric_pocket",
  "5X7D:LE:np:8VS":"intracellular_allosteric_pocket",
  "6N48:LE:np:KBY":"intracellular_allosteric_pocket",
  "8PKM:LE:np:T7M":"lipid_facing_site",
  "6OBA:LE:np:M3J":"lipid_facing_site",
  "6OIK:LE:np:2CU":"extracellular_allosteric_pocket",
  "7CKZ:LE:np:G4C":"lipid_facing_site",
  "7LJC:LE:np:G4C":"intracellular_allosteric_pocket",
  "7LJD:LE:np:G4C":"bitopic_or_multi_region_site",
  "7T94:LE:np:2CU":"extracellular_allosteric_pocket",
  "7T96:LE:np:2CU":"extracellular_allosteric_pocket",
  "7TRP:LE:np:IUE":"extracellular_allosteric_pocket",
  "7TRQ:LE:np:IUI":"extracellular_allosteric_pocket",
  "7V68:LE:np:2CU":"extracellular_allosteric_pocket",
  "7V6A:LE:np:5XI":"extracellular_allosteric_pocket",
  "7X2F:LE:np:G4C":"intracellular_allosteric_pocket",
  "8PJK:LE:np:T7M":"lipid_facing_site",
  "4PHU:LE:np:2YB":"bitopic_or_multi_region_site",
  "5TZR:LE:np:MK6":"bitopic_or_multi_region_site",
  "5TZY:LE:np:7OS":"bitopic_or_multi_region_site",
  "5KW2:LE:np:6XQ":"lipid_facing_site",
  "6KQI:LE:np:9GL":"lipid_facing_site",
  "7FEE:LE:np:7IC":"lipid_facing_site",
  "7WV9:LE:np:7IC":"lipid_facing_site",
  "8J20:LE:np:9T4":"intracellular_allosteric_pocket",
  "8XXU:LE:np:A1D5Q":"bitopic_or_multi_region_site",
  "8XXV:LE:np:A1D5Q":"bitopic_or_multi_region_site",
}

def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def wj(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    txt=json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    p.write_text(txt,encoding="utf-8")
    b=txt.encode("utf-8")
    return {"url":str(p.relative_to(WEB)).replace("\\","/"),"bytes":len(b),
            "sha256":hashlib.sha256(b).hexdigest()}
def f(x,n=6): return None if x is None else round(x,n)

def main()->int:
    if not (ENRICH/"freeze.json").is_file():
        raise SystemExit("missing enrichment freeze; run pipeline/enrichment/freeze_enrichment.py")
    TA={r["pdb_id"]:r for r in rd(ENRICH/"transducer_assignments.jsonl")}
    PE=rd(ENRICH/"pathway_evidence.jsonl")
    PE_by_pdb=defaultdict(list)
    for row in PE: PE_by_pdb[row["pdb_id"]].append(row)

    def panel_membership(pid,assignment):
        """Panels a structure belongs to: the structurally observed transducer plus every panel
        a positive tier-B functional assay puts it in. This mirrors the aminergic viewer, where
        panel membership is the union of the two (build_pathway_pocket_data_v15.py:374). The
        underlying fields stay separate — `transducer_class` remains structure-only and every
        evidence row keeps its own tier — so the config separation rule still holds."""
        panels=set(assignment["panels"])
        panels.update(row["panel"] for row in PE_by_pdb[pid]
                      if row["tier"]=="B" and row["panel_membership"])
        return sorted(panels)
    XREF={r["ccd"]:r for r in json.loads((ENRICH/"chemical_xrefs.json").read_text(encoding="utf-8"))}
    SREF={r["pdb_id"]:r for r in json.loads((ENRICH/"structure_references.json").read_text(encoding="utf-8"))}
    PANEL_STATS=json.loads((ENRICH/"panel_statistics.json").read_text(encoding="utf-8"))
    DB_CITATIONS=json.loads((ENRICH/"database_citations.json").read_text(encoding="utf-8"))
    SUPERSEDED=json.loads((ROOT/"config/enrichment/superseded_structures.json").read_text(encoding="utf-8"))
    SUPERSEDED_BY={pdb_id:{"pdb_id":pdb_id,**record}
                   for pdb_id,record in SUPERSEDED["structures"].items()}
    tax=json.loads((ROOT/"data/normalized/class_a_taxonomy.json").read_text(encoding="utf-8"))
    famnodes=[n for n in tax["nodes"] if n["level"]=="major_family"]
    rfam={n["source_id"]:n["name"] for n in tax["nodes"] if n["level"]=="receptor_family"}
    S={s["pdb_id"]:s for s in rd(IN/"structures.normalized.jsonl")}
    RI=rd(IN/"receptor_instances.jsonl"); EI={i["entity_inventory_id"]:i for i in rd(IN/"entity_inventory.jsonl")}
    LC={l["ligand_entity_id"]:l for l in rd(IN/"ligand_candidates.jsonl")}
    OB=rd(IN/"structure_ligand_observations.jsonl")
    # Curator-confirmed deposited pN162 chain. GPCRdb names the bound protein while reporting
    # structure-level function as apo, so retain a neutral pharmacology label instead of
    # inventing agonism or antagonism.
    LC["8QJ2:LE:poly:6"]={"ligand_entity_id":"8QJ2:LE:poly:6","entity_form":"polymer_chain",
      "entity_inventory_ids":["8QJ2:EI:poly:6"],"ligand_role":"pharmacological_co_ligand",
      "binding_mode":"Not specified","binding_site_class":"extracellular_polymer_interface",
      "biological_type":"protein","manual_review_status":"completed",
      "source_annotations":{"gpcrdb_ligand":{"name":"pN162"}}}
    OB.append({"pdb_id":"8QJ2","structure_ligand_id":"8QJ2:LE:poly:6::8QJ2:RI:5:A",
               "ligand_entity_id":"8QJ2:LE:poly:6"})
    LC["7UTZ:LE:np:Z41"]={"ligand_entity_id":"7UTZ:LE:np:Z41",
      "entity_form":"nonpolymer_residue","entity_inventory_ids":["7UTZ:EI:np:Z41:R:805:"],
      "ligand_role":"structural_lipid","binding_mode":"Not specified",
      "binding_site_class":"bitopic_or_multi_region_site","biological_type":"lipid",
      "manual_review_status":"completed",
      "source_annotations":{"gpcrdb_ligand":{"name":"Structural lipid Z41"}}}
    OB.append({"pdb_id":"7UTZ","structure_ligand_id":"7UTZ:LE:np:Z41::7UTZ:RI:4:R",
               "ligand_entity_id":"7UTZ:LE:np:Z41"})
    EL={e["structure_ligand_id"]:e for e in rd(P3/"contact_eligibility.jsonl")}
    SUMO={s["structure_ligand_id"]:s for s in rd(ROOT/"data/contacts/observation_contact_summary.jsonl")}
    ANO={a["structure_ligand_id"]:a for a in rd(P4/"annotated_not_observed.jsonl")}
    U=rd(P4/"aggregation_units.jsonl"); PREV=rd(AGG/"contact_prevalence.jsonl")
    CVR={c["major_family_id"]:c for c in rd(P4/"coverage_records.jsonl")}
    UNIV=rd(P4/"canonical_review_universe.jsonl"); ADJ={a["review_item_id"]:a for a in rd(P4/"evidence_adjudications.jsonl")}
    resolved_reviews=set(json.loads((ROOT/"config/phase5/resolved_review_items.json").read_text(
      encoding="utf-8"))["review_item_ids"])
    REMED={r["receptor_instance_id"]:r for r in rd(P4/"mapping_remediation.jsonl")}
    ASM={a["pdb_id"]:a for a in rd(P4/"assembly_context_audit.jsonl")}
    MR=rd(P4/"motif_residues.jsonl"); MM=rd(P4/"motif_metrics.jsonl")
    MSUM=rd(AGG/"motif_summaries/motif_summary.jsonl")
    STN={r["pdb_id"]:r["chosen_normalized_state"] for r in rd(P4/"structural_state_normalization.jsonl")}
    WGT=rd(AGG/"weighting_sensitivity/weighting.jsonl"); THR=rd(AGG/"threshold_sensitivity/threshold.jsonl")
    MUTC=rd(AGG/"mutation_sensitivity/cohorts.jsonl")
    LAY={n:rd(AGG/n/"aggregate.jsonl") for n in
         ("by_major_family","by_receptor_family","by_receptor","by_site_class","by_structural_state")}
    core=json.loads((ROOT/"config/phase4/motifs.core.json").read_text(encoding="utf-8"))
    geo=json.loads((ROOT/"config/phase4/motif_geometry_metrics.json").read_text(encoding="utf-8"))
    lown=json.loads((ROOT/"config/phase4/low_n_warnings.json").read_text(encoding="utf-8"))
    srcv=json.loads((ROOT/"releases/phase4/SOURCE_VERSIONS.json").read_text(encoding="utf-8"))
    lic=json.loads((ROOT/"data/licences/licence_verification_phase2.json").read_text(encoding="utf-8"))
    UNIV_by_pdb=defaultdict(list)
    for u in UNIV: UNIV_by_pdb[u["pdb_id"]].append(u)
    obs_by_pdb=defaultdict(list)
    for o in OB: obs_by_pdb[o["pdb_id"]].append(o)
    units_by_fam=defaultdict(list)
    for u in U: units_by_fam[u["major_family_id"]].append(u)
    prev_by=defaultdict(list)
    for p in PREV: prev_by[(p["major_family_id"],p["binding_site_class"])].append(p)
    mr_by_fam=defaultdict(list)
    for m in MR: mr_by_fam[m["major_family_id"]].append(m)
    mm_by_fam=defaultdict(list)
    for m in MM: mm_by_fam[m["major_family_id"]].append(m)

    manifests={}; landing_rows=[]; search_rows=[]; panel_structure_rows=[]; total_prev=0
    for node in famnodes:
        fid=node["source_id"]; slug=node["project_slug"]
        fam_s=[s for s in S.values() if s["major_family_id"]==fid]
        fam_pdbs={s["pdb_id"] for s in fam_s}
        fam_units=units_by_fam[fid]
        cov=CVR[fid]
        d=WEB/"families"/slug
        files={}

        # ---- structures index (one row per structure, observations nested) -----------------
        srows=[]
        for s in sorted(fam_s,key=lambda x:x["pdb_id"]):
            pid=s["pdb_id"]; obs=[]
            for o in sorted(obs_by_pdb[pid],key=lambda x:x["structure_ligand_id"]):
                if pid in CURATED_NON_LIGAND_STRUCTURES:
                    continue
                sl=o["structure_ligand_id"]; lg=LC[o["ligand_entity_id"]]
                sm=SUMO.get(sl); an=ANO.get(sl)
                curated=CURATED_STRUCTURE_LIGANDS.get(pid)
                viewer_obs=None
                viewer_meta=WEB/"structures"/pid/"viewer_meta.json"
                if curated and viewer_meta.exists():
                    vm=json.loads(viewer_meta.read_text(encoding="utf-8"))
                    viewer_obs=next((v for v in vm.get("observations",[])
                                     if v.get("observation_id")==sl),None)
                observed=bool(sm or curated or lg["ligand_entity_id"] in CURATED_OBSERVED_LIGANDS or
                              (viewer_obs and viewer_obs.get("ligand_selection")))
                comps=((curated or {}).get("ligand_components") or
                  sorted({EI[i]["nonpolymer_comp_id"] for i in lg["entity_inventory_ids"]
                          if i in EI and EI[i].get("nonpolymer_comp_id")}))
                obs.append({"observation_id":sl,"ligand_entity_id":lg["ligand_entity_id"],
                  "ligand_name":((curated or {}).get("ligand_name") or
                    (lg["source_annotations"].get("gpcrdb_ligand") or {}).get("name")),
                  "ligand_components":comps,
                  "ligand_role":(curated or {}).get("ligand_role",lg["ligand_role"]),
                  "entity_form":(curated or {}).get("entity_form",lg["entity_form"]),
                  "biological_type":(curated or {}).get("biological_type",lg["biological_type"]),
                  "binding_mode":(curated or {}).get("binding_mode",lg["binding_mode"]),
                  "binding_site_class":(curated or {}).get("binding_site_class",
                    CURATED_SITE_CLASSES.get(lg["ligand_entity_id"],lg["binding_site_class"])),
                  "coordinate_status":("observed" if observed else
                                       ("annotated_not_observed" if an else "no_coordinate_observation")),
                  "annotated_not_observed_detail":(an or {}).get("phase4_subclassification"),
                  "production_status":("curator_confirmed_coordinate_observation" if observed and not sm
                                       else EL.get(sl,{}).get("production_status")),
                  "generic_contact_eligibility":(sm or {}).get("generic_contact_eligibility"),
                  "receptor_residues_5A":((sm or {}).get("receptor_residues_5A") if sm else
                    len((viewer_obs or {}).get("contact_receptor_residues",[]))),
                  "receptor_residues_4_5A":(sm or {}).get("receptor_residues_4_5A"),
                  "receptor_residues_4A":(sm or {}).get("receptor_residues_4A"),
                  "ligand_residue_contacts":((sm or {}).get("ligand_residue_contact_count") if sm else
                    len((viewer_obs or {}).get("contact_ligand_residues",[]))),
                  "is_polymer_interface":(curated or {}).get("binding_site_class",
                    CURATED_SITE_CLASSES.get(lg["ligand_entity_id"],lg["binding_site_class"])) in POLYMER,
                  "manual_review_status":("completed" if curated else lg["manual_review_status"])})
            insts=[r for r in RI if r["pdb_id"]==pid]
            unval=any(REMED.get(r["receptor_instance_id"],{}).get("outcome")
                      =="mapping_unresolved_excluded_from_generic_aggregation" for r in insts)
            assignment=TA[pid]
            srows.append({"pdb_id":pid,"receptor_name":s["receptor_name"],
              "receptor_entry_name":s["receptor_entry_name"],
              "receptor_family_id":s["receptor_family_id"],
              "receptor_family_name":rfam.get(s["receptor_family_id"]),
              "species":s["species"],"experimental_method":s["experimental_method"],
              "resolution":s["resolution"],"release_date":s["release_date"],
              "structural_state":STN.get(pid),
              "structural_transducer_present":bool(s.get("phase1_qc_flags") is not None and
                                                   any(o.get("is_polymer_interface") is not None for o in obs)) if False else None,
              "apo_status":("confirmed_apo" if pid in CURATED_APO_STRUCTURES else
                            "not_apo" if pid in CURATED_STRUCTURE_LIGANDS and
                            any(o["coordinate_status"]=="observed" for o in obs)
                            else s["apo_status"]),
              "ligand_status":("no_pharmacological_ligand_detected" if pid in CURATED_APO_STRUCTURES else
                               "ligand_bound" if pid in CURATED_STRUCTURE_LIGANDS and
                                any(o["coordinate_status"]=="observed" for o in obs)
                                else s["ligand_status"]),
              "construct_engineering_status":s["construct_engineering_status"],
              "metadata_completeness":s["metadata_completeness"],
              "generic_mapping_status":("unresolved" if unval else "validated"),
              "assembly_review_status":ASM.get(pid,{}).get("outcome"),
              "human_review_items":len(UNIV_by_pdb.get(pid,[])),
              "human_review_required":sum(1 for u in UNIV_by_pdb.get(pid,[])
                                          if u["human_review_requirement"]=="required" and
                                          u["review_item_id"] not in resolved_reviews),
              "transducer_class":assignment["transducer_class"],
              "transducer_panels":panel_membership(pid,assignment),
              "transducer_panels_structural":assignment["panels"],
              "transducer_assignment_evidence":assignment["assignment_evidence"],
              "pathway_evidence_count":len(PE_by_pdb[pid]),
              "pathway_evidence_tiers":sorted({row["tier"] for row in PE_by_pdb[pid]}),
              "superseded":SUPERSEDED_BY.get(pid),
              "superseded_by":(SUPERSEDED_BY.get(pid,{}).get("replaced_by") or [None])[0],
              "observations":obs,"observation_count":len(obs),
              "has_viewer_bundle":True})
        files["structures.json"]=wj(d/"structures.json",
            {"schema":"structure_index.schema.json","schema_version":SCHEMA_VERSION,
             "family_id":fid,"family_slug":slug,"count":len(srows),"structures":srows})
        for structure in srows:
            panel_structure_rows.append({
              "pdb_id":structure["pdb_id"], "family_id":fid, "family_slug":slug,
              "family_name":node["name"], "receptor_name":structure["receptor_name"],
              "receptor_entry_name":structure["receptor_entry_name"],
              "panels":structure["transducer_panels"]})
        search_rows.extend({
          "pdb_id":s["pdb_id"],"family_slug":slug,"family_name":node["name"],
          "receptor_name":s["receptor_name"],
          "receptor_entry_name":s["receptor_entry_name"],
          "aliases":["7XOX"] if s["pdb_id"]=="8IA7" else [],
          "ligands":sorted({o["ligand_name"] for o in s["observations"] if o.get("ligand_name")})
        } for s in srows if not s.get("superseded_by"))

        # ---- receptors --------------------------------------------------------------------
        rec=defaultdict(lambda: {"structures":0,"units":0,"species":set(),"pdbs":[]})
        for s in fam_s:
            k=(s["receptor_entry_name"],s["species"])
            rec[k]["structures"]+=1; rec[k]["species"].add(s["species"])
            rec[k]["pdbs"].append(s["pdb_id"])
            rec[k]["receptor_name"]=s["receptor_name"]
            rec[k]["receptor_family_id"]=s["receptor_family_id"]
        for u in fam_units:
            k=(u["receptor_entry_name"],u["species_taxon"])
            if k in rec: rec[k]["units"]+=1
        rrows=[{"receptor_entry_name":k[0],"species":k[1],"receptor_name":v["receptor_name"],
                "receptor_family_id":v["receptor_family_id"],
                "receptor_family_name":rfam.get(v["receptor_family_id"]),
                "structure_count":v["structures"],"analysis_unit_count":v["units"],
                "pdb_ids":sorted(v["pdbs"])} for k,v in sorted(rec.items())]
        files["receptors.json"]=wj(d/"receptors.json",
            {"schema":"receptor_index","schema_version":SCHEMA_VERSION,
             "family_id":fid,"count":len(rrows),"receptors":rrows})

        # ---- contacts / interfaces, one file per site class -------------------------------
        fam_layer=[l for l in LAY["by_major_family"] if l["group_key"][0]==fid]
        recep_layer=[l for l in LAY["by_receptor"] if any(u["receptor_accession"]==l["group_key"][0]
                     and u["major_family_id"]==fid for u in U)]
        state_layer=[l for l in LAY["by_structural_state"]]
        for lay in fam_layer:
            site=lay["group_key"][1]
            raw=prev_by[(fid,site)]
            total_prev+=len(raw)
            per_recep=[{"receptor_accession":l["group_key"][0],"species":l["group_key"][1],
                        "analysis_units":l["analysis_units"],"structures":l["structures"],
                        "positions":l["positions"],"warnings":l["warnings"]}
                       for l in recep_layer if l["group_key"][2]==site
                       and any(u["receptor_accession"]==l["group_key"][0] and u["major_family_id"]==fid
                               and u["binding_site_class"]==site for u in U)]
            payload={"schema":("interface_view.schema.json" if site in POLYMER
                               else "contact_view.schema.json"),
              "schema_version":SCHEMA_VERSION,"family_id":fid,"family_slug":slug,
              "binding_site_class":site,"is_polymer_interface":site in POLYMER,
              "object_name":("receptor–ligand residue-pair interface" if site in POLYMER
                             else "small-molecule binding pocket"),
              "metric":{"id":"unit_weighted_contact_fraction_5A",
                "label_en":"Unit-weighted mean contact fraction — 5 Å",
                "label_tr":"Birim-ağırlıklı ortalama temas oranı — 5 Å",
                "definition_en":("For each analysis unit the fraction of its eligible structures "
                  "that make a 5 Å contact with a generic position is computed; the value shown "
                  "is the equally weighted mean of those fractions across analysis units."),
                "definition_tr":("Her analiz birimi içindeki uygun yapıların bir jenerik "
                  "pozisyonla 5 Å temas kurma oranı hesaplanır; gösterilen değer bu oranların "
                  "analiz birimleri üzerindeki eşit ağırlıklı ortalamasıdır."),
                "source":"data/aggregates/by_major_family/aggregate.jsonl"},
              "denominator":{"type":"analysis_units","count":lay["analysis_units"],
                "note_en":"analysis units in this family and site class",
                "note_tr":"bu aile ve site sınıfındaki analiz birimleri"},
              "analysis_units":lay["analysis_units"],"structures":lay["structures"],
              "unique_receptors":lay["unique_receptors"],"unique_ligands":lay["unique_ligands"],
              "unique_species":lay["unique_species"],
              "estimable":lay["estimable"],"warnings":lay["warnings"],
              "raw_unit_position_records":len(raw),
              "raw_records_note_en":("per-unit records are summarised here and are not shipped to "
                "the browser; they are available through CSV export"),
              "positions":lay["positions"],
              "by_receptor_url":f"{'interfaces' if site in POLYMER else 'contacts'}/{site}.by_receptor.json",
              "by_receptor_records":len(per_recep),
              "threshold_sensitivity":[t for t in THR if t["binding_site_class"]==site],
              "weighting_sensitivity":[w for w in WGT if w["binding_site_class"]==site],
              "state_stratified":[{"state":l["group_key"][0],"positions":l["positions"],
                                   "analysis_units":l["analysis_units"]}
                                  for l in state_layer if l["group_key"][1]==site]}
            sub="interfaces" if site in POLYMER else "contacts"
            files[f"{sub}/{site}.json"]=wj(d/sub/f"{site}.json",payload)
            # the per-receptor breakdown is the bulk of the payload and is only needed when a
            # user drills into a receptor, so it is a separate lazy file
            files[f"{sub}/{site}.by_receptor.json"]=wj(d/sub/f"{site}.by_receptor.json",
              {"schema":("interface_view.schema.json" if site in POLYMER
                         else "contact_view.schema.json"),
               "schema_version":SCHEMA_VERSION,"family_id":fid,"binding_site_class":site,
               "detail_level":"by_receptor","count":len(per_recep),"by_receptor":per_recep})

        # ---- motifs -----------------------------------------------------------------------
        fmr=mr_by_fam[fid]; fmm=mm_by_fam[fid]
        msum=[m for m in MSUM if m["level"]=="major_family" and m["group_key"][0]==fid]
        mrows=[]
        for m in core["motifs"]:
            sub=[r for r in fmr if r["generic_position"] in m["generic_positions"]]
            st=Counter(r["observation_status"] for r in sub)
            mets=[x for x in fmm if x["metric_type"]=="distance" and x.get("value_used")
                  and set(x["generic_positions"])<=set(m["generic_positions"])]
            vals=[x["primary_value_angstrom"] if x["value_used"]=="primary"
                  else x["fallback_min_heavy_atom_angstrom"] for x in mets]
            vals=[v for v in vals if v is not None]
            bystate=defaultdict(list)
            for x in mets:
                v=(x["primary_value_angstrom"] if x["value_used"]=="primary"
                   else x["fallback_min_heavy_atom_angstrom"])
                if v is not None: bystate[STN.get(x["pdb_id"],"unknown")].append(v)
            mrows.append({"motif_id":m["id"],"description":m["description"],
              "generic_positions":m["generic_positions"],
              "receptor_instances":len({r["receptor_instance_id"] for r in sub}),
              "structures":len({r["pdb_id"] for r in sub}),
              "canonical_identity":st.get("observed_canonical_identity",0),
              "noncanonical_identity":st.get("observed_noncanonical_identity",0),
              "expected_but_unresolved":st.get("expected_but_unresolved",0),
              "generic_mapping_unresolved":st.get("generic_mapping_unresolved",0),
              "coordinate_missing":st.get("coordinate_missing",0),
              "mutation_count":sum(1 for r in sub if r.get("mutation_flag")),
              "coverage":(msum[0]["coverage"] if msum else None),
              "metric_count":len(vals),
              "median_angstrom":f(statistics.median(vals)) if vals else None,
              "range_angstrom":[f(min(vals)),f(max(vals))] if vals else None,
              "state_stratified":{k:{"n":len(v),"median":f(statistics.median(v))}
                                  for k,v in sorted(bystate.items())},
              "association_only":True,
              "interpretation_note_en":("descriptive geometry of static experimental structures; "
                "association with source-annotated context, not causation"),
              "interpretation_note_tr":("statik deneysel yapıların betimleyici geometrisi; "
                "kaynak-anotasyonlu bağlamla ilişki, nedensellik değil")})
        pos_rows=[]
        bypos=defaultdict(list)
        for r in fmr: bypos[r["generic_position"]].append(r)
        for g,rr in sorted(bypos.items()):
            ident=Counter(r["residue_identity"] for r in rr if r["residue_identity"])
            pos_rows.append({"generic_position":g,
              "motif_memberships":rr[0]["motif_memberships"],
              "observed":sum(1 for r in rr if r["coordinate_observed"]),
              "canonical":sum(1 for r in rr if r["observation_status"]=="observed_canonical_identity"),
              "noncanonical":sum(1 for r in rr if r["observation_status"]=="observed_noncanonical_identity"),
              "unresolved":sum(1 for r in rr if r["observation_status"] in
                               ("expected_but_unresolved","generic_mapping_unresolved")),
              "residue_identities":dict(ident.most_common(8)),
              "sodium_environment":dict(Counter(r["sodium_environment"] for r in rr))})
        files["motifs.json"]=wj(d/"motifs.json",
            {"schema":"motif_view.schema.json","schema_version":SCHEMA_VERSION,
             "family_id":fid,"motif_layer":"core_class_a","motifs":mrows,"positions":pos_rows,
             "geometry_metrics":geo["distance_metrics"],
             "state_never_derived_from_geometry":True})

        # ---- coverage / reviews / references ----------------------------------------------
        files["coverage.json"]=wj(d/"coverage.json",
            {"schema":"coverage_view","schema_version":SCHEMA_VERSION,"family_id":fid,
             "dimensions":{k:cov[k] for k in ("structure_coverage","receptor_coverage",
               "observation_coverage","generic_contact_coverage","state_coverage",
               "ligand_identity_coverage","site_class_coverage")},
             "counts":{k:cov[k] for k in ("structure_count","analysis_units","unique_receptors",
                                          "unique_ligands","unique_species")},
             "warnings":cov["warnings"],"warning_thresholds":lown["thresholds"]})
        revs=[]
        for u in UNIV:
            if u["pdb_id"] not in fam_pdbs: continue
            a=ADJ.get(u["review_item_id"],{})
            revs.append({"review_item_id":u["review_item_id"],"pdb_id":u["pdb_id"],
              "issue_types":u["issue_types"],"originating_phases":u["originating_phases"],
              "automated_proposal":u["automated_proposal"],
              "evidence_adjudication":a.get("evidence_adjudication"),
              "adjudication_basis":a.get("adjudication_basis"),
              "adjudication_confidence":a.get("adjudication_confidence"),
              "adjudication_sources":a.get("adjudication_sources"),
              "human_curator_decision":("resolved_by_source_verification_and_owner_review"
                if u["review_item_id"] in resolved_reviews else None),
              "human_review_status":("completed" if u["review_item_id"] in resolved_reviews
                                     else "not_started"),
              "human_review_requirement":("not_required" if u["review_item_id"] in resolved_reviews
                                          else u["human_review_requirement"]),
              "source_conflict":any(t.startswith("source_conflict") for t in u["issue_types"])})
        files["reviews.json"]=wj(d/"reviews.json",
            {"schema":"review_view.schema.json","schema_version":SCHEMA_VERSION,"family_id":fid,
             "count":len(revs),
             "human_review_required":sum(1 for r in revs if r["human_review_requirement"]=="required"),
             "unit_of_count":"canonical_review_item",
             "label_en":"Human-review-required evidence items",
             "label_tr":"İnsan incelemesi gereken kanıt kayıtları",
             "adjudication_is_not_human_curation":True,"items":revs})
        family_ccds=sorted({ccd for row in srows for obs in row["observations"]
                            for ccd in obs.get("ligand_components",[]) if ccd in XREF})
        files["evidence.json"]=wj(d/"evidence.json",
            {"schema":"pathway_evidence_collection","schema_version":SCHEMA_VERSION,
             "family_id":fid,"count":sum(len(PE_by_pdb[p]) for p in fam_pdbs),
             "records":[row for p in sorted(fam_pdbs) for row in PE_by_pdb[p]]})
        files["ligand_xrefs.json"]=wj(d/"ligand_xrefs.json",
            {"schema":"ligand_xref_collection","schema_version":SCHEMA_VERSION,
             "family_id":fid,"count":len(family_ccds),
             "records":[XREF[ccd] for ccd in family_ccds]})
        pocket=json.loads((ENRICH/"pocket_detail"/f"{fid}.json").read_text(encoding="utf-8"))
        files["pocket_detail.json"]=wj(d/"pocket_detail.json",
          {"schema":"pocket_detail.schema.json","schema_version":SCHEMA_VERSION,**pocket})
        files["references.json"]=wj(d/"references.json",
            {"schema":"reference_payload.schema.json","schema_version":SCHEMA_VERSION,
             "family_id":fid,
             "structure_sources":[{**SREF[p],
               "rcsb_entry":f"https://www.rcsb.org/structure/{p}",
               "pdb_doi":f"https://doi.org/10.2210/pdb{p}/pdb",
               "gpcrdb_structure":f"https://gpcrdb.org/structure/{p}",
               "superseded":SUPERSEDED_BY.get(p)} for p in sorted(fam_pdbs)]})

        # ---- family summary ---------------------------------------------------------------
        sc=Counter(u["binding_site_class"] for u in fam_units)
        summary={"schema":"family_summary.schema.json","schema_version":SCHEMA_VERSION,
          "family_id":fid,"family_slug":slug,"family_name":node["name"],
          "structure_count":len(fam_s),
          "receptor_count":len({s["receptor_entry_name"] for s in fam_s}),
          "receptor_family_count":len({s["receptor_family_id"] for s in fam_s}),
          "species_count":len({s["species"] for s in fam_s}),
          "analysis_unit_count":len(fam_units),
          "site_class_counts":dict(sc),
          "state_counts":dict(Counter(u["normalized_structural_state"] for u in fam_units)),
          "coordinate_observed_ligand_observations":sum(
            1 for s in fam_s for o in obs_by_pdb[s["pdb_id"]] if o["structure_ligand_id"] in SUMO),
          "annotated_not_observed_observations":sum(
            1 for s in fam_s for o in obs_by_pdb[s["pdb_id"]] if o["structure_ligand_id"] in ANO),
          "apo_count":sum(1 for s in fam_s if s["apo_status"]=="confirmed_apo"),
          "human_review_items":len(revs),
          "human_review_required":sum(1 for r in revs if r["human_review_requirement"]=="required"),
          "coverage":{k:cov[k] for k in ("structure_coverage","receptor_coverage",
            "generic_contact_coverage","state_coverage","site_class_coverage")},
          "warnings":cov["warnings"],
          "unresolved_site_class_observations":sum(
            1 for s in fam_s for o in obs_by_pdb[s["pdb_id"]]
            if LC[o["ligand_entity_id"]]["binding_site_class"]=="unresolved")}
        files["summary.json"]=wj(d/"summary.json",summary)

        man={"schema":"family_manifest.schema.json","schema_version":SCHEMA_VERSION,
             "data_version":DATA_VERSION,"family_id":fid,"family_slug":slug,
             "family_name":node["name"],
             "files":[{"name":k,"url":v["url"],"bytes":v["bytes"],"sha256":v["sha256"],
                       "schema_version":SCHEMA_VERSION,
                       "required":k in ("summary.json","structures.json"),
                       "semantic_role":("family summary" if k=="summary.json" else
                                        "structure index" if k=="structures.json" else
                                        "receptor index" if k=="receptors.json" else
                                        "pocket contact aggregate" if k.startswith("contacts/") else
                                        "polymer interface aggregate" if k.startswith("interfaces/") else
                                        "core motif summary" if k=="motifs.json" else
                                        "coverage and warnings" if k=="coverage.json" else
                                        "evidence and review items" if k in ("reviews.json","evidence.json") else
                                        "ligand database cross-references" if k=="ligand_xrefs.json" else
                                        "residue-level pocket detail" if k=="pocket_detail.json" else
                                        "source links")}
                      for k,v in sorted(files.items())]}
        mm_=wj(d/"manifest.json",man)
        manifests[slug]={"family_id":fid,"manifest":mm_,"files":files,"summary":summary}
        landing_rows.append({"major_family_id":fid,"family_slug":slug,"family_name":node["name"],
          "structure_count":summary["structure_count"],"receptor_count":summary["receptor_count"],
          "receptor_family_count":summary["receptor_family_count"],
          "species_count":summary["species_count"],
          "analysis_unit_count":summary["analysis_unit_count"],
          "coordinate_observed_ligand_observations":summary["coordinate_observed_ligand_observations"],
          "apo_count":summary["apo_count"],"site_class_counts":summary["site_class_counts"],
          "motif_coverage":(msum[0]["coverage"] if msum else None),
          "generic_mapping_coverage":cov["generic_contact_coverage"],
          "human_review_items":summary["human_review_items"],
          "human_review_required":summary["human_review_required"],
          "warnings":cov["warnings"],
          "family_manifest_sha256":mm_["sha256"],
          "family_payload_url":f"families/{slug}/manifest.json"})

    # ------------------------------------------------------------------ global payloads
    G=WEB/"global"
    gfiles={}
    gfiles["panels.json"]=wj(G/"panels.json",
      {"schema":"panels.schema.json","schema_version":SCHEMA_VERSION,
       "source_freeze":"enrichment-1.0.0",
       "structure_index":sorted(panel_structure_rows,key=lambda r:(r["family_name"],r["pdb_id"])),
       **PANEL_STATS})
    gfiles["landing.json"]=wj(G/"landing.json",
      {"schema":"landing.schema.json","schema_version":SCHEMA_VERSION,
       "families":sorted(landing_rows,key=lambda r:-r["structure_count"]),
       "taxonomy_source":"data/normalized/class_a_taxonomy.json",
       "family_count":len(landing_rows)})
    gfiles["search_index.json"]=wj(G/"search_index.json",
      {"schema":"global_search_index","schema_version":SCHEMA_VERSION,
       "count":len(search_rows),"structures":sorted(search_rows,key=lambda r:r["pdb_id"])})
    gfiles["cross_family_summary.json"]=wj(G/"cross_family_summary.json",
      {"schema":"cross_family_summary","schema_version":SCHEMA_VERSION,
       "comparison_rule_en":("Cross-family comparison is only valid within one binding-site "
         "class, at one threshold, one weighting, one mutation cohort and one state "
         "stratification."),
       "comparison_rule_tr":("Aileler arası karşılaştırma yalnız tek bir bağlanma-bölgesi sınıfı, "
         "tek eşik, tek ağırlıklandırma, tek mutasyon kohortu ve tek durum tabakalaması içinde "
         "geçerlidir."),
       "incompatible_message_en":("These summaries use different biological objects and "
         "denominators and cannot be combined in one contact-consensus comparison."),
       "incompatible_message_tr":("Bu özetler farklı biyolojik nesneler ve paydalar kullanır; "
         "tek bir temas-konsensüs karşılaştırmasında birleştirilemez."),
       "by_site_class_url":"site_class_positions.json",
       "site_class_families":{l["group_key"][1]:[] for l in LAY["by_major_family"]} and
         {sc:sorted({l["group_key"][0] for l in LAY["by_major_family"] if l["group_key"][1]==sc})
          for sc in {l["group_key"][1] for l in LAY["by_major_family"]}}})
    gfiles["site_class_positions.json"]=wj(G/"site_class_positions.json",
      {"schema":"cross_family_positions","schema_version":SCHEMA_VERSION,
       "by_site_class":LAY["by_site_class"],
       "by_major_family":LAY["by_major_family"]})
    gfiles["motif_catalogue.json"]=wj(G/"motif_catalogue.json",
      {"schema":"motif_catalogue","schema_version":SCHEMA_VERSION,
       "layer":"core_class_a_motifs","motifs":core["motifs"],
       "all_positions":core["all_positions"],
       "identity_rule_en":core["identity_rule"],"overlap_rule_en":core["overlap_rule"],
       "geometry_metrics":geo["distance_metrics"],
       "dihedral_positions":geo["dihedral_metrics"]["positions"],
       "family_candidate_layer_active":False})
    gfiles["sources.json"]=wj(G/"sources.json",
      {"schema":"sources","schema_version":SCHEMA_VERSION,"sources":srcv["sources"],
       "licences":[{"provider":s["provider"] if isinstance(s,dict) and "provider" in s else k,
                    "status":s.get("status") if isinstance(s,dict) else None}
                   for k,s in [(k,v) for k,v in lic["sources"][0].items()][:0]] or
                  [{"provider":s["provider"],"status":s["status"],
                    "licence":s.get("licence") or s.get("owner_provided_values"),
                    "verification_method":s["verification_method"],
                    "blocks_phase_2":s["blocks_blocks"] if False else s["blocks_phase_2"]}
                   for s in lic["sources"]],
       "release_gates":lic["release_gates_still_open"],
       # Per-source role, fields used, licence and what this project did with the data.
       "source_roles":json.loads((ROOT/"config/enrichment/source_roles.json")
                                 .read_text(encoding="utf-8"))["sources"]})
    gfiles["references.json"]=wj(G/"references.json",
      {"schema":"reference_payload.schema.json","schema_version":SCHEMA_VERSION,
       "atlas":{"title":"Class A GPCR Atlas","version":"5.0.0-pre",
                "doi":None,"doi_note_en":"No DOI has been minted for this pre-release build.",
                "doi_note_tr":"Bu ön-sürüm derlemesi için DOI oluşturulmamıştır."},
       "database_citations":DB_CITATIONS,
       "pdb_doi_pattern":"https://doi.org/10.2210/pdb{PDB_ID}/pdb"})
    gfiles["release_metadata.json"]=wj(G/"release_metadata.json",
      {"schema":"release_metadata","schema_version":SCHEMA_VERSION,
       "phase":5,"pre_release":True,
       "pre_release_notice_en":("This is a pre-release research build. Some evidence items still "
         "require human review, and public redistribution remains subject to project code "
         "licensing and source-derived-data review."),
       "pre_release_notice_tr":("Bu bir ön-sürüm araştırma derlemesidir. Bazı kanıt kayıtları "
         "hâlâ insan incelemesi gerektirmektedir ve kamuya dağıtım, proje kod lisansı ile "
         "kaynak-türevli veri incelemesine tabidir."),
       "code_licence":"pending",
       "code_licence_note_en":"Code licence pending project-owner and institutional decision",
       "code_licence_note_tr":"Kod lisansı proje sahibi ve kurumsal karara kadar belirsizdir",
       "release_gates":lic["release_gates_still_open"],
       "data_freeze":"phase4+enrichment","data_version":DATA_VERSION})
    total_hr=sum(1 for u in UNIV if u["human_review_requirement"]=="required" and
                 u["review_item_id"] not in resolved_reviews)
    gm={"schema":"global_manifest.schema.json","schema_version":SCHEMA_VERSION,
      "atlas_title":"Class A GPCR Atlas","version":"5.0.0-pre","phase":5,"pre_release":True,
      "data_version":DATA_VERSION,"data_freeze_phase":"phase4+enrichment",
      "phase4_manifest_hash":content_sha256(json.loads(
        (ROOT/"releases/phase4/OUTPUT_MANIFEST.json").read_text(encoding="utf-8"))),
      "enrichment_freeze_hash":hashlib.sha256((ENRICH/"freeze.json").read_bytes()).hexdigest(),
      "schema_versions":{"payloads":SCHEMA_VERSION},
      "families":[{"family_id":r["major_family_id"],"slug":r["family_slug"],
                   "name":r["family_name"],"manifest_url":r["family_payload_url"],
                   "manifest_sha256":r["family_manifest_sha256"],
                   "manifest_bytes":manifests[r["family_slug"]]["manifest"]["bytes"],
                   "payload_bytes":sum(v["bytes"] for v in manifests[r["family_slug"]]["files"].values())}
                  for r in sorted(landing_rows,key=lambda x:-x["structure_count"])],
      "family_count":len(landing_rows),
      "structure_bundle_base":"structures/",
      "global_files":{k:v for k,v in gfiles.items()},
      "source_versions":srcv["sources"],
      "review_warning_count":total_hr,
      "review_warning_unit":"canonical_review_item",
      "licence_gates":lic["release_gates_still_open"],
      "supported_languages":["tr","en"],"supported_themes":["grey","dark"],
      "totals":{"structures":len(S),"aggregation_units":len(U),
                "aggregate_records_phase4":len(PREV),
                "aggregate_records_represented":total_prev}}
    gfiles["manifest.json"]=wj(G/"manifest.json",gm)
    (ROOT/"data/intermediate/phase5"/"_payload_build.json").write_text(json.dumps(
      {"families":{k:{"files":len(v["files"]),
                      "bytes":sum(x["bytes"] for x in v["files"].values())}
                   for k,v in manifests.items()},
       "global_bytes":sum(v["bytes"] for v in gfiles.values()),
       "aggregate_records_represented":total_prev,
       "aggregate_records_phase4":len(PREV)},indent=1),encoding="utf-8")
    print(json.dumps({"families":len(manifests),
      "global_bytes":sum(v["bytes"] for v in gfiles.values()),
      "family_bytes_total":sum(sum(x["bytes"] for x in v["files"].values()) for v in manifests.values()),
      "largest_family":max(((k,sum(x["bytes"] for x in v["files"].values())) for k,v in manifests.items()),
                           key=lambda t:t[1]),
      "aggregate_records_represented":total_prev,"phase4_records":len(PREV),
      "match":total_prev==len(PREV)},indent=1))
    return 0
if __name__=="__main__": raise SystemExit(main())
