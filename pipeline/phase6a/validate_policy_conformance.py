#!/usr/bin/env python3
"""Phase 6A.1 — policy conformance tests for the review gate and the validation disclosure.

These check that the implementation matches the policy that was actually committed to, which is
narrower than "exclude everything under review". Two failure modes are equally serious and both
are tested: under-exclusion (an identity blocker left in a pooled metric) and over-exclusion
(sound data removed because something unrelated in the same deposition is open).
"""
from __future__ import annotations
import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OV = ROOT / "data/release_overlays/rc6"
P4 = ROOT / "data/intermediate/phase4"
AGG = ROOT / "data/aggregates"
R: list[dict] = []


def check(group, name, ok, detail=""):
    R.append({"group": group, "check": name, "status": "PASS" if ok else "FAIL",
              "detail": str(detail) if not ok else ""})


def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    impact = rd(OV / "review_impact.jsonl")
    slots = rd(OV / "structure_slot_eligibility.jsonl")
    bunits = rd(OV / "beta_aggregation_units.jsonl")
    bprev = rd(OV / "beta_contact_prevalence.jsonl")
    summ = json.loads((OV / "beta_exclusion_summary.json").read_text(encoding="utf-8"))
    fvs = json.loads((OV / "family_validation_status.json").read_text(encoding="utf-8"))
    univ = {u["review_item_id"]: u for u in rd(P4 / "canonical_review_universe.jsonl")}
    open_ids = [r["review_item_id"] for r in
                csv.DictReader((ROOT / "curation/review_items.csv").open(encoding="utf-8"))]
    units4 = rd(P4 / "aggregation_units.jsonl")
    prev4 = rd(AGG / "contact_prevalence.jsonl")
    policy = json.loads((ROOT / "governance/REVIEW_GATING_POLICY.json").read_text(encoding="utf-8"))

    # ---- A. completeness -------------------------------------------------------------------
    ids = [r["review_item_id"] for r in impact]
    check("A", "all_737_canonical_records_accounted", len(set(ids)) == len(univ) == 737,
          f"{len(set(ids))} distinct of {len(univ)}")
    check("A", "all_189_open_items_accounted",
          set(open_ids) <= set(ids) and len(open_ids) == 189, len(open_ids))
    dup = [k for k, v in Counter(ids).items() if v > 1]
    check("A", "no_duplicate_review_effects", not dup, f"{len(dup)} duplicated: {dup[:3]}")
    check("A", "every_effect_has_rule_and_reason",
          all(r.get("rule_id") and len(r.get("effect_reason", "")) >= 20 for r in impact))
    check("A", "every_effect_in_vocabulary",
          all(r["aggregation_effect"] in policy["aggregation_effect_vocabulary"] for r in impact))
    check("A", "every_scope_in_vocabulary",
          all(r["affected_scope"] in policy["affected_scope_vocabulary"] for r in impact))
    check("A", "no_unmatched_rule",
          not [r for r in impact if r["rule_id"] == "RG-UNMATCHED"],
          [r["review_item_id"] for r in impact if r["rule_id"] == "RG-UNMATCHED"][:5])

    # ---- B. granularity --------------------------------------------------------------------
    blocked = {o for r in impact
               if r["aggregation_effect"] == "exclude_from_public_beta_pooled_analysis"
               for o in r["affected_observations"]}
    obs_by_pdb = defaultdict(set)
    for u in units4:
        for o in u["observations"]:
            obs_by_pdb[o.split(":")[0]].add(o)
    # a PDB with several observations must not lose them all because one item names one of them
    collateral = []
    for r in impact:
        if r["aggregation_effect"] != "exclude_from_public_beta_pooled_analysis":
            continue
        if r["affected_scope"] != "observation":
            continue
        others = obs_by_pdb[r["pdb_id"]] - set(r["affected_observations"])
        collateral += [o for o in others if o in blocked and
                       o not in {x for y in impact if y["pdb_id"] == r["pdb_id"] and
                                 y["affected_scope"] == "observation"
                                 for x in y["affected_observations"]}]
    check("B", "observation_scope_does_not_block_sibling_observations", not collateral,
          collateral[:3])
    multi = [u for u in bunits if u["observations_total"] > 1 and
             u["review_blocked_observations_total"] > 0]
    bad_multi = [u["aggregation_unit_id"] for u in multi
                 if u["beta_status"] == "removed_zero_denominator"
                 and u["beta_eligible_observations_total"] > 0]
    check("B", "partial_block_does_not_delete_whole_unit", not bad_multi, bad_multi[:3])
    wrong_removal = [u["aggregation_unit_id"] for u in bunits
                     if u["beta_status"] == "removed_zero_denominator"
                     and u["beta_eligible_observations_total"] != 0]
    check("B", "unit_removed_only_when_denominator_zero", not wrong_removal, wrong_removal[:3])
    check("B", "forbidden_blanket_rule_not_applied",
          summ["units_removed"] + summ["units_modified"] <
          summ["coarse_pdb_join_would_have_touched_units"],
          f"gated {summ['units_removed'] + summ['units_modified']} vs coarse "
          f"{summ['coarse_pdb_join_would_have_touched_units']}")

    # ---- C. issue semantics ----------------------------------------------------------------
    eff = {r["review_item_id"]: r for r in impact}

    def eff_of(issue):
        return Counter(eff[i]["aggregation_effect"] for i in open_ids
                       if issue in univ[i]["issue_types"])

    md = [r for r in impact if r["affected_scope"] == "metadata_only"]
    check("C", "metadata_only_never_excluded",
          all(r["aggregation_effect"] != "exclude_from_public_beta_pooled_analysis" for r in md),
          [r["review_item_id"] for r in md
           if r["aggregation_effect"] == "exclude_from_public_beta_pooled_analysis"][:3])
    ano = [r for r in impact if "annotated_not_observed" in r["issue_type"]]
    check("C", "annotated_not_observed_marked_already_excluded",
          all(r["aggregation_effect"] == "already_excluded" for r in ano),
          Counter(r["aggregation_effect"] for r in ano))
    apo = eff_of("apo_assignment")
    check("C", "apo_without_contact_row_already_excluded",
          apo.get("already_excluded", 0) > 0 and
          "exclude_from_public_beta_pooled_analysis" not in apo, dict(apo))
    gm = eff_of("generic_mapping_unvalidated")
    check("C", "unvalidated_generic_mapping_already_excluded",
          set(gm) <= {"already_excluded"}, dict(gm))
    sc = eff_of("site_class_unresolved")
    check("C", "unresolved_site_class_excluded_or_already_excluded",
          set(sc) <= {"already_excluded", "exclude_from_public_beta_pooled_analysis"}, dict(sc))
    rm = eff_of("receptor_mapping")
    check("C", "unresolved_receptor_identity_blocks_where_it_reaches_data",
          set(rm) <= {"exclude_from_public_beta_pooled_analysis", "no_effect"}, dict(rm))
    lc = eff_of("ligand_classification")
    check("C", "unresolved_ligand_identity_blocks_where_it_reaches_data",
          set(lc) <= {"exclude_from_public_beta_pooled_analysis", "no_effect"}, dict(lc))
    td = eff_of("source_conflict:transducer_presence_disagreement")
    check("C", "non_impacting_transducer_disagreement_is_warning_or_no_effect",
          set(td) <= {"warning_only", "no_effect"}, dict(td))

    # ---- D. aggregates ---------------------------------------------------------------------
    check("D", "beta_metric_uses_gated_denominator",
          all(r["denominator_after_review_gate"] <= r["denominator_before_review_gate"]
              for r in bprev))
    zero_bad = [r for r in bprev if r["denominator_after_review_gate"] == 0
                and (r["contact_fraction_5A"] == 0.0)]
    check("D", "zero_denominator_yields_NA_not_zero_percent", not zero_bad, len(zero_bad))
    check("D", "not_estimable_reason_present_when_zero",
          all(r["not_estimable_reason"] for r in bprev
              if r["denominator_after_review_gate"] == 0))
    check("D", "all_three_thresholds_present",
          all(all(k in r for k in ("contact_fraction_4A", "contact_fraction_4_5A",
                                   "contact_fraction_5A")) for r in bprev))
    fam = rd(OV / "beta_family_site_class_summaries.jsonl")
    wanted = {f"{w}_{th}" for w in ("unit_weighted_continuous", "structure_weighted",
                                    "receptor_weighted", "ligand_weighted")
              for th in ("4A", "4_5A", "5A")}
    missing = set()
    for g in fam:
        for p in g["positions"]:
            if p["status"] == "estimable":
                missing |= (wanted - set(p))
    check("D", "all_five_weightings_x_three_thresholds_precomputed", not missing,
          sorted(missing)[:5])
    check("D", "original_phase4_metric_preserved_in_every_row",
          all("source_phase4_metric" in r for r in bprev))
    check("D", "every_blocked_slot_has_review_provenance",
          all(x["review_item_ids"] for x in slots if x["beta_eligibility"] == "review_blocked"))
    # the frozen Phase 4 table must be untouched
    check("D", "phase4_prevalence_row_count_unchanged", len(prev4) == 182169, len(prev4))
    check("D", "phase4_unit_count_unchanged", len(units4) == 727, len(units4))
    # no silent row loss: every unit that keeps an eligible observation keeps its positions
    kept = {u["aggregation_unit_id"] for u in bunits if u["beta_eligible_observations_total"] > 0
            and u["generic_aggregation_eligible"]}
    have = {r["aggregation_unit_id"] for r in bprev}
    lost = sorted(kept - have)
    check("D", "no_silent_unit_loss_in_beta_prevalence", not lost, lost[:3])

    # ---- E. validation disclosure ----------------------------------------------------------
    fams = {r["major_family_id"] for r in fvs["rows"]}
    check("E", "all_11_major_families_represented", len(fams) == 11, len(fams))
    ref = [r for r in fvs["rows"] if r["transfer_status"] == "reference_tested_within_scope"]
    check("E", "only_aminergic_marked_reference_tested",
          all(r["major_family_id"] == "001_001" for r in ref),
          sorted({r["major_family_id"] for r in ref}))
    check("E", "reference_count_matches_frozen_evidence",
          all(r["reference_structure_count"] > 0 for r in ref) and
          fvs["aminergic_reference_evidence"]["independent_reference_structures"] == 9,
          fvs["aminergic_reference_evidence"])
    check("E", "crosswalk_not_claimed_as_independent_validation",
          fvs["aminergic_reference_evidence"]["crosswalk_is_independent_ground_truth"] is False)
    poly = [r for r in fvs["rows"] if r["site_class"] in
            ("extracellular_polymer_interface", "tethered_ligand_interface")]
    check("E", "polymer_interface_never_labelled_pocket_validated",
          all(r["transfer_status"] ==
              "descriptive_interface_rule_not_independently_reference_tested" for r in poly),
          Counter(r["transfer_status"] for r in poly))
    check("E", "polymer_statements_say_descriptive_shell",
          all("descriptive" in r["statement_en"].lower() for r in poly))
    cov = [r for r in fvs["rows"] if r["site_class"] == "covalent_core_site"]
    check("E", "covalent_bond_distinct_from_shell_validation",
          all(r["transfer_status"] ==
              "covalent_relation_verified_contact_shell_not_independently_tested" for r in cov))
    check("E", "every_row_has_tr_and_en", all(len(r["statement_tr"]) >= 20 and
                                              len(r["statement_en"]) >= 20 for r in fvs["rows"]))
    allowed = set(fvs["allowed_status_vocabulary"])
    check("E", "status_vocabulary_respected",
          all(r["transfer_status"] in allowed for r in fvs["rows"]))
    # a family/site-class combination that does not occur must not be invented
    real = {(u["major_family_id"], u["binding_site_class"]) for u in units4}
    invented = [(r["major_family_id"], r["site_class"]) for r in fvs["rows"]
                if r["site_class"] and (r["major_family_id"], r["site_class"]) not in real]
    check("E", "no_invented_family_site_class_rows", not invented, invented[:3])

    # ---- F. wording ------------------------------------------------------------------------
    idx_p = OV / "web/global/review_gate_index.json"
    if idx_p.exists():
        idx = json.loads(idx_p.read_text(encoding="utf-8"))
        for lang in ("en", "tr"):
            w = idx.get(f"policy_wording_{lang}", "")
            check("F", f"policy_wording_not_widened[{lang}]",
                  "where required" in w or "gerektiği yerde" in w, w)
        # The claim must not be ASSERTED. It legitimately appears inside the constraint field,
        # which exists precisely to forbid it, so a blanket substring search over the whole
        # payload flags the safeguard as the violation.
        asserting = [k for k, v in idx.items()
                     if isinstance(v, str) and "all open items are excluded" in v.lower()
                     and not k.endswith("_constraint_en") and not k.endswith("_constraint_tr")]
        check("F", "wording_does_not_claim_all_excluded", not asserting, asserting)
        check("F", "constraint_field_forbids_the_wider_claim",
              "all open items are excluded" in
              idx.get("policy_wording_constraint_en", "").lower())
    else:
        check("F", "overlay_web_payloads_built", False, "review_gate_index.json missing")

    failed = [r for r in R if r["status"] == "FAIL"]
    out = {"checks": len(R), "failed": len(failed),
           "status": "PASSED" if not failed else "FAILED", "results": R}
    (ROOT / "reports/phase6a/policy_conformance_results.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for r in failed:
        print(f"FAIL  {r['group']} :: {r['check']}  {r['detail']}")
    print(json.dumps({k: out[k] for k in ("checks", "failed", "status")}, indent=1))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
