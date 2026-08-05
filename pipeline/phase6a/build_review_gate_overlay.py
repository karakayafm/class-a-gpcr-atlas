#!/usr/bin/env python3
"""Phase 6A.1 — review-gated public-beta aggregation overlay.

Produces a SEPARATE release overlay. It never rewrites a Phase 4 or Phase 5 artefact: the frozen
scientific values stay exactly where they are, and the beta values live alongside them carrying
their own provenance.

The gate is issue-specific by construction. The rule this file exists to avoid is "an open review
item touches this unit, so drop the unit" — that would discard sound data because something
unrelated in the same deposition is unresolved. Every effect here is decided from what the review
item demonstrably reaches, using the rules in governance/REVIEW_GATING_POLICY.json.

Contacts and motif geometry are NOT recomputed. The frozen per-observation contact rows are
re-summarised under an eligibility mask, which is the only honest way to change a denominator.
"""
from __future__ import annotations
import csv, gzip, hashlib, json, statistics, sys
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IN = ROOT / "data/intermediate"
P3 = IN / "phase3"
P4 = IN / "phase4"
CON = ROOT / "data/contacts"
AGG = ROOT / "data/aggregates"
OUT = ROOT / "data/release_overlays/rc6"
POLICY = json.loads((ROOT / "governance/REVIEW_GATING_POLICY.json").read_text(encoding="utf-8"))
RULE_VERSION = POLICY["rule_version"]

POCKET_CLASSES = {"canonical_7tm_pocket", "extended_orthosteric_pocket",
                  "bitopic_or_multi_region_site", "covalent_core_site"}


def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def dump(p: Path, rows) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    txt = "".join(json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
                  for r in rows)
    p.write_text(txt, encoding="utf-8")
    return hashlib.sha256(txt.encode()).hexdigest()


def dump_json(p: Path, obj) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    p.write_text(txt, encoding="utf-8")
    return hashlib.sha256(txt.encode()).hexdigest()


def f(x, n=6): return None if x is None else round(x, n)
def frac(a, b): return None if not b else round(a / b, 6)


