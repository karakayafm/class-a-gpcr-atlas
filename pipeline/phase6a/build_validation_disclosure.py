#!/usr/bin/env python3
"""Phase 6A.1 — cross-family contact-validation disclosure.

Builds the family x site-class validation matrix from the real data rather than from a hardcoded
list of families. A family/site-class combination that does not occur in the corpus is marked
not_applicable; it is never invented so the table looks complete.

The distinction this file exists to protect: the 5 A contact definition was reference-tested
against a small aminergic small-molecule set, and everything else inherited it. Saying
"validated for the Aminergic family" would claim ligand forms, receptor states and interface
types that test never touched.
"""
from __future__ import annotations
import hashlib, json
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P4 = ROOT / "data/intermediate/phase4"
OUT = ROOT / "data/release_overlays/rc6"
REG = ROOT / "data/pilots/phase3/aminergic_regression"

STATUS = {"reference_tested_within_scope", "transferred_without_family_specific_reference_test",
          "descriptive_interface_rule_not_independently_reference_tested",
          "covalent_relation_verified_contact_shell_not_independently_tested",
          "not_applicable", "unresolved"}


def rd(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    units = rd(P4 / "aggregation_units.jsonl")
    fam_manifest = json.loads((ROOT / "data/manifests/class_a_family_manifest.json")
                              .read_text(encoding="utf-8"))
    key = [k for k in fam_manifest if isinstance(fam_manifest[k], list)][0]
    FAMNAME = {f.get("source_id"): f.get("name") for f in fam_manifest[key]}

    reg = json.loads((REG / "regression_summary.json").read_text(encoding="utf-8"))
    cross = rd(REG / "exact_crosswalk.jsonl")
    reg_pdbs = sorted({c["pdb_id"] for c in cross})
    reg_equiv = sum(1 for c in cross if c.get("contact_equivalent"))
    reg_hash = hashlib.sha256((REG / "regression_summary.json").read_bytes()).hexdigest()

    # Which family x site_class x ligand_form combinations actually exist.
    combos = defaultdict(Counter)
    for u in units:
        combos[u["major_family_id"]][(u["binding_site_class"], u["ligand_entity_form"])] += 1

    AMINERGIC = "001_001"
    rows = []
    for fid in sorted(combos):
        for (site, form), n in sorted(combos[fid].items()):
            if site == "canonical_7tm_pocket" and form == "nonpolymer_residue":
                if fid == AMINERGIC:
                    status = "reference_tested_within_scope"
                    ref_status = (f"Cross-checked against the frozen aminergic project: "
                                  f"{len(cross)} observations across {len(reg_pdbs)} structures "
                                  f"exactly matched, {reg_equiv} contact-equivalent, "
                                  f"{reg['discrepancy_count']} discrepancies.")
                    ref_n = len(reg_pdbs)
                    ref_scope = ("aminergic small-molecule ligands, 5 A heavy-atom definition, "
                                 "generic positions contacted")
                    ind = ("The frozen project's own definition was independently reference-tested "
                           "against a QC table for nine aminergic small-molecule structures "
                           "(DD-07). This crosswalk tests consistency with that implementation; "
                           "it is not a second independent ground truth.")
                    lim = ("Covers small-molecule ligands only. Does not cover polymer ligands, "
                           "covalent adducts, every receptor state, or mutation and construct "
                           "variants within this family.")
                    tr = ("Aminergik küçük-molekül cebi: 5 A ağır-atom temas tanımı, donmuş "
                          f"aminergik projeye karşı {len(cross)} gözlemde çapraz kontrol "
                          f"edilmiştir ({reg['discrepancy_count']} uyuşmazlık). Bağımsız referans "
                          "testi dokuz aminergik küçük-molekül yapısıyla sınırlıdır. Bu kapsam "
                          "polimer ligandları, kovalent eklentileri ve tüm reseptör durumlarını "
                          "içermez.")
                    en = ("Reference-tested against nine aminergic small-molecule structures, and "
                          f"cross-checked against the frozen aminergic project over {len(cross)} "
                          f"observations ({reg['discrepancy_count']} discrepancies). The tested "
                          "scope is small-molecule pocket contacts under the 5 A heavy-atom "
                          "definition; it does not extend to polymer ligands, covalent adducts or "
                          "all receptor states.")
                else:
                    status = "transferred_without_family_specific_reference_test"
                    ref_status = "no family-specific reference test performed"
                    ref_n = 0
                    ref_scope = "none"
                    ind = "not performed"
                    lim = ("The contact definition is inherited from the aminergic "
                           "reference-tested workflow. No structures of this family were compared "
                           "against an independent reference set.")
                    tr = ("5 A ağır-atom temas tanımı, referans testi yapılmış aminergik iş "
                          "akışından aktarılmıştır. Bu aile için bağımsız, aileye özgü insan "
                          "doğrulaması henüz tamamlanmamıştır.")
                    en = ("The 5 A heavy-atom contact definition was transferred from the "
                          "aminergic reference-tested workflow. Independent family-specific human "
                          "validation has not yet been completed.")
            elif site in ("extracellular_polymer_interface", "tethered_ligand_interface"):
                status = "descriptive_interface_rule_not_independently_reference_tested"
                ref_status = "not reference-tested"
                ref_n = 0
                ref_scope = "none"
                ind = "not performed"
                lim = ("A 5 A shell around a polymer ligand is a descriptive interface "
                       "definition, not a validated biological interface threshold. It must not "
                       "be read as pocket validation.")
                tr = ("5 A değeri burada betimleyici bir reseptör–polimer arayüz kabuğu "
                      "tanımlar. Class A aileleri genelinde evrensel bir biyolojik arayüz eşiği "
                      "olarak bağımsız biçimde doğrulanmamıştır. Bu bir cep doğrulaması "
                      "değildir.")
                en = ("The 5 A value defines a descriptive receptor-polymer interface shell. It "
                      "has not been independently validated as a universal biological interface "
                      "threshold across Class A families.")
            elif site == "covalent_core_site":
                status = "covalent_relation_verified_contact_shell_not_independently_tested"
                ref_status = ("covalent linkage verifiable from deposited struct_conn records; "
                              "the surrounding 5 A shell is not reference-tested")
                ref_n = 0
                ref_scope = "covalent connectivity only"
                ind = "not performed for the contact shell"
                lim = ("The covalent bond itself is evidenced by deposited connectivity records. "
                       "No cross-family reference validation exists for the surrounding 5 A "
                       "contact shell.")
                tr = ("Kovalent bağ, çökeltilmiş struct_conn kayıtlarından doğrulanabilir. "
                      "Ancak çevredeki 5 A temas kabuğu için aileler arası bağımsız referans "
                      "doğrulaması bulunmamaktadır.")
                en = ("The covalent linkage is evidenced by deposited connectivity records. The "
                      "surrounding 5 A contact shell has no cross-family reference validation.")
            else:
                status = "unresolved"
                ref_status = "not characterised"
                ref_n = 0
                ref_scope = "none"
                ind = "not performed"
                lim = "Site class outside the characterised set."
                tr = "Bu bölge sınıfı için doğrulama durumu belirlenmemiştir."
                en = "Validation status for this site class has not been characterised."

            assert status in STATUS
            rows.append({
                "major_family_id": fid, "family_name": FAMNAME.get(fid, fid),
                "site_class": site, "ligand_entity_form": form,
                "aggregation_units": n,
                "contact_definition": "minimum heavy-atom distance <= 5 A, hydrogens excluded",
                "reference_test_status": ref_status,
                "reference_structure_count": ref_n,
                "reference_family": "001_001" if status == "reference_tested_within_scope" else None,
                "reference_ligand_scope": ref_scope,
                "independent_human_validation_status": ind,
                "transfer_status": status,
                "limitations": lim,
                "statement_tr": tr, "statement_en": en,
                "source_report": "reports/phase6a/CROSS_FAMILY_VALIDATION_DISCLOSURE.md",
                "source_hash": reg_hash})

    # families present in the taxonomy but contributing no aggregation unit
    for fid, name in sorted(FAMNAME.items()):
        if fid not in combos:
            rows.append({
                "major_family_id": fid, "family_name": name, "site_class": None,
                "ligand_entity_form": None, "aggregation_units": 0,
                "contact_definition": "minimum heavy-atom distance <= 5 A, hydrogens excluded",
                "reference_test_status": "no aggregation unit in this release",
                "reference_structure_count": 0, "reference_family": None,
                "reference_ligand_scope": "none",
                "independent_human_validation_status": "not applicable",
                "transfer_status": "not_applicable",
                "limitations": "This family contributes no pooled analysis unit in this release.",
                "statement_tr": "Bu aile bu sürümde havuzlanmış analiz birimi içermemektedir.",
                "statement_en": "This family contributes no pooled analysis unit in this release.",
                "source_report": "reports/phase6a/CROSS_FAMILY_VALIDATION_DISCLOSURE.md",
                "source_hash": reg_hash})

    # per-family badge, derived rather than asserted
    per_family = {}
    for fid in sorted(FAMNAME):
        fr = [r for r in rows if r["major_family_id"] == fid and r["transfer_status"] != "not_applicable"]
        st = {r["transfer_status"] for r in fr}
        if not st:
            badge, badge_tr = "not_applicable", "kapsam dışı"
        elif len(st) > 1:
            badge, badge_tr = "mixed_validation_scope", "karma doğrulama kapsamı"
        else:
            only = next(iter(st))
            badge = {"reference_tested_within_scope": "reference_tested_within_scope",
                     "transferred_without_family_specific_reference_test": "transferred_method",
                     "descriptive_interface_rule_not_independently_reference_tested":
                         "descriptive_interface_rule",
                     "covalent_relation_verified_contact_shell_not_independently_tested":
                         "covalent_shell_untested",
                     "unresolved": "unresolved"}[only]
            badge_tr = {"reference_tested_within_scope": "kapsam içinde referans testli",
                        "transferred_method": "aktarılmış yöntem",
                        "descriptive_interface_rule": "betimleyici arayüz kuralı",
                        "covalent_shell_untested": "kovalent kabuk test edilmemiş",
                        "unresolved": "belirsiz"}[badge]
        per_family[fid] = {"family_name": FAMNAME[fid], "badge": badge, "badge_tr": badge_tr,
                           "site_class_rows": len(fr),
                           "statuses": sorted(st)}

    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule_version": "phase6a1-validation-disclosure-1.0.0",
        "contact_definition": "minimum heavy-atom distance <= 5 A, hydrogens excluded",
        "global_statement_en": "Contact-rule validation varies by family and site class.",
        "global_statement_tr": "Temas kuralının doğrulanması aileye ve bölge sınıfına göre değişir.",
        "aminergic_reference_evidence": {
            "independent_reference_structures": 9,
            "independent_reference_scope": ("aminergic small-molecule structures checked against "
                                            "an independent QC table in the frozen project (DD-07)"),
            "crosswalk_observations": len(cross),
            "crosswalk_structures": len(reg_pdbs),
            "crosswalk_contact_equivalent": reg_equiv,
            "crosswalk_discrepancies": reg["discrepancy_count"],
            "crosswalk_is_independent_ground_truth": False,
            "note": ("The crosswalk tests consistency with a previously validated implementation. "
                     "It is not a second independent validation, and must not be reported as one.")},
        "families_total": len(FAMNAME),
        "rows_total": len(rows),
        "per_family_badge": per_family,
        "rows": rows,
        "allowed_status_vocabulary": sorted(STATUS),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    (OUT / "family_validation_status.json").write_text(txt, encoding="utf-8")
    # content hash with the timestamp stripped, so determinism is checkable
    _c = {k: v for k, v in doc.items() if k != "generated_at"}
    (OUT / "family_validation_status.content_sha256").write_text(
        hashlib.sha256(json.dumps(_c, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        + "\n", encoding="utf-8")
    print(json.dumps({"families": len(FAMNAME), "rows": len(rows),
                      "badges": Counter(v["badge"] for v in per_family.values()),
                      "sha256": hashlib.sha256(txt.encode()).hexdigest()[:16]},
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
