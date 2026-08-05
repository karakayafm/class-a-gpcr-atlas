#!/usr/bin/env python3
"""Phase 6A.1 — web payloads for the review-gated public-beta overlay.

Writes into data/release_overlays/rc6/web/ only. The Phase 5 payload tree is read for slug
mapping and is never written to, so every Phase 5 hash stays where it is.

Everything the browser needs is precomputed here. The application does no scientific
reaggregation at runtime: it reads a number and shows it, which is the only way the displayed
value can be tied to a build hash.
"""
from __future__ import annotations
import hashlib, json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OV = ROOT / "data/release_overlays/rc6"
WEB = OV / "web"
P5WEB = ROOT / "data/web"

TH = [("4A", "4 Å"), ("4_5A", "4.5 Å"), ("5A", "5 Å")]
WEIGHTS = ["unit_weighted_continuous", "unit_weighted_any_contact", "structure_weighted",
           "receptor_weighted", "ligand_weighted"]

GATE_EN = ("Public-beta pooled summaries exclude observations or structure slots whose unresolved "
           "review items can alter receptor identity, ligand identity, site classification, "
           "coordinate context, or aggregation eligibility. Metadata-only review items remain "
           "visible but do not automatically remove otherwise eligible data.")
GATE_TR = ("Public-beta toplu özetleri; reseptör kimliğini, ligand kimliğini, bölge sınıfını, "
           "koordinat bağlamını veya agregasyon uygunluğunu değiştirebilecek çözülmemiş inceleme "
           "kayıtlarına sahip gözlem ya da yapı yuvalarını dışlar. Yalnız metadata ile ilgili "
           "inceleme kayıtları görünür kalır, ancak başka bakımdan uygun veriyi otomatik olarak "
           "dışlamaz.")
ORIG_EN = "Original Phase 4 aggregate before public-beta review gating"
ORIG_TR = "Public-beta inceleme filtresi uygulanmadan önceki özgün Phase 4 agregasyonu"


def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


VOLATILE = ("generated_at",)


def content_hash(obj) -> str:
    """Hash the science, not the run. Mirrors the content_sha256/package_sha256 split used from
    Phase 1 onward: a re-run must be able to prove the content did not change even though the
    timestamp did."""
    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if k not in VOLATILE}
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def w(path: Path, obj) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    path.write_text(txt, encoding="utf-8")
    return content_hash(obj)


