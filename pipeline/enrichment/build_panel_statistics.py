#!/usr/bin/env python3
"""E6: panel statistics using the frozen Phase 4 unit and denominator semantics."""
from __future__ import annotations

import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.generic_numbers import display_generic_number  # noqa: E402

IN = ROOT / "data/intermediate"
P3 = IN / "phase3"
P4 = IN / "phase4"
CONTACTS = ROOT / "data/contacts/by_family"
ASSIGNMENTS = IN / "enrichment/transducer_assignments.jsonl"
POCKET = IN / "enrichment/pocket_detail"
OUTPUT = IN / "enrichment/panel_statistics.json"
SCHEMA = ROOT / "schemas/enrichment/panel_statistics.schema.json"
REPORT = ROOT / "reports/enrichment_panel_statistics.md"
PANEL_ORDER = ["Gs", "Gi/o", "Gq/11", "G12/13", "arrestin", "transducer_free"]
CANONICAL_SITE = "canonical_7tm_pocket"
CORE_THRESHOLD = 0.75
AA3_TO_1 = {"ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q",
             "GLU":"E","GLY":"G","HIS":"H","ILE":"I","LEU":"L","LYS":"K",
             "MET":"M","PHE":"F","PRO":"P","SER":"S","THR":"T","TRP":"W",
             "TYR":"Y","VAL":"V","SEC":"U","PYL":"O"}


def rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def rounded(value):
    return None if value is None else round(value, 6)


def activity(binding_modes: set[str]) -> str:
    agonists = {"Agonist", "Agonist (partial)", "Allosteric agonist", "Ago-PAM"}
    antagonists = {"Antagonist", "Inverse agonist", "Allosteric antagonist"}
    if binding_modes and binding_modes <= agonists:
        return "agonist"
    if binding_modes and binding_modes <= antagonists:
        return "antagonist"
    return "unknown"


def position_payload(unit_position_rows: list[dict], denominator_counts: dict) -> list[dict]:
    grouped = defaultdict(list)
    for row in unit_position_rows:
        grouped[row["generic_position"]].append(row)
    result = []
    for canonical, values in sorted(grouped.items()):
        fractions = [row["contact_fraction_5A"] for row in values]
        contact_units = [row for row in values if row["contact_any_5A"]]
        modes = Counter(row["aa"] for row in contact_units if row["aa"])
        top_aa = modes.most_common(1)[0][0] if modes else None
        activity_values = {}
        for label in ("agonist", "antagonist", "unknown"):
            subset = [row["contact_fraction_5A"] for row in values if row["activity"] == label]
            activity_values[label] = rounded(statistics.mean(subset)) if subset else None
        segment = Counter(row["segment"] for row in values if row["segment"]).most_common(1)
        gn = display_generic_number(canonical)
        result.append({
            "gn": gn, "canonical_gn": canonical,
            "segment": segment[0][0] if segment else None,
            "helix": gn.split("x", 1)[0] if gn and gn.split("x", 1)[0].isdigit() else None,
            "n_units": len(contact_units),
            "mapped_unit_denominator": len(values),
            "prevalence": rounded(statistics.mean(fractions)),
            "agonist_prevalence": activity_values["agonist"],
            "antagonist_prevalence": activity_values["antagonist"],
            "unknown_prevalence": activity_values["unknown"],
            "top_aa": top_aa,
            "top_aa_fraction": rounded(modes[top_aa] / sum(modes.values())) if top_aa else None,
            "n_variants": len(modes),
            "denominators": {
                "all_mapped_units": len(values),
                "agonist_mapped_units": sum(row["activity"] == "agonist" for row in values),
                "antagonist_mapped_units": sum(row["activity"] == "antagonist" for row in values),
                "unknown_mapped_units": sum(row["activity"] == "unknown" for row in values),
                "site_units": denominator_counts["all"],
            },
        })
    return result


def panel_membership(assignments: dict, evidence_rows) -> dict:
    """Union of the structurally observed transducer panel and every panel a positive tier-B
    functional assay places the structure in — the same rule the aminergic viewer applies in
    build_pathway_pocket_data_v15.py:374. Statistics must use the identical definition as the
    payloads, otherwise the same panel would report two different structure counts."""
    members = {pdb: set(panels) for pdb, panels in assignments.items()}
    for row in evidence_rows:
        if row["tier"] == "B" and row["panel_membership"]:
            members.setdefault(row["pdb_id"], set()).add(row["panel"])
    return {pdb: sorted(panels) for pdb, panels in members.items()}


