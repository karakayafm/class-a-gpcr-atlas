#!/usr/bin/env python3
"""Phase 4C — aggregation units, site-class-specific prevalence, coverage and sensitivity.

Small-molecule pockets and polymer interfaces are aggregated in separate tables and never share
a denominator. A unit spanning several structures is summarised by a continuous
contact_fraction_5A; binary reductions are produced alongside for comparison and none of them is
called "prevalence" on its own.

    python3 pipeline/phase4/aggregate.py
"""
from __future__ import annotations
import gzip, json, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.canonical import canonical_dumps, content_sha256   # noqa: E402
from common.http import utc_now                                # noqa: E402
IN, P3, P4 = ROOT/"data/intermediate", ROOT/"data/intermediate/phase3", ROOT/"data/intermediate/phase4"
CON, AGG = ROOT/"data/contacts", ROOT/"data/aggregates"
RULE = "phase4-rules-1.0.0"
CFGU=json.loads((ROOT/"config/phase4/aggregation_unit.json").read_text(encoding="utf-8"))
CFGW=json.loads((ROOT/"config/phase4/aggregation_weighting.json").read_text(encoding="utf-8"))
CFGD=json.loads((ROOT/"config/phase4/denominator_policy.json").read_text(encoding="utf-8"))
CFGL=json.loads((ROOT/"config/phase4/low_n_warnings.json").read_text(encoding="utf-8"))
CFGS=json.loads((ROOT/"config/phase4/structural_state_vocabulary.json").read_text(encoding="utf-8"))
TH=CFGL["thresholds"]
POLYMER_SITES={"extracellular_polymer_interface","tethered_ligand_interface"}
STATE_MAP={"Active":"active","Inactive":"inactive","Intermediate":"intermediate",
           None:"unknown","":"unknown"}

def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
def dump(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(canonical_dumps(r) for r in rows)+("\n" if rows else ""), encoding="utf-8")
    return {"rows": len(rows), "content_sha256": content_sha256(rows)}
def f(x,n=6): return None if x is None else round(x,n)
def frac(a,b): return None if not b else round(a/b,6)