def main() -> int:
    fam_summ = rd(OV / "beta_family_site_class_summaries.jsonl")
    beta_units = {u["aggregation_unit_id"]: u for u in rd(OV / "beta_aggregation_units.jsonl")}
    slots = rd(OV / "structure_slot_eligibility.jsonl")
    impact = rd(OV / "review_impact.jsonl")
    excl = json.loads((OV / "beta_exclusion_summary.json").read_text(encoding="utf-8"))
    fvs = json.loads((OV / "family_validation_status.json").read_text(encoding="utf-8"))

    slug = {}
    for d in sorted((P5WEB / "families").iterdir()):
        if d.is_dir():
            m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            slug[m.get("family_id") or d.name.replace("ca-", "").replace("-", "_")] = d.name

    by_fam_site = defaultdict(dict)
    for r in fam_summ:
        fid, site = r["group_key"][0], r["group_key"][1]
        by_fam_site[fid][site] = r

    # per-family review-gate + validation payloads
    hashes = {}
    for fid, sites in sorted(by_fam_site.items()):
        s = slug.get(fid, "ca-" + fid.replace("_", "-"))
        fam_slots = [x for x in slots if x["major_family_id"] == fid]
        fam_units = [u for u in beta_units.values() if u["major_family_id"] == fid]
        gate = {
            "family_id": fid, "family_slug": s,
            "review_gate": "applied", "rule_version": excl["rule_version"],
            "explanation_en": GATE_EN, "explanation_tr": GATE_TR,
            "original_label_en": ORIG_EN, "original_label_tr": ORIG_TR,
            "units_total": len(fam_units),
            "units_unchanged": sum(1 for u in fam_units if u["beta_status"] == "unchanged"),
            "units_modified": sum(1 for u in fam_units if u["beta_status"] == "modified"),
            "units_removed": sum(1 for u in fam_units
                                 if u["beta_status"] == "removed_zero_denominator"),
            "structure_slots_total": len(fam_slots),
            "structure_slots_excluded": sum(1 for x in fam_slots
                                            if x["beta_eligibility"] == "review_blocked"),
            "structure_slots_warning_only": sum(1 for x in fam_slots
                                                if x["beta_eligibility"] == "warning_only"),
            "affecting_review_items": sorted({r for x in fam_slots for r in x["review_item_ids"]}),
            "site_classes": {},
        }
        for site, r in sorted(sites.items()):
            units_here = [u for u in fam_units if u["binding_site_class"] == site]
            den_before = sum(u["observations_total"] for u in units_here)
            den_after = sum(u["beta_eligible_observations_total"] for u in units_here)
            pos = []
            for p in r["positions"]:
                row = {"generic_position": p["generic_position"], "units": p["units"],
                       "units_estimable": p["units_estimable"], "status": p["status"]}
                for th, _ in TH:
                    for wt in WEIGHTS:
                        k = f"{wt}_{th}"
                        if k in p:
                            row[k] = p[k]
                pos.append(row)
            gate["site_classes"][site] = {
                "denominator_before_review_gate": den_before,
                "denominator_after_review_gate": den_after,
                "units_total": len(units_here),
                "units_removed": sum(1 for u in units_here
                                     if u["beta_status"] == "removed_zero_denominator"),
                "units_modified": sum(1 for u in units_here if u["beta_status"] == "modified"),
                "estimable": den_after > 0,
                "not_estimable_note_en": None if den_after else
                    "No eligible structure slot remains; the value is NA, not 0%.",
                "not_estimable_note_tr": None if den_after else
                    "Uygun yapı yuvası kalmadı; değer 0% değil NA'dır.",
                "positions": pos,
            }
        gate["coverage_warning_en"] = (
            f"{gate['structure_slots_excluded']} structure slot(s) excluded and "
            f"{gate['units_removed']} unit(s) removed by the review gate in this family."
            if (gate["structure_slots_excluded"] or gate["units_removed"]) else
            "No structure slot in this family is excluded by the review gate.")
        gate["coverage_warning_tr"] = (
            f"Bu ailede inceleme kapısı {gate['structure_slots_excluded']} yapı yuvasını dışladı "
            f"ve {gate['units_removed']} birimi kaldırdı."
            if (gate["structure_slots_excluded"] or gate["units_removed"]) else
            "Bu ailede inceleme kapısı hiçbir yapı yuvasını dışlamamaktadır.")
        hashes[f"{s}/review_gate"] = w(WEB / "families" / s / "review_gate.json", gate)

        vrows = [r for r in fvs["rows"] if r["major_family_id"] == fid]
        val = {"family_id": fid, "family_slug": s,
               "badge": fvs["per_family_badge"].get(fid, {}).get("badge"),
               "badge_tr": fvs["per_family_badge"].get(fid, {}).get("badge_tr"),
               "contact_definition": fvs["contact_definition"],
               "global_statement_en": fvs["global_statement_en"],
               "global_statement_tr": fvs["global_statement_tr"],
               "rows": vrows}
        hashes[f"{s}/validation"] = w(WEB / "families" / s / "validation.json", val)

    # global payloads
    per_item = [{"review_item_id": r["review_item_id"], "pdb_id": r["pdb_id"],
                 "issue_type": r["issue_type"], "aggregation_effect": r["aggregation_effect"],
                 "affected_scope": r["affected_scope"], "effect_reason": r["effect_reason"],
                 "affected_observations": r["affected_observations"],
                 "aggregation_unit_id": r["aggregation_unit_id"],
                 "rule_id": r["rule_id"]}
                for r in impact if r["aggregation_effect"] != "no_effect"]
    hashes["global/review_gate_index"] = w(WEB / "global" / "review_gate_index.json", {
        "rule_version": excl["rule_version"],
        "explanation_en": GATE_EN, "explanation_tr": GATE_TR,
        "original_label_en": ORIG_EN, "original_label_tr": ORIG_TR,
        "policy_wording_en": "open items visible and excluded from pooled analyses where required",
        "policy_wording_tr": ("açık kayıtlar görünür kalır ve gerektiği yerde havuzlanmış "
                              "analizlerden dışlanır"),
        "policy_wording_constraint_en": ("This is not 'all open items are excluded'. Most open "
                                         "items do not change a pooled metric."),
        "counts": {k: excl[k] for k in
                   ("human_review_required_items", "observations_blocked", "units_modified",
                    "units_removed", "units_unchanged", "observations_total", "units_total")},
        "effect_counts_open_items": excl["effect_counts_open_items"],
        "items": per_item})
    hashes["global/family_validation_status"] = w(
        WEB / "global" / "family_validation_status.json", fvs)

    idx = {"overlay": "rc6", "rule_version": excl["rule_version"], "hashes": hashes,
           "files": len(hashes)}
    txt = json.dumps(idx, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    (WEB / "overlay_payload_index.json").write_text(txt, encoding="utf-8")
    print(json.dumps({"families": len(by_fam_site), "payload_files": len(hashes),
                      "index_sha": hashlib.sha256(txt.encode()).hexdigest()[:16]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