def main() -> int:
    # ---------------------------------------------------------------- frozen inputs (read-only)
    UNIV = {u["review_item_id"]: u for u in rd(P4 / "canonical_review_universe.jsonl")}
    open_ids = [r["review_item_id"] for r in
                csv.DictReader((ROOT / "curation/review_items.csv").open(encoding="utf-8"))]
    units = rd(P4 / "aggregation_units.jsonl")
    prev4 = rd(AGG / "contact_prevalence.jsonl")
    SCR = {r["ligand_entity_id"]: r for r in rd(P4 / "site_class_remediation.jsonl")}
    RMD = rd(P4 / "mapping_remediation.jsonl")
    UNVAL_RI = {r["receptor_instance_id"] for r in RMD
                if r["outcome"] == "mapping_unresolved_excluded_from_generic_aggregation"}
    UNVAL_PDB = {r["pdb_id"] for r in RMD
                 if r["outcome"] == "mapping_unresolved_excluded_from_generic_aggregation"}
    TETH = {t["pdb_id"]: t for t in rd(P4 / "tethered_ligand_review.jsonl")}
    SSN = {s["pdb_id"]: s for s in rd(P4 / "structural_state_normalization.jsonl")}
    ANO = {a["pdb_id"] for a in rd(P4 / "annotated_not_observed.jsonl")}

    # Does the state stratification depend on transducer presence? Decided from the frozen rule
    # itself, not from a substring search — an earlier version of this file matched the word
    # "transducer" inside a rule that says transducer presence is NOT used, and over-excluded
    # four sound observations as a result. The test is uniformity of the documented rule, and it
    # fails safe: if the rule ever changes or stops being uniform, transducer disagreements
    # become blockers again.
    _rules = {s["decision_rule"] for s in SSN.values()}
    STATE_USES_TRANSDUCER = not (
        len(_rules) == 1 and
        "NOT relabelled active on that basis" in next(iter(_rules)))

    # observation -> unit, and the reverse
    unit_of_obs, obs_by_pdb, obs_by_le = {}, defaultdict(set), defaultdict(set)
    UMAP = {u["aggregation_unit_id"]: u for u in units}
    for u in units:
        for o in u["observations"]:
            unit_of_obs[o] = u["aggregation_unit_id"]
            obs_by_pdb[o.split(":")[0]].add(o)
            obs_by_le[o.split("::")[0]].add(o)

    # ------------------------------------------------------- 1. per review item, decide effect
    impact = []
    blocked_obs: dict[str, list] = defaultdict(list)   # observation -> review_item_ids
    warned_obs: dict[str, list] = defaultdict(list)

    def emit(rid, u, rule_id, scope, effect, reason, obs_list=(), site=None):
        rec = {
            "review_item_id": rid, "issue_type": ";".join(u["issue_types"]), "pdb_id": u["pdb_id"],
            "structure_ligand_id": u.get("structure_ligand_id"),
            "receptor_instance_id": u.get("receptor_instance_id"),
            "ligand_entity_id": u.get("ligand_entity_id"),
            "aggregation_unit_id": sorted({unit_of_obs[o] for o in obs_list}) or None,
            "affected_observations": sorted(obs_list),
            "affected_scope": scope, "aggregation_effect": effect, "effect_reason": reason,
            "affected_site_class": site,
            "affected_thresholds": ["4A", "4.5A", "5A"] if effect ==
                "exclude_from_public_beta_pooled_analysis" else [],
            "affected_weightings": ["unit_weighted_continuous", "unit_weighted_any_contact",
                                    "structure_weighted", "receptor_weighted", "ligand_weighted"]
                if effect == "exclude_from_public_beta_pooled_analysis" else [],
            "current_review_status": u.get("human_review_status") or "not_started",
            "source_evidence_status": u.get("evidence_completeness"),
            "rule_id": rule_id, "rule_version": RULE_VERSION,
        }
        impact.append(rec)
        for o in obs_list:
            (blocked_obs if effect == "exclude_from_public_beta_pooled_analysis"
             else warned_obs)[o].append(rid)

    for rid in open_ids:
        u = UNIV[rid]
        pdb = u["pdb_id"]
        le = u.get("ligand_entity_id")
        its = set(u["issue_types"])
        pdb_obs = obs_by_pdb.get(pdb, set())
        le_obs = obs_by_le.get(le, set()) if le else set()

        if "site_class_unresolved" in its:
            r = SCR.get(le or "", {})
            if r.get("enters_pooled_aggregation") is False:
                emit(rid, u, "RG-01", "already_excluded_upstream", "already_excluded",
                     "Phase 4 already keeps this entity out of the site-class pooled aggregate "
                     "(enters_pooled_aggregation = false); re-excluding would double count.",
                     (), r.get("final_binding_site_class"))
            else:
                emit(rid, u, "RG-01", "observation", "exclude_from_public_beta_pooled_analysis",
                     "Unresolved binding-site class is an aggregation-identity blocker.",
                     le_obs, r.get("final_binding_site_class"))

        if "apo_assignment" in its:
            if not pdb_obs:
                emit(rid, u, "RG-02", "already_excluded_upstream", "already_excluded",
                     "The structure contributes no ligand-contact observation to any aggregation "
                     "unit, so there is nothing in a pooled metric to exclude.")
            else:
                emit(rid, u, "RG-02", "structure_slot",
                     "exclude_from_public_beta_pooled_analysis",
                     "Apo versus ligand-bound status unresolved while contact rows exist.",
                     pdb_obs)

        if "generic_mapping_unvalidated" in its:
            if pdb in UNVAL_PDB:
                emit(rid, u, "RG-03", "already_excluded_upstream", "already_excluded",
                     "The receptor instance is already excluded from generic aggregation by the "
                     "Phase 4 mapping remediation; the exclusion exists.")
            else:
                emit(rid, u, "RG-03", "structure_slot",
                     "exclude_from_public_beta_pooled_analysis",
                     "Generic mapping unvalidated and not excluded upstream.", pdb_obs)

        if "receptor_mapping" in its:
            if pdb_obs:
                emit(rid, u, "RG-04", "structure_slot",
                     "exclude_from_public_beta_pooled_analysis",
                     "Unresolved receptor identity or mapping changes which receptor the contacts "
                     "belong to, so every structure slot of this entry is unreliable.", pdb_obs)
            else:
                emit(rid, u, "RG-04", "no_current_aggregate_effect", "no_effect",
                     "The entry contributes no observation to any aggregation unit.")

        if "ligand_classification" in its:
            if le_obs:
                emit(rid, u, "RG-05", "observation",
                     "exclude_from_public_beta_pooled_analysis",
                     "Unresolved ligand identity blocks the observation it names, and only that "
                     "observation.", le_obs)
            else:
                emit(rid, u, "RG-05", "no_current_aggregate_effect", "no_effect",
                     "This ligand entity is not the ligand of any observation in a pooled unit.")

        if "polymer_chain_role" in its:
            if le_obs:
                emit(rid, u, "RG-06", "observation",
                     "exclude_from_public_beta_pooled_analysis",
                     "The polymer chain is itself treated as the ligand of a pooled observation, "
                     "so its unresolved role blocks that observation.", le_obs)
            else:
                emit(rid, u, "RG-06", "no_current_aggregate_effect", "warning_only",
                     "The unresolved chain is not the ligand of any pooled observation. Resolving "
                     "it could ADD a missing polymer-interface observation but cannot invalidate "
                     "the small-molecule observations that exist, so the sound data is kept and "
                     "the under-inclusion risk is shown as a warning.", ())

        if "source_conflict:transducer_presence_disagreement" in its:
            s = SSN.get(pdb, {})
            derived = STATE_USES_TRANSDUCER or bool(s.get("derived_from_motif_geometry"))
            if derived and pdb_obs:
                emit(rid, u, "RG-07", "structure_slot",
                     "exclude_from_public_beta_pooled_analysis",
                     "The unit's structural state was derived from transducer presence, which is "
                     "what the sources disagree about.", pdb_obs)
            else:
                emit(rid, u, "RG-07", "metadata_only", "warning_only",
                     "Pooled units are stratified by normalized structural state, and this "
                     "entry's state was mapped from the source state annotation rather than from "
                     "transducer presence. The disagreement is shown, not acted on.", ())

        if "tethered_ligand_candidate" in its:
            t = TETH.get(pdb, {})
            pocket = {o for o in pdb_obs
                      if UMAP[unit_of_obs[o]]["binding_site_class"] in POCKET_CLASSES}
            if t.get("outcome") == "unresolved_human_review_required" and pocket:
                emit(rid, u, "RG-08", "observation",
                     "exclude_from_public_beta_pooled_analysis",
                     "The receptor's endogenous ligand is a tethered segment whose identity is "
                     "unresolved, so whether the co-bound small molecule occupies the orthosteric "
                     "pocket is undecidable. Presenting it as a settled pocket contact would "
                     "assert the very thing under review.", pocket,
                     sorted({UMAP[unit_of_obs[o]]["binding_site_class"] for o in pocket})[0])
            else:
                emit(rid, u, "RG-08", "no_current_aggregate_effect", "warning_only",
                     "No pooled pocket observation depends on the tethered-ligand question.", ())

    # every open item must be accounted for
    accounted = {r["review_item_id"] for r in impact}
    for rid in open_ids:
        if rid not in accounted:
            u = UNIV[rid]
            emit(rid, u, "RG-UNMATCHED", "unresolved", "human_policy_required",
                 "No rule in the policy matches this issue type; a person must decide before the "
                 "public beta can claim issue-specific gating.", ())

    # the 548 optional-confirmation records are accounted for too, as non-blocking
    for rid, u in UNIV.items():
        if rid in accounted or rid in open_ids:
            continue
        its = set(u["issue_types"])
        if "annotated_not_observed" in its or "source_conflict:annotated_component_absent" in its:
            emit(rid, u, "RG-09/10", "already_excluded_upstream", "already_excluded",
                 "An annotated component absent from the coordinates contributes no contact row.")
        elif "mutation_mapping_unresolved" in its:
            emit(rid, u, "RG-11", "no_current_aggregate_effect", "no_effect",
                 "Mutation metadata unresolved outside the contacted and motif residues that "
                 "enter a pooled contact metric.")
        elif "aminergic_regression_discrepancy" in its:
            emit(rid, u, "RG-12", "metadata_only", "warning_only",
                 "A reconciliation record against the frozen aminergic project, not a defect in "
                 "this observation's identity.")
        else:
            emit(rid, u, "RG-13", "metadata_only", "no_effect",
                 "Optional-confirmation record with no demonstrated effect on a pooled metric.")

    h_impact = dump(OUT / "review_impact.jsonl", sorted(impact, key=lambda r: r["review_item_id"]))

    # ------------------------------------------------- 2. structure-slot eligibility per unit
    slot_rows = []
    for u in units:
        for o in sorted(u["observations"]):
            st = ("review_blocked" if o in blocked_obs else
                  "warning_only" if o in warned_obs else "eligible")
            slot_rows.append({
                "aggregation_unit_id": u["aggregation_unit_id"], "observation_id": o,
                "pdb_id": o.split(":")[0], "ligand_entity_id": o.split("::")[0],
                "receptor_instance_id": o.split("::")[-1],
                "binding_site_class": u["binding_site_class"],
                "major_family_id": u["major_family_id"],
                "beta_eligibility": st,
                "review_item_ids": sorted(blocked_obs.get(o, []) + warned_obs.get(o, [])),
                "rule_version": RULE_VERSION})
    h_slots = dump(OUT / "structure_slot_eligibility.jsonl", slot_rows)

    # ------------------------------------------------------------ 3. beta aggregation units
    beta_units, removed_units, modified_units = [], [], []
    for u in units:
        obs = list(u["observations"])
        elig = [o for o in obs if o not in blocked_obs]
        blocked = [o for o in obs if o in blocked_obs]
        warned = [o for o in obs if o in warned_obs and o not in blocked_obs]
        row = dict(u)
        row.update({
            "beta_eligible_observations": sorted(elig),
            "beta_eligible_observations_total": len(elig),
            "review_blocked_observations": sorted(blocked),
            "review_blocked_observations_total": len(blocked),
            "warning_only_observations_total": len(warned),
            "beta_structures": sorted({o.split(":")[0] for o in elig}),
            "beta_structures_total": len({o.split(":")[0] for o in elig}),
            "original_structures_total": u["structures_total"],
            "beta_status": "removed_zero_denominator" if not elig else
                           ("modified" if blocked else "unchanged"),
            "review_item_ids": sorted({r for o in blocked for r in blocked_obs[o]} |
                                      {r for o in warned for r in warned_obs[o]}),
            "source_phase4_unit": u["aggregation_unit_id"],
            "overlay_rule_version": RULE_VERSION})
        beta_units.append(row)
        if not elig:
            removed_units.append(u["aggregation_unit_id"])
        elif blocked:
            modified_units.append(u["aggregation_unit_id"])
    h_units = dump(OUT / "beta_aggregation_units.jsonl", beta_units)

    # ------------------------------- 4. re-summarise contacts under the mask (no recomputation)
    MAPPED = defaultdict(set)
    for m in rd(P3 / "receptor_residue_mapping.jsonl"):
        if m.get("display_generic_number"):
            MAPPED[m["receptor_instance_id"]].add(m["display_generic_number"])
    SUMM = {s["structure_ligand_id"]: s for s in rd(CON / "observation_contact_summary.jsonl")}
    by_obs = defaultdict(list)
    for fp in sorted((CON / "by_family").glob("*/residue_pair_contacts.jsonl.gz")):
        for l in gzip.open(fp, "rt"):
            c = json.loads(l)
            by_obs[c["structure_ligand_id"]].append(c)

    def generic_ok(sl):
        return (SUMM.get(sl, {}).get("generic_contact_eligibility") == "yes"
                and sl.split("::")[-1] not in UNVAL_RI)

    prev4_idx = {(r["aggregation_unit_id"], r["generic_position"]): r for r in prev4}
    beta_prev = []
    for u in beta_units:
        if not u["generic_aggregation_eligible"]:
            continue
        obs_all = [o for o in u["observations"] if generic_ok(o)]
        obs_beta = [o for o in u["beta_eligible_observations"] if generic_ok(o)]
        n_before, n_after = len(obs_all), len(obs_beta)
        available = set()
        for sl in obs_beta:
            available |= MAPPED.get(sl.split("::")[-1], set())
        pos = {g: {"4": set(), "45": set(), "5": set(), "d": []} for g in available}
        for sl in obs_beta:
            seen = defaultdict(list)
            for c in by_obs.get(sl, []):
                g = c["receptor_generic_number"]
                if g:
                    seen[g].append(c["min_distance_angstrom"])
            for g, ds in seen.items():
                md = min(ds)
                p = pos.setdefault(g, {"4": set(), "45": set(), "5": set(), "d": []})
                if md <= 4.0: p["4"].add(sl)
                if md <= 4.5: p["45"].add(sl)
                if md <= 5.0: p["5"].add(sl)
                p["d"].append(md)
        for g, p in sorted(pos.items()):
            src = prev4_idx.get((u["aggregation_unit_id"], g), {})
            ds = sorted(p["d"])
            beta_prev.append({
                "aggregation_unit_id": u["aggregation_unit_id"], "generic_position": g,
                "binding_site_class": u["binding_site_class"],
                "is_polymer_interface": u["is_polymer_interface"],
                "major_family_id": u["major_family_id"],
                "receptor_family_id": u["receptor_family_id"],
                "receptor_accession": u["receptor_accession"],
                "species_taxon": u["species_taxon"],
                "normalized_ligand_identity": u["normalized_ligand_identity"],
                "normalized_structural_state": u["normalized_structural_state"],
                "original_structures_total": u["original_structures_total"],
                "beta_eligible_structures": u["beta_structures_total"],
                "review_blocked_structures": u["review_blocked_observations_total"],
                "warning_only_structures": u["warning_only_observations_total"],
                "structures_with_contact_4A": len(p["4"]),
                "structures_with_contact_4_5A": len(p["45"]),
                "structures_with_contact_5A": len(p["5"]),
                "contact_fraction_4A": frac(len(p["4"]), n_after),
                "contact_fraction_4_5A": frac(len(p["45"]), n_after),
                "contact_fraction_5A": frac(len(p["5"]), n_after),
                "contact_any_5A": len(p["5"]) > 0,
                "denominator_before_review_gate": n_before,
                "denominator_after_review_gate": n_after,
                "estimable": n_after > 0,
                "not_estimable_reason": None if n_after else "zero_eligible_denominator",
                "min_distance": f(min(ds)) if ds else None,
                "median_min_distance": f(statistics.median(ds)) if ds else None,
                "review_item_ids": u["review_item_ids"],
                "review_gate_warning": bool(u["review_blocked_observations_total"] or
                                            u["warning_only_observations_total"]),
                "source_phase4_metric": {
                    "contact_fraction_5A": src.get("contact_fraction_5A"),
                    "contact_fraction_4_5A": src.get("contact_fraction_4_5A"),
                    "contact_fraction_4A": src.get("contact_fraction_4A"),
                    "denominator_count": src.get("denominator_count")},
                "overlay_rule_version": RULE_VERSION})
    h_prev = dump(OUT / "beta_contact_prevalence.jsonl", beta_prev)

    # --------------------------------------- 5. weightings, all derived from frozen contributions
    def weight_layer(rows, keyfn, name):
        out = defaultdict(list)
        for r in rows:
            out[keyfn(r)].append(r)
        res = []
        for k, v in sorted(out.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
            byp = defaultdict(list)
            for r in v:
                byp[r["generic_position"]].append(r)
            positions = []
            for g, rr in sorted(byp.items()):
                est = [x for x in rr if x["estimable"]]
                entry = {"generic_position": g, "units": len(rr), "units_estimable": len(est)}
                if not est:
                    for th in ("4A", "4_5A", "5A"):
                        for w in ("unit_weighted_continuous", "unit_weighted_any_contact",
                                  "structure_weighted", "receptor_weighted", "ligand_weighted"):
                            entry[f"{w}_{th}"] = None
                    entry["status"] = "not_estimable_zero_eligible_denominator"
                    positions.append(entry)
                    continue
                for th, key in (("4A", "contact_fraction_4A"), ("4_5A", "contact_fraction_4_5A"),
                                ("5A", "contact_fraction_5A")):
                    fr = [x[key] for x in est if x[key] is not None]
                    entry[f"unit_weighted_continuous_{th}"] = f(statistics.mean(fr)) if fr else None
                    num = sum(x[f"structures_with_contact_{th}"] for x in est)
                    den = sum(x["denominator_after_review_gate"] for x in est)
                    entry[f"structure_weighted_{th}"] = frac(num, den)
                    # receptor- and ligand-weighted: average within the group, then across groups.
                    # A re-weighting of the same frozen unit contributions, not a new measurement.
                    for wname, field in (("receptor_weighted", "receptor_accession"),
                                         ("ligand_weighted", "normalized_ligand_identity")):
                        grp = defaultdict(list)
                        for x in est:
                            if x[key] is not None:
                                grp[x[field]].append(x[key])
                        means = [statistics.mean(z) for z in grp.values() if z]
                        entry[f"{wname}_{th}"] = f(statistics.mean(means)) if means else None
                entry["unit_weighted_any_contact_5A"] = f(statistics.mean(
                    [1.0 if x["contact_any_5A"] else 0.0 for x in est]))
                entry["status"] = "estimable"
                positions.append(entry)
            res.append({"layer": name, "group_key": [str(x) for x in
                        (k if isinstance(k, tuple) else (k,))],
                        "analysis_units": len({r["aggregation_unit_id"] for r in v}),
                        "positions_reported": len(positions), "positions": positions,
                        "overlay_rule_version": RULE_VERSION})
        return res

    fam = weight_layer(beta_prev, lambda r: (r["major_family_id"], r["binding_site_class"]),
                       "major_family x site_class")
    h_iface = dump(OUT / "beta_interface_summaries.jsonl",
                   [r for r in fam if "polymer" in r["group_key"][1] or
                    "tethered" in r["group_key"][1]])
    dump(OUT / "beta_family_site_class_summaries.jsonl", fam)

    # ------------------------------------------------------------------- 6. motif context
    motif_rows = []
    for u in beta_units:
        if u["beta_status"] == "unchanged":
            continue
        motif_rows.append({
            "aggregation_unit_id": u["aggregation_unit_id"],
            "major_family_id": u["major_family_id"],
            "beta_status": u["beta_status"],
            "motif_geometry_recomputed": False,
            "note": ("Motif geometry is frozen Phase 4 output and is not recomputed. Only the set "
                     "of observations contributing to a pooled motif context changes."),
            "beta_eligible_observations_total": u["beta_eligible_observations_total"],
            "review_item_ids": u["review_item_ids"],
            "overlay_rule_version": RULE_VERSION})
    h_motif = dump(OUT / "beta_motif_context.jsonl", motif_rows)

    # ------------------------------------------------------------------------ 7. coverage
    cov = []
    for famid in sorted({u["major_family_id"] for u in beta_units}):
        us = [u for u in beta_units if u["major_family_id"] == famid]
        cov.append({
            "major_family_id": famid,
            "units_total": len(us),
            "units_unchanged": sum(1 for u in us if u["beta_status"] == "unchanged"),
            "units_modified": sum(1 for u in us if u["beta_status"] == "modified"),
            "units_removed": sum(1 for u in us if u["beta_status"] == "removed_zero_denominator"),
            "observations_total": sum(u["observations_total"] for u in us),
            "observations_beta_eligible": sum(u["beta_eligible_observations_total"] for u in us),
            "observations_review_blocked": sum(u["review_blocked_observations_total"] for u in us),
            "observations_warning_only": sum(u["warning_only_observations_total"] for u in us),
            "overlay_rule_version": RULE_VERSION})
    h_cov = dump(OUT / "beta_coverage.jsonl", cov)

    # ------------------------------------------------------------------- 8. exclusion summary
    eff = Counter(r["aggregation_effect"] for r in impact)
    scope = Counter(r["affected_scope"] for r in impact)
    eff_open = Counter(r["aggregation_effect"] for r in impact if r["review_item_id"] in open_ids)
    summary = {
        "rule_version": RULE_VERSION,
        "canonical_review_records": len(UNIV),
        "human_review_required_items": len(open_ids),
        "impact_records": len(impact),
        "effect_counts_all": dict(eff),
        "effect_counts_open_items": dict(eff_open),
        "scope_counts": dict(scope),
        "observations_blocked": len(blocked_obs),
        "observations_warning_only": len([o for o in warned_obs if o not in blocked_obs]),
        "observations_total": sum(len(u["observations"]) for u in units),
        "units_total": len(units),
        "units_modified": len(modified_units),
        "units_removed": len(removed_units),
        "units_unchanged": len(units) - len(modified_units) - len(removed_units),
        "modified_unit_ids": sorted(modified_units),
        "removed_unit_ids": sorted(removed_units),
        "coarse_pdb_join_would_have_touched_units": len(
            {u["aggregation_unit_id"] for u in units
             if {o.split(":")[0] for o in u["observations"]} &
                {UNIV[r]["pdb_id"] for r in open_ids}}),
        "coarse_pdb_join_would_have_touched_observations": len(
            [o for u in units for o in u["observations"]
             if o.split(":")[0] in {UNIV[r]["pdb_id"] for r in open_ids}]),
        "forbidden_rule_not_applied": ("Units are not excluded merely because an open review item "
                                       "shares their PDB. The coarse figures above are recorded "
                                       "to show what the forbidden rule would have removed."),
    }
    h_sum = dump_json(OUT / "beta_exclusion_summary.json", summary)

    manifest = {
        "overlay": "rc6", "rule_version": RULE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_phase4_prevalence_rows": len(prev4),
        "beta_prevalence_rows": len(beta_prev),
        "hashes": {"review_impact_sha": h_impact, "structure_slot_eligibility_sha": h_slots,
                   "beta_aggregation_units_sha": h_units, "beta_contact_prevalence_sha": h_prev,
                   "beta_interface_summaries_sha": h_iface, "beta_motif_context_sha": h_motif,
                   "beta_coverage_sha": h_cov, "beta_exclusion_summary_sha": h_sum,
                   "review_gating_policy_sha": hashlib.sha256(
                       (ROOT / "governance/REVIEW_GATING_POLICY.json").read_bytes()).hexdigest()},
        "thresholds": ["4A", "4.5A", "5A"],
        "weightings": ["unit_weighted_continuous", "unit_weighted_any_contact",
                       "structure_weighted", "receptor_weighted", "ligand_weighted"],
        "contacts_recomputed": False,
        "motif_geometry_recomputed": False,
        "phase4_artefacts_modified": False,
    }
    h_man = dump_json(OUT / "overlay_manifest.json", manifest)
    manifest["hashes"]["overlay_manifest_sha"] = h_man

    print(json.dumps({k: summary[k] for k in
                      ("human_review_required_items", "impact_records", "effect_counts_open_items",
                       "observations_blocked", "observations_warning_only", "units_modified",
                       "units_removed", "coarse_pdb_join_would_have_touched_units")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
