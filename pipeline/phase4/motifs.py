#!/usr/bin/env python3
"""Phase 4B — Class A core motif extraction, residue identities and geometry.

Motif positions are GPCRdb generic numbers. Amino-acid identity is measured, never assumed:
a receptor carrying a non-canonical residue at a motif position is recorded as
`observed_noncanonical_identity`, which is a different fact from a missing position.

Geometry is descriptive. It never produces a state label or a pharmacology claim.

    python3 pipeline/phase4/motifs.py
"""
from __future__ import annotations
import json, math, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from phase3.mmcif import read, atoms, PARSER_VERSION           # noqa: E402
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402
IN, P3, P4 = ROOT/"data/intermediate", ROOT/"data/intermediate/phase3", ROOT/"data/intermediate/phase4"
RULE = "phase4-rules-1.0.0"
CFGM = json.loads((ROOT/"config/phase4/motifs.core.json").read_text(encoding="utf-8"))
CFGG = json.loads((ROOT/"config/phase4/motif_geometry_metrics.json").read_text(encoding="utf-8"))

# side-chain functional atoms, by residue type; used by the "functional atom" selection rule
FUNC = {"ARG":["NH1","NH2","NE"],"LYS":["NZ"],"ASP":["OD1","OD2"],"GLU":["OE1","OE2"],
        "ASN":["OD1","ND2"],"GLN":["OE1","NE2"],"SER":["OG"],"THR":["OG1"],"TYR":["OH"],
        "TRP":["NE1"],"HIS":["ND1","NE2"],"CYS":["SG"],"MET":["SD"]}
BACKBONE = {"N","CA","C","O","OXT"}
CHI1 = {"ARG":"CG","ASN":"CG","ASP":"CG","GLN":"CG","GLU":"CG","HIS":"CG","LEU":"CG",
        "LYS":"CG","MET":"CG","PHE":"CG","PRO":"CG","TRP":"CG","TYR":"CG",
        "ILE":"CG1","VAL":"CG1","THR":"OG1","SER":"OG","CYS":"SG"}
CHI2 = {"ARG":("CG","CD"),"ASN":("CG","OD1"),"ASP":("CG","OD1"),"GLN":("CG","CD"),
        "GLU":("CG","CD"),"HIS":("CG","ND1"),"ILE":("CG1","CD1"),"LEU":("CG","CD1"),
        "LYS":("CG","CD"),"MET":("CG","SD"),"PHE":("CG","CD1"),"TRP":("CG","CD1"),
        "TYR":("CG","CD1")}

def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def dump(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(canonical_dumps(r) for r in rows)+("\n" if rows else ""), encoding="utf-8")
    return {"rows": len(rows), "content_sha256": content_sha256(rows)}
def fnum(x): return None if x is None else round(x, 6)
def dist(a,b): return math.sqrt((a["x"]-b["x"])**2+(a["y"]-b["y"])**2+(a["z"]-b["z"])**2)