def main() -> int:
    S={s["pdb_id"]:s for s in rd(IN/"structures.normalized.jsonl")}
    RI={r["receptor_instance_id"]:r for r in rd(IN/"receptor_instances.jsonl")}
    EI={i["entity_inventory_id"]:i for i in rd(IN/"entity_inventory.jsonl")}
    LC={l["ligand_entity_id"]:l for l in rd(IN/"ligand_candidates.jsonl")}
    EL={e["structure_ligand_id"]:e for e in rd(P3/"contact_eligibility.jsonl")}
    SUM={s["structure_ligand_id"]:s for s in rd(CON/"observation_contact_summary.jsonl")}
    RMD={(r["pdb_id"],r["receptor_instance_id"]):r for r in rd(P4/"mapping_remediation.jsonl")}
    # Phase 3's generic-eligibility rule ("no contacted core residue is unmapped") passes
    # VACUOUSLY for a receptor instance whose mapping route never validated: such an instance
    # has no generic numbers at all, so it has no unmapped core residues either. Phase 4 closes
    # that gap by requiring a validated route as well. Phase 3's freeze is not rewritten; the
    # correction lives here and in mapping_remediation.jsonl.
    UNVALIDATED={rid for (pid,rid),r in RMD.items()
                 if r["outcome"]=="mapping_unresolved_excluded_from_generic_aggregation"}
    def generic_ok(sl):
        return (SUM[sl]["generic_contact_eligibility"]=="yes"
                and sl.split("::")[-1] not in UNVALIDATED)
    UNI=json.loads((ROOT/"data/normalized/class_a_structure_universe.json").read_text(encoding="utf-8"))
    STATE_RAW={u["pdb_id"]:u["gpcrdb_structure_record"].get("state") for u in UNI["structures"]}
    TRANS={u["pdb_id"]:u["transducer_observed_in_structure_raw"] for u in UNI["structures"]}
    # Which generic positions EXIST (are mapped) in each receptor instance. Without this the
    # per-position denominator would be "units where the position was contacted", making every
    # contact fraction trivially 1.0 and the ranking meaningless.
    MAPPED=defaultdict(set)
    def _norm(g):
        if not g: return None
        s=str(g)
        if "x" not in s: return s
        l,r=s.split("x",1)
        return f"{l.split('.')[0]}x{r}"
    for m in rd(P3/"receptor_residue_mapping.jsonl"):
        if m.get("display_generic_number"):
            MAPPED[m["receptor_instance_id"]].add(m["display_generic_number"])
    contacts=[]
    for fp in sorted((CON/"by_family").glob("*/residue_pair_contacts.jsonl.gz")):
        contacts += [json.loads(l) for l in gzip.open(fp,"rt")]
    by_obs=defaultdict(list)
    for c in contacts: by_obs[c["structure_ligand_id"]].append(c)

    # ------------------------------------------------------------- structural state
    state_rows=[]
    for pid,st in sorted(S.items()):
        raw=STATE_RAW.get(pid)
        norm=STATE_MAP.get(raw,"unknown")
        state_rows.append({"pdb_id":pid,"gpcrdb_state":raw,"depositor_annotation":None,
            "transducer_presence":bool(TRANS.get(pid)),"source_publication":None,
            "chosen_normalized_state":norm,
            "decision_rule":("mapped from the GPCRdb state annotation only; a transducer-bound "
                             "structure is NOT relabelled active on that basis"),
            "conflict_status":"no_conflict_detected",
            "derived_from_motif_geometry":False})
    dump(P4/"structural_state_normalization.jsonl",state_rows)
    STATE={r["pdb_id"]:r["chosen_normalized_state"] for r in state_rows}

    # ------------------------------------------------------------- aggregation units
    units=defaultdict(list)
    excl=Counter()
    for sl,o in SUM.items():
        lg=LC[o["structure_ligand_id"].split("::")[0]]
        rid=o["structure_ligand_id"].split("::")[-1]
        ri=RI.get(rid,{}); pid=o["pdb_id"]
        site=o["binding_site_class"]
        if site=="unresolved": excl["site_class_unresolved"]+=1; continue
        if lg["classification_confidence"] in ("ambiguous_multiple_candidates",
                                               "no_polymer_candidate","unmatchable_annotation",
                                               "annotated_component_absent_from_deposition"):
            excl["ligand_identity_unresolved"]+=1; continue
        # normalized ligand identity: chem component for non-polymer, UniProt/description for polymer
        comps=sorted({EI[i]["nonpolymer_comp_id"] for i in lg["entity_inventory_ids"]
                      if i in EI and EI[i].get("nonpolymer_comp_id")})
        if comps: lid=("component:"+"+".join(comps))
        else:
            accs=sorted({a for i in lg["entity_inventory_ids"] if i in EI
                         for a in (EI[i]["source_identifiers"].get("uniprot_ids") or [])})
            desc=sorted({EI[i]["entity_description"] for i in lg["entity_inventory_ids"] if i in EI})
            lid=("uniprot:"+"+".join(accs)) if accs else ("description:"+"|".join(d or "" for d in desc))
        key=(ri.get("receptor_accession"),S[pid]["species"],lid,lg["entity_form"],site,STATE[pid])
        units[key].append((sl,o,lg,pid,rid))
    unit_rows=[]
    for key,members in sorted(units.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        acc,sp,lid,form,site,state=key
        pdbs=sorted({m[3] for m in members})
        gen_ok=[m for m in members if generic_ok(m[0])]
        unit_rows.append({
            "aggregation_unit_id":f"{acc}|{sp}|{lid}|{form}|{site}|{state}",
            "receptor_accession":acc,"species_taxon":sp,"normalized_ligand_identity":lid,
            "ligand_entity_form":form,"binding_site_class":site,
            "normalized_structural_state":state,
            "is_polymer_interface":site in POLYMER_SITES,
            "major_family_id":S[members[0][3]]["major_family_id"],
            "receptor_family_id":S[members[0][3]]["receptor_family_id"],
            "receptor_entry_name":S[members[0][3]]["receptor_entry_name"],
            "structures":pdbs,"structures_total":len(pdbs),
            "observations":sorted(m[0] for m in members),
            "observations_total":len(members),
            "generic_eligible_observations":len(gen_ok),
            "state_stratifiable":state!="unknown",
            "generic_aggregation_eligible":len(gen_ok)>0})
    a_units=dump(P4/"aggregation_units.jsonl",unit_rows)

    # ---------------------------------------- per unit x generic position contact table
    prev_rows=[]
    for u in unit_rows:
        if not u["generic_aggregation_eligible"]: continue
        obs=[o for o in u["observations"] if generic_ok(o)]
        n=len(obs)
        # denominator: positions present in the receptor across this unit's observations
        available=set()
        for sl in obs:
            available |= MAPPED.get(sl.split("::")[-1], set())
        pos_data={g:{"4":set(),"45":set(),"5":set(),"d":[]} for g in available}
        for sl in obs:
            seen=defaultdict(list)
            for c in by_obs[sl]:
                g=c["receptor_generic_number"]
                if not g: continue
                seen[g].append(c["min_distance_angstrom"])
            for g,ds in seen.items():
                md=min(ds); p=pos_data.setdefault(g,{"4":set(),"45":set(),"5":set(),"d":[]})
                if md<=4.0: p["4"].add(sl)
                if md<=4.5: p["45"].add(sl)
                if md<=5.0: p["5"].add(sl)
                p["d"].append(md)
        for g,p in sorted(pos_data.items()):
            if not p["5"] and not p["d"] and g not in available:
                continue
            ds=sorted(p["d"])
            q1=statistics.quantiles(ds,n=4)[0] if len(ds)>3 else (ds[0] if ds else None)
            q3=statistics.quantiles(ds,n=4)[2] if len(ds)>3 else (ds[-1] if ds else None)
            f5=frac(len(p["5"]),n)
            prev_rows.append({
                "aggregation_unit_id":u["aggregation_unit_id"],
                "binding_site_class":u["binding_site_class"],
                "is_polymer_interface":u["is_polymer_interface"],
                "major_family_id":u["major_family_id"],
                "receptor_family_id":u["receptor_family_id"],
                "receptor_accession":u["receptor_accession"],"species_taxon":u["species_taxon"],
                "normalized_ligand_identity":u["normalized_ligand_identity"],
                "normalized_structural_state":u["normalized_structural_state"],
                "generic_position":g,
                "structures_total":u["structures_total"],
                "structures_contact_eligible":n,
                "structures_with_contact_4A":len(p["4"]),
                "structures_with_contact_4_5A":len(p["45"]),
                "structures_with_contact_5A":len(p["5"]),
                "contact_fraction_4A":frac(len(p["4"]),n),
                "contact_fraction_4_5A":frac(len(p["45"]),n),
                "contact_fraction_5A":f5,
                "contact_any_5A":len(p["5"])>0,
                "contact_all_5A":len(p["5"])==n,
                "min_distance":f(min(ds)) if ds else None,
                "median_min_distance":f(statistics.median(ds)) if ds else None,
                "distance_IQR":f(q3-q1) if (q1 is not None and q3 is not None) else None,
                "structure_heterogeneity_flag":bool(n>1 and 0<len(p["5"])<n),
                "position_mapped_in_unit":g in available,
                "denominator_type":"generic_eligible_observations_in_unit_where_position_is_mapped",
                "denominator_count":n,
                "numerator_definition":("observations whose minimum heavy-atom distance at this "
                    "generic position is within the threshold; positions mapped but never "
                    "contacted are retained with a zero numerator so the denominator is the "
                    "receptor's mappable positions, not the contacted ones"),
                "primary_metric":"contact_fraction_5A"})
    a_prev=dump(AGG/"contact_prevalence.jsonl",prev_rows)

    # ------------------------------------------------------------------ aggregation layers
    def layer(name, keyfn, rows):
        out=defaultdict(list)
        for r in rows: out[keyfn(r)].append(r)
        res=[]
        for k,v in sorted(out.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
            units_n=len({r["aggregation_unit_id"] for r in v})
            recs={r["receptor_accession"] for r in v}
            ligs={r["normalized_ligand_identity"] for r in v}
            spp={r["species_taxon"] for r in v}
            structs=sum({r["aggregation_unit_id"]:r["structures_total"] for r in v}.values())
            byp=defaultdict(list)
            for r in v: byp[r["generic_position"]].append(r)
            positions=[]
            for g,rr in sorted(byp.items()):
                fr=[x["contact_fraction_5A"] for x in rr if x["contact_fraction_5A"] is not None]
                positions.append({"generic_position":g,
                    "units":len(rr),
                    "units_with_any_contact":sum(1 for x in rr if x["contact_any_5A"]),
                    "unit_weighted_contact_fraction_5A":f(statistics.mean(fr)) if fr else None,
                    "unit_weighted_contact_fraction_4A":f(statistics.mean(
                        [x["contact_fraction_4A"] for x in rr if x["contact_fraction_4A"] is not None])) if fr else None,
                    "unit_weighted_contact_fraction_4_5A":f(statistics.mean(
                        [x["contact_fraction_4_5A"] for x in rr if x["contact_fraction_4_5A"] is not None])) if fr else None,
                    "unit_weighted_any_contact":f(statistics.mean([1.0 if x["contact_any_5A"] else 0.0 for x in rr])),
                    "structure_weighted_binary":f(sum(x["structures_with_contact_5A"] for x in rr)/
                                                  max(sum(x["structures_contact_eligible"] for x in rr),1)),
                    "median_min_distance":f(statistics.median([x["median_min_distance"] for x in rr
                                                               if x["median_min_distance"] is not None]))
                        if any(x["median_min_distance"] is not None for x in rr) else None})
            warn=[]
            if structs<TH["low_structure_count"]: warn.append("low_structure_count")
            if units_n<TH["low_analysis_unit_count"]: warn.append("low_analysis_unit_count")
            if len(recs)<TH["low_receptor_count"]: warn.append("low_receptor_count")
            cr=Counter(r["receptor_accession"] for r in v)
            if cr and cr.most_common(1)[0][1]/len(v)>=TH["single_receptor_dominance_fraction"]:
                warn.append("single_receptor_dominated")
            cl=Counter(r["normalized_ligand_identity"] for r in v)
            if cl and cl.most_common(1)[0][1]/len(v)>=TH["single_ligand_dominance_fraction"]:
                warn.append("single_ligand_dominated")
            cs=Counter(r["species_taxon"] for r in v)
            if cs and cs.most_common(1)[0][1]/len(v)>=TH["single_species_dominance_fraction"]:
                warn.append("single_species_dominated")
            res.append({"layer":name,"group_key":[str(x) for x in (k if isinstance(k,tuple) else (k,))],
                "analysis_units":units_n,"structures":structs,
                "unique_receptors":len(recs),"unique_ligands":len(ligs),"unique_species":len(spp),
                "positions_reported":len(positions),"positions":positions,
                "denominator_type":"analysis_units","denominator_count":units_n,
                "estimable":units_n>0,"warnings":warn})
        return res

    layers={
      "by_major_family":layer("major_family x site_class",
        lambda r:(r["major_family_id"],r["binding_site_class"]),prev_rows),
      "by_receptor_family":layer("receptor_family x site_class",
        lambda r:(r["receptor_family_id"],r["binding_site_class"]),prev_rows),
      "by_receptor":layer("receptor x species x site_class",
        lambda r:(r["receptor_accession"],r["species_taxon"],r["binding_site_class"]),prev_rows),
      "by_site_class":layer("site_class",lambda r:(r["binding_site_class"],),prev_rows),
      "by_structural_state":layer("state x site_class",
        lambda r:(r["normalized_structural_state"],r["binding_site_class"]),
        [r for r in prev_rows if r["normalized_structural_state"]!="unknown"]),
    }
    for name,rows in layers.items():
        dump(AGG/name/"aggregate.jsonl",rows)

    # ------------------------------------------------------------------ weighting sensitivity
    wrows=[]
    for site in sorted({r["binding_site_class"] for r in prev_rows}):
        sub=[r for r in prev_rows if r["binding_site_class"]==site]
        byp=defaultdict(list)
        for r in sub: byp[r["generic_position"]].append(r)
        schemes={}
        for g,rr in byp.items():
            fr=[x["contact_fraction_5A"] for x in rr if x["contact_fraction_5A"] is not None]
            schemes.setdefault("unit_weighted_continuous",{})[g]=statistics.mean(fr) if fr else 0.0
            schemes.setdefault("unit_weighted_any_contact",{})[g]=statistics.mean(
                [1.0 if x["contact_any_5A"] else 0.0 for x in rr])
            schemes.setdefault("structure_weighted_binary",{})[g]=(
                sum(x["structures_with_contact_5A"] for x in rr)/
                max(sum(x["structures_contact_eligible"] for x in rr),1))
            byr=defaultdict(list)
            for x in rr: byr[x["receptor_accession"]].append(x["contact_fraction_5A"] or 0.0)
            schemes.setdefault("receptor_weighted",{})[g]=statistics.mean(
                [statistics.mean(v) for v in byr.values()])
            byl=defaultdict(list)
            for x in rr: byl[x["normalized_ligand_identity"]].append(x["contact_fraction_5A"] or 0.0)
            schemes.setdefault("ligand_weighted",{})[g]=statistics.mean(
                [statistics.mean(v) for v in byl.values()])
        ranks={k:[g for g,_ in sorted(v.items(),key=lambda kv:(-kv[1],kv[0]))] for k,v in schemes.items()}
        base=ranks["unit_weighted_continuous"]
        for k,r_ in ranks.items():
            top10=set(base[:10]); overlap=len(top10 & set(r_[:10]))
            moved=sum(1 for i,g in enumerate(base) if r_.index(g)!=i)
            wrows.append({"binding_site_class":site,"scheme":k,
                "positions":len(base),"top10_overlap_with_unit_weighted":overlap,
                "positions_changing_rank":moved,
                "top10":r_[:10],
                "recommended":k=="unit_weighted_continuous",
                "note":"no weighting is presented as the single correct one"})
    dump(AGG/"weighting_sensitivity/weighting.jsonl",wrows)

    # ------------------------------------------------------------------ threshold sensitivity
    trows=[]
    for site in sorted({r["binding_site_class"] for r in prev_rows}):
        sub=[r for r in prev_rows if r["binding_site_class"]==site]
        for th,key in (("4.0A","contact_fraction_4A"),("4.5A","contact_fraction_4_5A"),
                       ("5.0A","contact_fraction_5A")):
            vals=[r[key] for r in sub if r[key] is not None]
            pos_any=len({r["generic_position"] for r in sub if (r[key] or 0)>0})
            trows.append({"binding_site_class":site,"threshold":th,
                "records":len(sub),"positions_with_any_contact":pos_any,
                "mean_contact_fraction":f(statistics.mean(vals)) if vals else None,
                "median_contact_fraction":f(statistics.median(vals)) if vals else None})
    dump(AGG/"threshold_sensitivity/threshold.jsonl",trows)

    # ------------------------------------------------------------------ mutation sensitivity
    mut_obs=set()
    for sl,o in SUM.items():
        if o["mutated_contact_count"]>0: mut_obs.add(sl)
    mrows=[]
    for cohort,pred in (("all_eligible",lambda sl:True),
                        ("no_contacted_reported_mutation",lambda sl: sl not in mut_obs),
                        ("engineered_construct",lambda sl: S[SUM[sl]["pdb_id"]]["construct_engineering_status"] in ("chimeric_fusion","mutations_reported"))):
        sub=[]
        for u in unit_rows:
            obs=[o for o in u["observations"] if generic_ok(o) and pred(o)]
            if obs: sub.append((u,obs))
        byp=defaultdict(list)
        for u,obs in sub:
            for sl in obs:
                for c in by_obs[sl]:
                    g=c["receptor_generic_number"]
                    if g and c["within_5A"]: byp[(u["binding_site_class"],g)].append(sl)
        for (site,g),v in sorted(byp.items()):
            mrows.append({"cohort":cohort,"binding_site_class":site,"generic_position":g,
                          "observations_with_contact":len(set(v))})
    dump(AGG/"mutation_sensitivity/cohorts.jsonl",mrows)

    # ------------------------------------------------------------------ coverage records
    cov=[]
    for fam in sorted({s["major_family_id"] for s in S.values()}):
        fs=[s for s in S.values() if s["major_family_id"]==fam]
        fobs=[o for o in SUM.values() if o["major_family_id"]==fam]
        fel=[e for e in EL.values() if S[e["pdb_id"]]["major_family_id"]==fam]
        funits=[u for u in unit_rows if u["major_family_id"]==fam]
        gen=[o for o in fobs if generic_ok(o["structure_ligand_id"])]
        known=[s for s in fs if STATE[s["pdb_id"]]!="unknown"]
        cov.append({"major_family_id":fam,"major_family_name":fs[0]["major_family_name"],
            "structure_count":len(fs),
            "structure_coverage":frac(len({o["pdb_id"] for o in fobs}),len(fs)),
            "receptor_coverage":frac(len({u["receptor_accession"] for u in funits}),
                                     len({s["receptor_entry_name"] for s in fs})),
            "observation_coverage":frac(len(fobs),len(fel)),
            "generic_contact_coverage":frac(len(gen),len(fobs)),
            "state_coverage":frac(len(known),len(fs)),
            "ligand_identity_coverage":frac(len({u["normalized_ligand_identity"] for u in funits}),
                                            max(len({o["structure_ligand_id"].split('::')[0] for o in fobs}),1)),
            "site_class_coverage":frac(sum(1 for o in fobs if o["binding_site_class"]!="unresolved"),
                                       max(len(fobs),1)),
            "analysis_units":len(funits),
            "unique_receptors":len({u["receptor_accession"] for u in funits}),
            "unique_ligands":len({u["normalized_ligand_identity"] for u in funits}),
            "unique_species":len({u["species_taxon"] for u in funits}),
            "warnings":[w for w,c in (
                ("low_structure_count",len(fs)<TH["low_structure_count"]),
                ("low_analysis_unit_count",len(funits)<TH["low_analysis_unit_count"]),
                ("low_receptor_count",len({u['receptor_accession'] for u in funits})<TH["low_receptor_count"]),
                ("mapping_coverage_warning",(frac(len(gen),max(len(fobs),1)) or 0)<TH["mapping_coverage_warning_below"]),
                ("state_coverage_warning",(frac(len(known),len(fs)) or 0)<TH["state_coverage_warning_below"]),
            ) if c]})
    a_cov=dump(P4/"coverage_records.jsonl",cov)

    manifest={"generated_at":utc_now(),"rule_version":RULE,
      "counts":{"aggregation_units":len(unit_rows),"contact_prevalence_rows":len(prev_rows),
                "excluded_observations":dict(excl),
                "layers":{k:len(v) for k,v in layers.items()},
                "weighting_rows":len(wrows),"threshold_rows":len(trows),
                "mutation_rows":len(mrows),"coverage_rows":len(cov)},
      "site_class_separation":("small-molecule and polymer-interface classes are aggregated in "
        "separate rows and never share a denominator"),
      "hashes":{"aggregation_units_sha":a_units["content_sha256"],
                "contact_prevalence_sha":a_prev["content_sha256"],
                "coverage_records_sha":a_cov["content_sha256"]}}
    (AGG/"global_manifest.json").write_text(json.dumps(manifest,indent=1,ensure_ascii=False),
                                            encoding="utf-8")
    print(json.dumps(manifest["counts"],indent=1))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
