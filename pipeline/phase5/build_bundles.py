#!/usr/bin/env python3
"""Phase 5C — site-aware structure viewer bundles.

One bundle per PDB. It contains the receptor instance chains, every approved pharmacological
ligand entity (small molecule, polymer chain or covalent adduct), motif-relevant observed ions,
and — where the size budget allows — the auxiliary chains behind a UI toggle. It never contains
invented coordinates.

    python3 pipeline/phase5/build_bundles.py [--limit N]
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"pipeline"))
from phase3.mmcif import read, atoms                          # noqa: E402
from common.canonical import content_sha256                   # noqa: E402
IN,P3,P4=ROOT/"data/intermediate",ROOT/"data/intermediate/phase3",ROOT/"data/intermediate/phase4"
WEB=ROOT/"data/web/structures"; SCHEMA_VERSION="5.0.0"
POLYMER={"extracellular_polymer_interface","tethered_ligand_interface"}
# Deposited-chain corrections confirmed against the source entry. In 7XWO, chain D is the
# pharmacological peptide; chain F was incorrectly merged into the same ambiguous polymer
# ligand candidate and must not enter the viewer selection or its contact shell.
EXCLUDED_LIGAND_CHAINS={"7XWO":{"F"}, "3ZEV":{"D"}, "4BV0":{"D"},
                        "4RWA":{"G"}, "6UP7":{"V"}, "7W0N":{"D"},
                        "8F7Q":{"P"}, "8F7R":{"P"}, "8F7S":{"P"}, "8GY7":{"P"}}
STRUCTURE_LIGAND_OVERRIDES={
  "8HCQ":{"inventory_ids":{"8HCQ:EI:poly:5"},"ligand_chain":"L","ligand_entity":"5",
           "receptor_chain":"R","receptor_entity":"6"},
  "8HCX":{"inventory_ids":{"8HCX:EI:poly:4"},"ligand_chain":"D","ligand_entity":"4",
           "receptor_chain":"C","receptor_entity":"3"},
}
SHORTCUT_GENERIC_POSITIONS={"5x42","5x43","5x46","5x461",
                            "6x48","6x51","6x52","7x42"}
AUX_BUDGET_BYTES=450_000
PHARM={"pharmacological_orthosteric_ligand","pharmacological_allosteric_ligand",
       "pharmacological_bitopic_ligand","pharmacological_covalent_ligand",
       "endogenous_polymer_ligand","tethered_ligand","pharmacological_co_ligand",
       "positive_allosteric_modulator","negative_allosteric_modulator",
       "silent_allosteric_modulator"}
def rd(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# Categories NGL's mmCIF layer needs. A bare atom_site block fails with
# "Cannot read properties of undefined (reading 'getField')"; this set was found empirically by
# removing blocks until parsing broke, and is verified by the browser test suite.
KEEP_CATEGORIES={"DATA","entry","cell","symmetry","entity","entity_poly","entity_poly_seq",
  "struct_asym","chem_comp","struct_conn","struct_conn_type","atom_site","exptl",
  "pdbx_struct_assembly","pdbx_struct_assembly_gen","pdbx_struct_oper_list",
  "pdbx_poly_seq_scheme","pdbx_nonpoly_scheme"}


def trim_categories(lines):
    """Keep only the categories the viewer needs, preserving each block verbatim."""
    blocks=[]; cur=[]
    for l in lines:
        if l.strip()=="#":
            if cur: blocks.append(cur); cur=[]
        else: cur.append(l)
    if cur: blocks.append(cur)
    out=[]
    for b in blocks:
        name="?"
        for l in b:
            if l.startswith("data_"): name="DATA"; break
            if l.startswith("_"):
                name=l[1:].split(".",1)[0].strip(); break
        if name in KEEP_CATEGORIES:
            out.extend(b); out.append("#")
    return out


def read_source(pid):
    """Return (prefix_lines, atom_col_index, atom_rows, suffix_lines) from the deposited CIF.

    The bundle is the deposited file with unwanted atom_site rows removed, rather than a CIF
    synthesised from scratch. A synthesised file parses in some readers and fails in NGL, whose
    mmCIF layer asks for categories a bare atom_site block does not provide; keeping the real
    header also preserves entity, chem_comp and struct_conn metadata for the viewer.
    """
    data=gzip.decompress((ROOT/"data/cache/coordinates"/f"{pid}.cif.gz").read_bytes()).decode("utf-8","replace")
    lines=data.splitlines()
    i=None
    for n,l in enumerate(lines):
        if l.strip()=="loop_" and n+1<len(lines) and lines[n+1].startswith("_atom_site."):
            i=n; break
    if i is None: return lines,None,[],[]
    j=i+1; cols=[]
    while j<len(lines) and lines[j].startswith("_atom_site."):
        cols.append(lines[j].strip().split(".",1)[1]); j+=1
    k=j
    while k<len(lines) and lines[k] and not lines[k].startswith(("#","loop_","_","data_")):
        k+=1
    return lines[:j], {c:n for n,c in enumerate(cols)}, lines[j:k], lines[k:]


def split_row(line):
    out=[]; i=0; n=len(line)
    while i<n:
        while i<n and line[i] in " \t": i+=1
        if i>=n: break
        if line[i] in "'\"":
            q=line[i]; i+=1; s=i
            while i<n and not (line[i]==q and (i+1>=n or line[i+1] in " \t")): i+=1
            out.append(line[s:i]); i+=1
        else:
            s=i
            while i<n and line[i] not in " \t": i+=1
            out.append(line[s:i])
    return out


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--limit",type=int,default=None)
    args=ap.parse_args()
    S={s["pdb_id"]:s for s in rd(IN/"structures.normalized.jsonl")}
    RI=rd(IN/"receptor_instances.jsonl"); EI=rd(IN/"entity_inventory.jsonl")
    EId={i["entity_inventory_id"]:i for i in EI}
    LC={l["ligand_entity_id"]:l for l in rd(IN/"ligand_candidates.jsonl")}
    OB=rd(IN/"structure_ligand_observations.jsonl")
    SUMO={s["structure_ligand_id"]:s for s in rd(ROOT/"data/contacts/observation_contact_summary.jsonl")}
    ANO={a["structure_ligand_id"]:a for a in rd(P4/"annotated_not_observed.jsonl")}
    MR=rd(P4/"motif_residues.jsonl")
    RM=rd(P3/"receptor_residue_mapping.jsonl")
    REMED={r["receptor_instance_id"]:r for r in rd(P4/"mapping_remediation.jsonl")}
    STN={r["pdb_id"]:r["chosen_normalized_state"] for r in rd(P4/"structural_state_normalization.jsonl")}
    ri_by_pdb=defaultdict(list)
    for r in RI: ri_by_pdb[r["pdb_id"]].append(r)
    ei_by_pdb=defaultdict(list)
    for i in EI: ei_by_pdb[i["pdb_id"]].append(i)
    obs_by_pdb=defaultdict(list)
    for o in OB: obs_by_pdb[o["pdb_id"]].append(o)
    mr_by=defaultdict(list)
    for m in MR: mr_by[(m["pdb_id"],m["receptor_instance_id"])].append(m)
    rm_by=defaultdict(list)
    for r in RM: rm_by[(r["pdb_id"],r["receptor_instance_id"])].append(r)
    contacts=defaultdict(list)
    for f in sorted((ROOT/"data/contacts/by_family").glob("*/residue_pair_contacts.jsonl.gz")):
        for l in gzip.open(f,"rt"):
            c=json.loads(l); contacts[c["structure_ligand_id"]].append(c)

    idx=[]; pdbs=sorted(S)
    if args.limit: pdbs=pdbs[:args.limit]
    for n,pid in enumerate(pdbs,1):
        st=S[pid]
        pre,colidx,rows,suf=read_source(pid)
        raw=read(ROOT/"data/cache/coordinates"/f"{pid}.cif.gz",{"_atom_site"})["_atom_site"]
        A=atoms(raw)
        models=sorted({a["model"] for a in A}); model0=models[0]
        A=[a for a in A if a["model"]==model0]
        insts=ri_by_pdb[pid]
        rec_keys={(r["auth_asym_id"],str(r["polymer_entity_id"])) for r in insts}
        rec_chains={r["auth_asym_id"] for r in insts}

        def is_receptor(ch,ent,grp):
            if grp!="ATOM": return False
            for c,e in rec_keys:
                if ch==c and (not e or e=="None" or ent==e): return True
            return False

        # ligand selections per observation, from the approved Phase 2/3 records only
        lig_keys=set(); obs_meta=[]
        for o in sorted(obs_by_pdb[pid],key=lambda x:x["structure_ligand_id"]):
            slid=o["structure_ligand_id"]; lg=LC[o["ligand_entity_id"]]
            pharm=lg["ligand_role"] in PHARM
            override=STRUCTURE_LIGAND_OVERRIDES.get(pid)
            observed=slid in SUMO or override is not None
            mine=set()
            if pharm and observed:
                if lg["entity_form"] in ("nonpolymer_residue","covalent_adduct"):
                    for i in lg["entity_inventory_ids"]:
                        if i in EId and EId[i]["auth_asym_ids"]:
                            mine.add(("np",EId[i]["auth_asym_ids"][0],str(EId[i]["auth_seq_id"])))
                else:
                    inventory_ids=(override["inventory_ids"] if override else
                                   set(lg["entity_inventory_ids"]))
                    for i in inventory_ids:
                        if i in EId:
                            for ch in (EId[i]["auth_asym_ids"] or []):
                                mine.add(("poly",ch,str(EId[i]["polymer_entity_id"])))
                excluded=EXCLUDED_LIGAND_CHAINS.get(pid,set())
                if excluded: mine={k for k in mine if k[1] not in excluded}
            crows=contacts.get(slid,[])
            if override and not crows:
                receptor_atoms=defaultdict(list); ligand_atoms=defaultdict(list)
                for a in A:
                    if (a["auth_asym"]==override["receptor_chain"] and
                        a["entity"]==override["receptor_entity"]):
                        receptor_atoms[(a["auth_asym"],a["auth_seq"])].append(a)
                    elif (a["auth_asym"]==override["ligand_chain"] and
                          a["entity"]==override["ligand_entity"]):
                        ligand_atoms[(a["auth_asym"],a["auth_seq"])].append(a)
                mapping={}
                for inst in insts:
                    for m in rm_by.get((pid,inst["receptor_instance_id"]),[]):
                        mapping[(m["auth_asym_id"],str(m["auth_seq_id"]))]=m
                for (rch,rseq),ras in receptor_atoms.items():
                    for (lch,lseq),las in ligand_atoms.items():
                        d2=min((ra["x"]-la["x"])**2+(ra["y"]-la["y"])**2+
                               (ra["z"]-la["z"])**2 for ra in ras for la in las)
                        if d2>25.0: continue
                        m=mapping.get((rch,rseq),{})
                        crows.append({"receptor_auth_asym_id":rch,
                          "receptor_auth_seq_id":rseq,
                          "receptor_residue_name":ras[0]["comp"],
                          "receptor_generic_number":m.get("canonical_generic_number"),
                          "receptor_segment":m.get("protein_segment"),
                          "receptor_uniprot_position":m.get("uniprot_position"),
                          "ligand_auth_asym_id":lch,"ligand_auth_seq_id":lseq,
                          "ligand_residue_name":las[0]["comp"],
                          "min_distance_angstrom":d2**0.5})
            excluded=EXCLUDED_LIGAND_CHAINS.get(pid,set())
            if excluded: crows=[c for c in crows if c["ligand_auth_asym_id"] not in excluded]
            # A polymer entity may have symmetry-/protomer-related copies.  The contact table is
            # receptor-instance-specific, so retain only the ligand chain paired with that active
            # receptor instead of displaying every deposited copy of the entity.
            if lg["entity_form"]=="polymer_chain" and crows:
                paired={c["ligand_auth_asym_id"] for c in crows}
                mine={k for k in mine if k[0]!="poly" or k[1] in paired}
            lig_keys |= mine
            rres=sorted({(c["receptor_auth_asym_id"],c["receptor_auth_seq_id"]) for c in crows})
            lres=sorted({(c["ligand_auth_asym_id"],c["ligand_auth_seq_id"]) for c in crows})
            # Preserve the already-computed per-structure GPCRdb mapping in the viewer payload.
            # The old UI exposed this as D3x32 / ASP117; reducing it to chain:residue made the
            # binding-site list scientifically opaque even though the mapping was available.
            rdetail=[]
            for ch,seq in rres:
                hits=[c for c in crows if c["receptor_auth_asym_id"]==ch and
                      c["receptor_auth_seq_id"]==seq]
                hit=min(hits,key=lambda c:c["min_distance_angstrom"])
                rdetail.append({"auth_asym_id":ch,"auth_seq_id":seq,
                  "residue_name":hit["receptor_residue_name"],
                  "generic_position":hit.get("receptor_generic_number"),
                  "segment":hit.get("receptor_segment"),
                  "uniprot_position":hit.get("receptor_uniprot_position"),
                  "min_distance_angstrom":hit["min_distance_angstrom"]})
            obs_meta.append({"observation_id":slid,
              "ligand_entity_id":lg["ligand_entity_id"],
              "ligand_name":(lg["source_annotations"].get("gpcrdb_ligand") or {}).get("name"),
              "ligand_role":lg["ligand_role"],"entity_form":lg["entity_form"],
              "binding_site_class":lg["binding_site_class"],
              "is_polymer_interface":lg["binding_site_class"] in POLYMER,
              "coordinate_status":("observed" if observed else
                                   "annotated_not_observed" if slid in ANO else "no_observation"),
              "ligand_selection":({"chains":sorted({k[1] for k in mine}),
                 "residues":sorted([[k[1],k[2]] for k in mine if k[0]=="np"]),
                 "entities":sorted({k[2] for k in mine if k[0]=="poly"}),
                 "selection_kind":("nonpolymer" if any(k[0]=="np" for k in mine) else "polymer_chain")}
                 if mine else None),
              "contact_receptor_residues":rres,
              "contact_receptor_details":rdetail,
              "contact_ligand_residues":lres,
              "residue_pair_count":len(crows),
              "no_ligand_reason":(None if mine else
                ("annotated_not_observed" if slid in ANO else
                 "not_a_pharmacological_ligand" if not pharm else "no_coordinate_observation"))})

        def is_ligand(ch,seq,ent,grp):
            for kind,c,v in lig_keys:
                if kind=="np" and ch==c and seq==v: return True
                if kind=="poly" and ch==c and ent==v: return True
            return False

        motif=[]
        for r in insts:
            for m in mr_by.get((pid,r["receptor_instance_id"]),[]):
                if m["coordinate_observed"]:
                    motif.append({"generic_position":m["generic_position"],
                      "motif_memberships":m["motif_memberships"],
                      "auth_asym_id":m["auth_asym_id"],"auth_seq_id":m["auth_seq_id"],
                      "residue_identity":m["residue_identity"],
                      "noncanonical":m["observation_status"]=="observed_noncanonical_identity"})
        shortcut=[]
        for r in insts:
            for m in rm_by.get((pid,r["receptor_instance_id"]),[]):
                gp=m.get("canonical_generic_number")
                if not gp or "x" not in gp or not m.get("observed_atom_count"): continue
                left,right=gp.split("x",1)
                short=f"{left.split('.',1)[0]}x{right}"
                if short in SHORTCUT_GENERIC_POSITIONS:
                    shortcut.append({"generic_position":gp,"generic_short":short,
                      "auth_asym_id":m["auth_asym_id"],"auth_seq_id":m["auth_seq_id"],
                      "residue_identity":m["residue_name"]})
        na=[{"auth_asym_id":a["auth_asym"],"auth_seq_id":a["auth_seq"]} for a in A if a["comp"]=="NA"]

        # filter the deposited atom_site rows
        ci=colidx or {}
        def field(parts,name,default=""):
            k=ci.get(name)
            return parts[k] if k is not None and k<len(parts) else default
        core=[]; aux=[]
        for line in rows:
            parts=split_row(line)
            if not parts: continue
            if field(parts,"pdbx_PDB_model_num","1")!=str(model0): continue
            comp=field(parts,"label_comp_id")
            if comp in ("HOH","DOD"): continue
            grp=parts[0] if parts else "ATOM"
            ch=field(parts,"auth_asym_id") or field(parts,"label_asym_id")
            ent=field(parts,"label_entity_id")
            seq=field(parts,"auth_seq_id")
            if is_receptor(ch,ent,grp) or is_ligand(ch,seq,ent,grp) or comp=="NA":
                core.append(line)
            else:
                aux.append(line)
        body_lines=trim_categories(pre+core+suf)
        body="\n".join(body_lines)+"\n"
        aux_included=False
        if aux and len(body.encode())+sum(len(x)+1 for x in aux) <= AUX_BUDGET_BYTES:
            body_lines=trim_categories(pre+core+aux+suf)
            body="\n".join(body_lines)+"\n"; aux_included=True
        aux_chains=sorted({(split_row(l)[ci["auth_asym_id"]] if "auth_asym_id" in ci else "") for l in aux}) if aux else []
        keep=core if not aux_included else core+aux
        d=WEB/pid; d.mkdir(parents=True,exist_ok=True)
        (d/"viewer.cif").write_text(body,encoding="utf-8")
        cif_bytes=len(body.encode())
        meta={"schema":"viewer_meta.schema.json","schema_version":SCHEMA_VERSION,
          "pdb_id":pid,"coordinate_file":"viewer.cif","coordinate_bytes":cif_bytes,
          "coordinate_sha256":hashlib.sha256(body.encode()).hexdigest(),
          "receptor_name":st["receptor_name"],"receptor_entry_name":st["receptor_entry_name"],
          "species":st["species"],"major_family_id":st["major_family_id"],
          "experimental_method":st["experimental_method"],"resolution":st["resolution"],
          "structural_state":STN.get(pid),
          "apo_status":st["apo_status"],
          "receptor_instances":[{"receptor_instance_id":r["receptor_instance_id"],
            "auth_asym_id":r["auth_asym_id"],"polymer_entity_id":r["polymer_entity_id"],
            "generic_mapping":("unresolved" if REMED.get(r["receptor_instance_id"],{}).get("outcome")
                               =="mapping_unresolved_excluded_from_generic_aggregation"
                               else "validated")} for r in insts],
          "receptor_chains":sorted(rec_chains),
          "observations":obs_meta,
          "motif_residues":motif,
          "shortcut_residues":shortcut,
          "observed_sodium":na,
          "auxiliary_chains_included":aux_included,
          "auxiliary_chains":[c for c in aux_chains if c],
          "auxiliary_note_en":("Auxiliary and environment chains (antibody, nanobody, G protein, "
            "arrestin, fusion partner, detergent, buffer, bulk lipid, glycan, crystallisation "
            "additive) are hidden by default." + ("" if aux_included else
            " They are not included in this bundle because it would exceed the size budget; use "
            "the RCSB link for the full deposited structure.")),
          "auxiliary_note_tr":("Yardımcı ve çevresel zincirler (antikor, nanokor, G proteini, "
            "arrestin, füzyon ortağı, deterjan, tampon, yığın lipid, glikan ve kristalizasyon "
            "katkısı) varsayılan olarak gizlenir." + ("" if aux_included else
            " Bu bundle boyut sınırını aşacağı için bu zincirler dahil edilmemiştir; çökeltilmiş "
            "yapının tamamı için RCSB bağlantısını kullanın.")),
          "full_structure_url":f"https://www.rcsb.org/structure/{pid}",
          "invented_coordinates":False}
        (d/"viewer_meta.json").write_text(json.dumps(meta,sort_keys=True,separators=(",",":"),
                                                     ensure_ascii=False),encoding="utf-8")
        idx.append({"pdb_id":pid,"cif_bytes":cif_bytes,
                    "meta_bytes":len((d/"viewer_meta.json").read_bytes()),
                    "atoms":len(keep),"aux_included":aux_included,
                    "observations":len(obs_meta),
                    "with_ligand_selection":sum(1 for o in obs_meta if o["ligand_selection"]),
                    "sha256":meta["coordinate_sha256"]})
        if n%200==0: print(f"  {n}/{len(pdbs)}",file=sys.stderr)
    sizes=sorted(x["cif_bytes"] for x in idx)
    summary={"bundles":len(idx),"total_bytes":sum(x["cif_bytes"]+x["meta_bytes"] for x in idx),
      "cif_median":sizes[len(sizes)//2],"cif_p95":sizes[int(len(sizes)*0.95)],
      "cif_max":sizes[-1],"aux_included":sum(1 for x in idx if x["aux_included"]),
      "bundles_with_ligand_selection":sum(1 for x in idx if x["with_ligand_selection"]>0),
      "index_sha256":content_sha256(idx)}
    (ROOT/"data/intermediate/phase5"/"_bundle_index.json").write_text(
        json.dumps({"summary":summary,"bundles":idx},indent=1),encoding="utf-8")
    print(json.dumps(summary,indent=1))
    return 0
if __name__=="__main__": raise SystemExit(main())