def dihedral(p1,p2,p3,p4):
    def sub(a,b): return (a["x"]-b["x"],a["y"]-b["y"],a["z"]-b["z"])
    def cross(u,v): return (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
    def dot(u,v): return sum(i*j for i,j in zip(u,v))
    def norm(u): return math.sqrt(dot(u,u))
    b1,b2,b3=sub(p2,p1),sub(p3,p2),sub(p4,p3)
    n1,n2=cross(b1,b2),cross(b2,b3)
    if norm(n1)<1e-8 or norm(n2)<1e-8: return None
    m=cross(n1,b2)
    if norm(b2)<1e-8: return None
    m=tuple(c/norm(b2) for c in m)
    x,y=dot(n1,n2),dot(m,n2)
    return math.degrees(math.atan2(y,x))

def main() -> int:
    S={s["pdb_id"]:s for s in rd(IN/"structures.normalized.jsonl")}
    # The source structural-state annotation and the structural transducer live on the GPCRdb
    # structure record in the Phase 1 universe, not on the Phase 2 structure row.
    UNI=json.loads((ROOT/"data/normalized/class_a_structure_universe.json").read_text(encoding="utf-8"))
    STATE={u["pdb_id"]:u["gpcrdb_structure_record"].get("state") for u in UNI["structures"]}
    TRANS={u["pdb_id"]:u["transducer_observed_in_structure_raw"] for u in UNI["structures"]}
    RI={r["receptor_instance_id"]:r for r in rd(IN/"receptor_instances.jsonl")}
    EI=rd(IN/"entity_inventory.jsonl")
    RM=rd(P3/"receptor_residue_mapping.jsonl")
    REMED={(r["pdb_id"],r["receptor_instance_id"]):r for r in rd(P4/"mapping_remediation.jsonl")}
    positions=set(CFGM["all_positions"])
    membership=defaultdict(list)
    for m in CFGM["motifs"]:
        for p in m["generic_positions"]: membership[p].append(m["id"])

    # sodium presence per structure, from the entity inventory (never inferred from geometry)
    na_by_pdb=defaultdict(lambda:"absent_sodium")
    for i in EI:
        if i.get("nonpolymer_comp_id")=="NA": na_by_pdb[i["pdb_id"]]="observed_sodium"
        elif i.get("nonpolymer_comp_id")=="UNX" and na_by_pdb[i["pdb_id"]]=="absent_sodium":
            na_by_pdb[i["pdb_id"]]="unresolved_ion_identity"

    # index the mapping by (instance, normalised generic position)
    def norm_gn(g):
        if not g: return None
        s=str(g)
        if "x" not in s: return s
        left,right=s.split("x",1)
        return f"{left.split('.')[0]}x{right}"
    idx=defaultdict(dict)
    for m in RM:
        g=norm_gn(m.get("display_generic_number"))
        if g in positions:
            idx[(m["pdb_id"],m["receptor_instance_id"])][g]=m

    motif_rows=[]; metric_rows=[]
    pdbs=sorted({m["pdb_id"] for m in RM})
    for n,pid in enumerate(pdbs,1):
        insts=sorted({m["receptor_instance_id"] for m in RM if m["pdb_id"]==pid})
        cif=None
        for rid in insts:
            st=S[pid]; ri=RI.get(rid,{})
            remed=REMED.get((pid,rid),{})
            found=idx.get((pid,rid),{})
            unval = remed.get("outcome")=="mapping_unresolved_excluded_from_generic_aggregation"
            if cif is None:
                A=atoms(read(ROOT/"data/cache/coordinates"/f"{pid}.cif.gz",{"_atom_site"})["_atom_site"])
                models=sorted({a["model"] for a in A}); A=[a for a in A if a["model"]==models[0]]
                by_res=defaultdict(list)
                for a in A: by_res[(a["auth_asym"],a["auth_seq"],a["ins"])].append(a)
                cif=by_res
            res_atoms={}
            for pos in sorted(positions):
                m=found.get(pos)
                if m is None:
                    status=("generic_mapping_unresolved" if unval else "expected_but_unresolved")
                    motif_rows.append({"motif_residue_id":f"{rid}|{pos}","pdb_id":pid,
                        "receptor_instance_id":rid,"major_family_id":st["major_family_id"],
                        "receptor_family_id":st["receptor_family_id"],
                        "receptor_entry_name":st["receptor_entry_name"],"species":st["species"],
                        "source_structural_state":STATE.get(pid),
                        "structural_transducer":TRANS.get(pid),
                        "generic_position":pos,"motif_memberships":membership[pos],
                        "auth_asym_id":ri.get("auth_asym_id"),"auth_seq_id":None,
                        "insertion_code":None,"residue_identity":None,
                        "wild_type_residue_identity":None,"construct_residue_identity":None,
                        "mutation_flag":None,"coordinate_observed":False,
                        "side_chain_complete":None,"backbone_complete":None,
                        "mapping_status":(m or {}).get("mapping_status") if m else
                                         ("no_validated_route" if unval else "position_not_mapped"),
                        "mapping_confidence":None,"observation_status":status,
                        "sodium_environment":na_by_pdb[pid],
                        "exclusion_flags":["generic_mapping_unresolved"] if unval else ["position_not_mapped"],
                        "provenance":{"rule_version":RULE,"parser_version":PARSER_VERSION,
                                      "source":"GPCRdb generic numbering + RCSB mmCIF"}})
                    continue
                key=(m["auth_asym_id"],m["auth_seq_id"],m["insertion_code"])
                ats=cif.get(key,[])
                res_atoms[pos]=(m,ats)
                sc=[a for a in ats if a["atom_id"] not in BACKBONE]
                obs=bool(ats)
                ident=m["residue_name"]; wt=m["wild_type_residue"]
                if not obs: status="coordinate_missing"
                elif m["mapping_status"]=="construct_or_fusion_region": status="construct_or_fusion"
                elif wt is None: status="expected_but_unresolved"
                elif ident and wt and (ident[:1]!="" ) and _one(ident)==wt: status="observed_canonical_identity"
                else: status="observed_noncanonical_identity"
                motif_rows.append({"motif_residue_id":f"{rid}|{pos}","pdb_id":pid,
                    "receptor_instance_id":rid,"major_family_id":st["major_family_id"],
                    "receptor_family_id":st["receptor_family_id"],
                    "receptor_entry_name":st["receptor_entry_name"],"species":st["species"],
                    "source_structural_state":STATE.get(pid),
                    "structural_transducer":TRANS.get(pid),
                    "generic_position":pos,"motif_memberships":membership[pos],
                    "auth_asym_id":m["auth_asym_id"],"auth_seq_id":m["auth_seq_id"],
                    "insertion_code":m["insertion_code"],"residue_identity":ident,
                    "wild_type_residue_identity":wt,
                    "construct_residue_identity":_one(ident),
                    "mutation_flag":bool(m["residue_identity_matches_wild_type"] is False),
                    "coordinate_observed":obs,
                    "side_chain_complete":bool(sc) if obs else False,
                    "backbone_complete":bool({a["atom_id"] for a in ats} >= {"N","CA","C"}) if obs else False,
                    "mapping_status":m["mapping_status"],
                    "mapping_confidence":m["mapping_confidence"],
                    "observation_status":status,
                    "sodium_environment":na_by_pdb[pid],
                    "exclusion_flags":[] if status.startswith("observed") else [status],
                    "provenance":{"rule_version":RULE,"parser_version":PARSER_VERSION,
                                  "source":"GPCRdb generic numbering + RCSB mmCIF"}})

            # ---- geometry -----------------------------------------------------------
            def pick(pos, rule):
                ent=res_atoms.get(pos)
                if not ent: return None,"position_unmapped"
                m,ats=ent
                if not ats: return None,"coordinate_missing"
                comp=m["residue_name"]
                if rule=="functional":
                    names=FUNC.get(comp)
                    sel=[a for a in ats if names and a["atom_id"] in names]
                    if sel: return sel,"side_chain_functional_atom"
                    return None,"residue_type_has_no_functional_atom"
                if rule=="hydroxyl":
                    sel=[a for a in ats if a["atom_id"]=="OH"]
                    if sel: return sel,"side_chain_hydroxyl"
                    return None,"residue_type_has_no_hydroxyl"
                if rule=="centroid":
                    sel=[a for a in ats if a["atom_id"] not in BACKBONE]
                    if sel:
                        cx=sum(a["x"] for a in sel)/len(sel); cy=sum(a["y"] for a in sel)/len(sel)
                        cz=sum(a["z"] for a in sel)/len(sel)
                        return [{"x":cx,"y":cy,"z":cz,"atom_id":"SIDECHAIN_CENTROID"}],"side_chain_centroid"
                    return None,"no_side_chain_atoms"
                return None,"unknown_rule"
            for met in CFGG["distance_metrics"]:
                p1,p2=met["generic_positions"]
                rule=("hydroxyl" if "hydroxyl" in met["atom_selection"] else
                      "centroid" if "centroid" in met["atom_selection"] else "functional")
                a1,w1=pick(p1,rule); a2,w2=pick(p2,rule)
                primary=fallback=None; used=None; note=None
                if a1 and a2:
                    primary=min(dist(x,y) for x in a1 for y in a2); used="primary"
                    note=f"{w1} / {w2}"
                e1=res_atoms.get(p1); e2=res_atoms.get(p2)
                if e1 and e2 and e1[1] and e2[1]:
                    fallback=min(dist(x,y) for x in e1[1] for y in e2[1])
                    if used is None: used="fallback"; note=f"{w1} / {w2}"
                metric_rows.append({"metric_id":f"{rid}|{met['name']}","pdb_id":pid,
                    "receptor_instance_id":rid,"major_family_id":st["major_family_id"],
                    "receptor_entry_name":st["receptor_entry_name"],"species":st["species"],
                    "source_structural_state":STATE.get(pid),
                    "metric_name":met["name"],"metric_type":"distance",
                    "generic_positions":met["generic_positions"],
                    "atom_selection_rule":met["atom_selection"],
                    "primary_value_angstrom":fnum(primary),
                    "fallback_min_heavy_atom_angstrom":fnum(fallback),
                    "value_used":used,"selection_note":note,
                    "unit":"angstrom",
                    "mutation_sensitive":any((res_atoms.get(p) or ({},))[0].get("residue_identity_matches_wild_type") is False
                                             for p in met["generic_positions"] if res_atoms.get(p)),
                    "interpretation_limit":met["interpretation_limit"],
                    "state_label_derived":False,
                    "provenance":{"rule_version":RULE,"parser_version":PARSER_VERSION}})
            for pos in CFGG["dihedral_metrics"]["positions"]:
                ent=res_atoms.get(pos)
                for ang in ("chi1","chi2"):
                    val=None; status="not_applicable"
                    if ent and ent[1]:
                        m,ats=ent; comp=m["residue_name"]
                        d={a["atom_id"]:a for a in ats}
                        if ang=="chi1" and comp in CHI1:
                            g=CHI1[comp]
                            if all(k in d for k in ("N","CA","CB",g)):
                                val=dihedral(d["N"],d["CA"],d["CB"],d[g]); status="computed"
                            else: status="coordinate_incomplete"
                        elif ang=="chi2" and comp in CHI2:
                            g,dl=CHI2[comp]
                            if all(k in d for k in ("CA","CB",g,dl)):
                                val=dihedral(d["CA"],d["CB"],d[g],d[dl]); status="computed"
                            else: status="coordinate_incomplete"
                        elif comp not in (CHI1 if ang=="chi1" else CHI2):
                            status="not_applicable"
                    elif ent: status="coordinate_missing"
                    else: status="position_unmapped"
                    metric_rows.append({"metric_id":f"{rid}|{pos}|{ang}","pdb_id":pid,
                        "receptor_instance_id":rid,"major_family_id":st["major_family_id"],
                        "receptor_entry_name":st["receptor_entry_name"],"species":st["species"],
                        "source_structural_state":STATE.get(pid),
                        "metric_name":f"{ang}_{pos}","metric_type":"dihedral",
                        "generic_positions":[pos],
                        "atom_selection_rule":CFGG["dihedral_metrics"]["atom_rules"][ang],
                        "primary_value_degrees":fnum(val),"status":status,
                        "residue_identity":(ent[0]["residue_name"] if ent else None),
                        "unit":"degrees",
                        "mutation_sensitive":bool(ent and ent[0].get("residue_identity_matches_wild_type") is False),
                        "interpretation_limit":("a rotamer is descriptive geometry; it does not "
                                                "assign a state or a ligand efficacy class"),
                        "state_label_derived":False,
                        "provenance":{"rule_version":RULE,"parser_version":PARSER_VERSION}})
        if n%200==0: print(f"  {n}/{len(pdbs)}",file=sys.stderr)

    a1=dump(P4/"motif_residues.jsonl",sorted(motif_rows,key=lambda r:r["motif_residue_id"]))
    a2=dump(P4/"motif_metrics.jsonl",sorted(metric_rows,key=lambda r:r["metric_id"]))
    print(json.dumps({"motif_residues":a1["rows"],"motif_metrics":a2["rows"],
        "observation_status":dict(Counter(r["observation_status"] for r in motif_rows)),
        "distance_metrics_with_value":sum(1 for r in metric_rows if r["metric_type"]=="distance"
                                          and r.get("value_used")),
        "dihedral_status":dict(Counter(r["status"] for r in metric_rows if r["metric_type"]=="dihedral"))},
        indent=1))
    return 0

_AA3={"ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E","GLY":"G","HIS":"H",
      "ILE":"I","LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P","SER":"S","THR":"T","TRP":"W",
      "TYR":"Y","VAL":"V","MSE":"M"}
def _one(x): return _AA3.get(x)

if __name__=="__main__":
    raise SystemExit(main())