def main() -> None:
    structural = {row["pdb_id"]: row["panels"] for row in rows(ASSIGNMENTS)}
    assignments = panel_membership(structural, rows(IN / "enrichment/pathway_evidence.jsonl"))
    structures = {row["pdb_id"]: row for row in rows(IN / "structures.normalized.jsonl")}
    ligand_candidates = {row["ligand_entity_id"]: row for row in rows(IN / "ligand_candidates.jsonl")}
    summaries = {row["structure_ligand_id"]: row for row in
                 rows(ROOT / "data/contacts/observation_contact_summary.jsonl")}
    units = rows(P4 / "aggregation_units.jsonl")
    remediation = rows(P4 / "mapping_remediation.jsonl")
    unvalidated = {row["receptor_instance_id"] for row in remediation
                   if row["outcome"] == "mapping_unresolved_excluded_from_generic_aggregation"}

    mapped = defaultdict(set)
    segment_by_gn = defaultdict(Counter)
    for row in rows(P3 / "receptor_residue_mapping.jsonl"):
        gn = row.get("display_generic_number")
        if gn:
            mapped[row["receptor_instance_id"]].add(gn)
            if row.get("protein_segment"):
                segment_by_gn[gn][row["protein_segment"]] += 1

    by_observation = defaultdict(list)
    for path in sorted(CONTACTS.glob("*/residue_pair_contacts.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                by_observation[row["structure_ligand_id"]].append(row)

    def generic_ok(observation: str) -> bool:
        return (summaries[observation]["generic_contact_eligibility"] == "yes" and
                observation.split("::")[-1] not in unvalidated)

    all_split_units = []
    for unit in units:
        for panel in PANEL_ORDER:
            all_observations = [obs for obs in unit["observations"]
                                if panel in assignments[summaries[obs]["pdb_id"]]]
            observations = [obs for obs in all_observations if generic_ok(obs)]
            if not all_observations:
                continue
            modes = {ligand_candidates[obs.split("::", 1)[0]]["binding_mode"]
                     for obs in all_observations}
            reasons = Counter()
            if not observations:
                for obs in all_observations:
                    rid = obs.split("::")[-1]
                    if rid in unvalidated:
                        reasons["receptor_mapping_unresolved"] += 1
                    elif summaries[obs]["generic_contact_eligibility"] != "yes":
                        reasons["generic_contact_mapping_incomplete"] += 1
                    else:
                        reasons["other_generic_aggregation_exclusion"] += 1
            not_estimable_reason = None
            if reasons:
                not_estimable_reason = ("receptor_mapping_unresolved"
                                        if reasons["receptor_mapping_unresolved"]
                                        else "generic_contact_mapping_incomplete"
                                        if reasons["generic_contact_mapping_incomplete"]
                                        else "other_generic_aggregation_exclusion")
            all_split_units.append({"unit": unit, "panel": panel,
                                    "all_observations": all_observations,
                                    "observations": observations,
                                    "activity": activity(modes),
                                    "estimable": bool(observations),
                                    "not_estimable_reason": not_estimable_reason})

    split_units = [row for row in all_split_units if row["estimable"]]

    unit_position_rows = []
    for split in split_units:
        observations = split["observations"]
        available = set()
        for obs in observations:
            available |= mapped.get(obs.split("::")[-1], set())
        data = {gn: {"4": set(), "45": set(), "5": set(), "aa": Counter()}
                for gn in available}
        for obs in observations:
            seen = defaultdict(list)
            aa_seen = defaultdict(list)
            for contact in by_observation[obs]:
                gn = contact.get("receptor_generic_number")
                if gn:
                    seen[gn].append(contact["min_distance_angstrom"])
                    aa_seen[gn].append(contact["receptor_residue_name"])
            for gn, distances in seen.items():
                minimum = min(distances)
                item = data.setdefault(gn, {"4": set(), "45": set(), "5": set(), "aa": Counter()})
                if minimum <= 4.0: item["4"].add(obs)
                if minimum <= 4.5: item["45"].add(obs)
                if minimum <= 5.0:
                    item["5"].add(obs)
                    closest_index = distances.index(minimum)
                    item["aa"][AA3_TO_1.get(aa_seen[gn][closest_index])] += 1
        n = len(observations)
        for gn, item in sorted(data.items()):
            unit_position_rows.append({
                "panel": split["panel"], "site_class": split["unit"]["binding_site_class"],
                "split_unit_id": split["unit"]["aggregation_unit_id"] + "|panel:" + split["panel"],
                "generic_position": gn, "activity": split["activity"],
                "contact_fraction_4A": rounded(len(item["4"]) / n),
                "contact_fraction_4_5A": rounded(len(item["45"]) / n),
                "contact_fraction_5A": rounded(len(item["5"]) / n),
                "contact_any_5A": bool(item["5"]),
                "aa": item["aa"].most_common(1)[0][0] if item["aa"] else None,
                "segment": segment_by_gn[gn].most_common(1)[0][0] if segment_by_gn[gn] else None,
                "denominator_type": "generic_eligible_observations_in_unit_where_position_is_mapped",
                "denominator_count": n,
            })

    pocket_counts = {}
    pocket_empty_reasons = {}
    for path in POCKET.glob("*.json"):
        for row in json.loads(path.read_text(encoding="utf-8"))["structures"]:
            pocket_counts[row["pdb_id"]] = row["n_contacts"]
            pocket_empty_reasons[row["pdb_id"]] = row["empty_reason"]

    panels = []
    for panel in PANEL_ORDER:
        pdb_ids = sorted(pdb for pdb, memberships in assignments.items() if panel in memberships)
        panel_all_units = [row for row in all_split_units if row["panel"] == panel]
        panel_units = [row for row in panel_all_units if row["estimable"]]
        site_payloads = []
        for site in sorted({row["unit"]["binding_site_class"] for row in panel_all_units}):
            site_all_units = [row for row in panel_all_units
                              if row["unit"]["binding_site_class"] == site]
            site_units = [row for row in panel_units if row["unit"]["binding_site_class"] == site]
            denominator_counts = {label: sum(row["activity"] == label for row in site_units)
                                  for label in ("agonist", "antagonist", "unknown")}
            denominator_counts["all"] = len(site_units)
            position_rows = [row for row in unit_position_rows
                             if row["panel"] == panel and row["site_class"] == site]
            site_reasons = Counter(row["not_estimable_reason"] for row in site_all_units
                                   if not row["estimable"])
            site_payloads.append({"binding_site_class": site,
                                  "n_units": len(site_all_units),
                                  "n_prevalence_estimable": len(site_units),
                                  "n_not_estimable": len(site_all_units) - len(site_units),
                                  "not_estimable_reasons": dict(site_reasons),
                                  "denominators": denominator_counts,
                                  "positions": position_payload(position_rows, denominator_counts)})
        canonical = next((row for row in site_payloads
                          if row["binding_site_class"] == CANONICAL_SITE),
                         {"denominators": {"all": 0, "agonist": 0, "antagonist": 0, "unknown": 0},
                          "positions": []})
        identities = {row["unit"]["normalized_ligand_identity"] for row in panel_all_units}
        receptors = {structures[pdb]["receptor_entry_name"] for pdb in pdb_ids}
        all_activity = Counter(row["activity"] for row in panel_all_units)
        panel_reasons = Counter(row["not_estimable_reason"] for row in panel_all_units
                                if not row["estimable"])
        empty_reasons = Counter(pocket_empty_reasons[pdb] for pdb in pdb_ids
                                if pocket_empty_reasons[pdb] is not None)
        panels.append({
            "id": panel, "n_structures": len(pdb_ids), "n_receptors": len(receptors),
            "n_ligands": len(identities), "n_units": len(panel_all_units),
            "n_prevalence_estimable": len(panel_units),
            "n_not_estimable": len(panel_all_units) - len(panel_units),
            "not_estimable_reasons": dict(panel_reasons),
            "structure_empty_reasons": dict(empty_reasons),
            "n_agonist": all_activity["agonist"], "n_antagonist": all_activity["antagonist"],
            "median_contacts_5A": rounded(statistics.median(pocket_counts[pdb] for pdb in pdb_ids)),
            "n_core_positions": sum((row["prevalence"] or 0) >= CORE_THRESHOLD
                                    for row in canonical["positions"]),
            "denominators": canonical["denominators"],
            "positions": canonical["positions"], "site_classes": site_payloads,
        })

    payload = {
        "methodology": {
            "source": "pipeline/phase4/aggregate.py and Phase 4 frozen aggregation units",
            "unit_key": ["receptor_accession", "species_taxon", "normalized_ligand_identity",
                         "ligand_entity_form", "binding_site_class", "normalized_structural_state"],
            "panel_split": "Phase 4 units are split only when their eligible observations belong to different structural-transducer panels",
            "primary_threshold_angstrom": 5.0,
            "primary_metric": "unit_weighted_continuous mean of contact_fraction_5A",
            "denominator_type": "generic_eligible_observations_in_unit_where_position_is_mapped",
            "site_class_rule": "site classes are separate and never share a denominator",
            "unit_count_rule": "n_units counts all panel-split Phase 4 units; n_prevalence_estimable counts units entering a site-specific generic-position prevalence; top-level denominators refer only to canonical_7tm_pocket",
            "zero_denominator_rule": "not_estimable (null), never 0%",
            "core_position_threshold": CORE_THRESHOLD,
        },
        "panels": panels,
    }
    errors = list(jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))).iter_errors(payload))
    if errors:
        raise RuntimeError(errors[0].message)
    if sum(panel["n_structures"] for panel in panels) < 1358:
        raise RuntimeError("panel structure coverage is incomplete")
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n", encoding="utf-8")

    phase4 = {(row["aggregation_unit_id"], row["generic_position"]): row
              for row in rows(ROOT / "data/aggregates/contact_prevalence.jsonl")}
    unchanged_checks = 0
    for split in split_units:
        if len(split["observations"]) != split["unit"]["generic_eligible_observations"]:
            continue
        for row in (item for item in unit_position_rows
                    if item["split_unit_id"] == split["unit"]["aggregation_unit_id"] + "|panel:" + split["panel"]):
            original = phase4.get((split["unit"]["aggregation_unit_id"], row["generic_position"]))
            if original and row["contact_fraction_5A"] != original["contact_fraction_5A"]:
                raise RuntimeError("Phase 4 prevalence mismatch for unchanged unit")
            if original:
                unchanged_checks += 1
    report = ["# Enrichment panel statistics", "",
              "Phase 4 unit keys, generic eligibility, 4.0/4.5/5.0 Å thresholds, "
              "mapped-position denominators and unit-weighted continuous prevalence are reused unchanged.", "",
              "| Panel | Structures | Units total | Estimable (all sites) | Not estimable | Canonical denominator | Other estimable site units |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for panel in panels:
        canonical_n = panel["denominators"]["all"]
        report.append(f"| {panel['id']} | {panel['n_structures']} | {panel['n_units']} | "
                      f"{panel['n_prevalence_estimable']} | {panel['n_not_estimable']} | "
                      f"{canonical_n} | {panel['n_prevalence_estimable'] - canonical_n} |")
    report += ["", "The previously apparent `n_units - denominators.all` gap is not an "
               "estimability loss: top-level `denominators.all` is canonical-pocket-only, while "
               "`n_units` spans every site class. Other-site units remain estimable under their "
               "own separate denominators.", "", "## True non-estimable unit reasons", ""]
    for panel in panels:
        report.append(f"- **{panel['id']}**: {panel['n_not_estimable']} — " +
                      (", ".join(f"`{key}`={value}" for key, value in
                                 sorted(panel["not_estimable_reasons"].items())) or "none"))
    report += ["", "## Empty structure reasons (separate from analysis-unit estimability)", ""]
    for panel in panels:
        report.append(f"- **{panel['id']}**: " +
                      (", ".join(f"`{key}`={value}" for key, value in
                                 sorted(panel["structure_empty_reasons"].items())) or "none"))
    report += ["", f"Panel structure memberships sum to {sum(p['n_structures'] for p in panels)}.",
               f"Unsplit unit-position values checked directly against `contact_prevalence.jsonl`: {unchanged_checks} exact matches.",
               "Every site class carries its own explicit all/agonist/antagonist/unknown unit denominators; null is used where a denominator is zero.", ""]
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"panels": {p["id"]: p["n_structures"] for p in panels},
                      "structure_memberships": sum(p["n_structures"] for p in panels),
                      "split_units_total": len(all_split_units),
                      "split_units_estimable": len(split_units),
                      "split_units_not_estimable": len(all_split_units) - len(split_units),
                      "unit_position_rows": len(unit_position_rows),
                      "phase4_exact_checks": unchanged_checks, "schema_errors": 0}, indent=2))


if __name__ == "__main__":
    main()
