#!/usr/bin/env python3
"""Ligand labels that change from one deposition to the next, and label corrections waiting for a build.

The atlas groups ligands by the pharmacological label (binding mode) recorded for each deposition. The
same compound can carry different labels in different entries - carazolol is an antagonist in some
beta-adrenoceptor entries and an inverse agonist in others - so a comparison that separates two labels
can partly be comparing annotations. This lists every compound that carries more than one label within
a family, from the published payloads (read only), and writes:

    curation/ligand_label_review/label_conflicts.csv     every compound x family with more than one label
    site/data/web/overlay/curation_pending.json          corrections decided here, applied by the site's
                                                          loader until the next build carries them, and
                                                          the Antagonist / Inverse agonist conflicts the
                                                          contact map warns about

A correction decided here is also written into pipeline/phase5/build_payloads.py (CURATED_LIGAND_ROLES
and CURATED_STRUCTURE_NOTES), which is where it becomes permanent; the overlay only bridges the gap.

    python3 curation/ligand_label_review/scan_labels.py
"""
from __future__ import annotations
import csv, datetime, json, time, urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "site/data/web"
OUT_CSV = Path(__file__).with_name("label_conflicts.csv")
OUT_OVERLAY = WEB / "overlay/curation_pending.json"
OUT_REVIEW = Path(__file__).with_name("label_review_candidates.csv")
CACHE = ROOT / "data/cache/gpcrdb_structures"
AGONISTS = {"Agonist", "Agonist (partial)"}

# Decided corrections. Key: ligand entity id. Each is also in build_payloads.py.
CORRECTIONS = {
    "9IJD:LE:np:CAU": {
        "pdb": "9IJD", "ligand": "Carazolol", "from": "Inverse agonist", "to": "Agonist",
        "decided": "2026-10-02",
        "evidence": "RCSB 9IJD 'Carazolol-activated human beta3 adrenergic receptor', active state with Gs; "
                    "primary citation 'Molecular Mechanism of the beta3AR Agonist Activity of a beta-Blocker', "
                    "ChemPlusChem 2024, doi:10.1002/cplu.202400288; GPCRdb lists (S)-carazolol in 9IJD as Agonist.",
        "note_en": "Carazolol was recorded here as an inverse agonist. 9IJD is the carazolol-activated human beta3 "
                   "receptor in its active, Gs-coupled state, and the primary publication and GPCRdb describe "
                   "carazolol as an agonist at beta3. The label is corrected to Agonist; until the next build the "
                   "correction is applied by the site, and precomputed aggregates still count the old label.",
        "note_tr": "Carazolol burada ters agonist olarak kayıtlıydı. 9IJD, carazolol ile aktive edilmiş insan beta3 "
                   "reseptörünün Gs'ye bağlı aktif yapısıdır; birincil yayın ve GPCRdb carazolol'ü beta3'te agonist "
                   "olarak tanımlar. Etiket Agonist olarak düzeltildi; bir sonraki build'e kadar düzeltmeyi site "
                   "uygular, önceden hesaplanmış toplamlar ise eski etiketi saymaya devam eder."},
    "8DCS:LE:np:P32": {
        "pdb": "8DCS", "ligand": "Cyanopindolol", "from": "Antagonist", "to": "Agonist (partial)",
        "decided": "2026-10-03",
        "evidence": "RCSB 8DCS 'Cryo-EM structure of cyanopindolol-bound beta1-adrenergic receptor in complex with "
                    "heterotrimeric Gs-protein', keywords 'partial agonist'; active state with Gs; primary citation "
                    "'Structures of beta1-adrenergic receptor in complex with Gs and ligands of different efficacies' "
                    "(2022); GPCRdb lists cyanopindolol in 8DCS as Agonist (partial).",
        "note_en": "Cyanopindolol was recorded here as an antagonist. 8DCS is the turkey beta1 receptor bound to "
                   "cyanopindolol in complex with Gs, in its active state; the entry and GPCRdb describe cyanopindolol "
                   "here as a partial agonist. The label is corrected to Agonist (partial); until the next build the "
                   "correction is applied by the site, and precomputed aggregates still count the old label.",
        "note_tr": "Siyanopindolol burada antagonist olarak kayıtlıydı. 8DCS, siyanopindolol bağlı hindi beta1 "
                   "reseptörünün Gs ile kompleksidir ve aktif durumdadır; girdi ve GPCRdb siyanopindolol'ü burada kısmi "
                   "agonist olarak tanımlar. Etiket Agonist (kısmi) olarak düzeltildi; bir sonraki build'e kadar "
                   "düzeltmeyi site uygular, önceden hesaplanmış toplamlar ise eski etiketi saymaya devam eder."},
    "7C61:LE:np:ERM": {
        "pdb": "7C61", "ligand": "ergotamine", "from": "Antagonist", "to": "Agonist",
        "decided": "2026-10-03",
        "evidence": "GPCRdb lists ergotamine in 7C61 as Agonist; the same compound at the same receptor (5-HT1B, 4IAR) "
                    "is recorded as Agonist in the atlas and in GPCRdb.",
        "note_en": "Ergotamine was recorded here as an antagonist. GPCRdb lists it as an agonist in 7C61, and the "
                   "same compound at the same receptor (4IAR) is an agonist in the atlas. The label is corrected to "
                   "Agonist; until the next build the correction is applied by the site.",
        "note_tr": "Ergotamin burada antagonist olarak kayıtlıydı. GPCRdb 7C61'de onu agonist olarak listeler ve "
                   "aynı bileşik aynı reseptörde (4IAR) atlasta da agonisttir. Etiket Agonist olarak düzeltildi; bir "
                   "sonraki build'e kadar düzeltmeyi site uygular."},
}
BLOCKERS = {"Antagonist", "Inverse agonist"}


def gpcrdb(pdb):
    """GPCRdb's own record of the structure (cached; read only)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{pdb}.json"
    if not path.exists():
        with urllib.request.urlopen(f"https://gpcrdb.org/services/structure/{pdb}/", timeout=60) as r:
            path.write_bytes(r.read())
        time.sleep(0.3)
    return json.loads(path.read_text())


def chem_name(comp):
    """RCSB chemical component name, for compounds the atlas names only by a ChEMBL id."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"chemcomp_{comp}.json"
    if not path.exists():
        with urllib.request.urlopen(f"https://data.rcsb.org/rest/v1/core/chemcomp/{comp}", timeout=60) as r:
            path.write_bytes(r.read())
        time.sleep(0.2)
    d = json.loads(path.read_text())
    # A common name where RCSB lists one among the synonyms (letters only, e.g. CARVEDILOL), else the
    # systematic name.
    plain = [x.get("name", "") for x in d.get("rcsb_chem_comp_synonyms") or []
             if x.get("name") and x["name"].replace("-", "").isalpha()]
    return min(plain, key=len) if plain else (d.get("chem_comp") or {}).get("name", comp)


def display(name, comps):
    if name and name.upper().startswith("CHEMBL") and comps:
        return f"{chem_name(comps[0]).capitalize()} ({name})"
    return name


def main():
    manifest = json.loads((WEB / "global/manifest.json").read_text())
    rows, conflicts, candidates = [], {}, []
    for fam in manifest["families"]:
        path = WEB / "families" / fam["slug"] / "structures.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        by = defaultdict(lambda: defaultdict(set))       # compound -> label -> {(pdb, unit)}
        names = {}
        for s in data["structures"]:
            for o in s["observations"]:
                mode = o.get("binding_mode")
                if not mode or mode in ("Not specified", "unknown"):
                    continue
                if o.get("ligand_entity_id") in CORRECTIONS:
                    mode = CORRECTIONS[o["ligand_entity_id"]]["to"]
                comps = o.get("ligand_components") or []
                key = ",".join(sorted(comps)) if comps else (o.get("ligand_name") or "").lower()
                if not key:
                    continue
                names.setdefault(key, o.get("ligand_name") or key)
                by[key][mode].add((s["pdb_id"], s["receptor_entry_name"]))
        # Rule A: a blocker label on a structure that is active or carries a transducer.
        # Rule B: the same compound at the same receptor, an agonist in one entry and a blocker in another.
        per_receptor = defaultdict(lambda: defaultdict(set))
        for s_ in data["structures"]:
            for o in s_["observations"]:
                mode = CORRECTIONS.get(o.get("ligand_entity_id"), {}).get("to", o.get("binding_mode"))
                comps = o.get("ligand_components") or []
                if comps:
                    per_receptor[(s_["receptor_entry_name"], ",".join(sorted(comps)))][mode].add(s_["pdb_id"])
        for s_ in data["structures"]:
            for o in s_["observations"]:
                if o.get("ligand_entity_id") in CORRECTIONS or o.get("binding_site_class") in (None, "unresolved"):
                    continue
                mode = o.get("binding_mode"); comps = o.get("ligand_components") or []
                rules = []
                if mode in BLOCKERS and (s_.get("structural_state") == "active" or
                                         s_.get("transducer_class") not in (None, "transducer_free")):
                    rules.append("A")
                if comps and mode in BLOCKERS | AGONISTS:
                    other = per_receptor[(s_["receptor_entry_name"], ",".join(sorted(comps)))]
                    opposite = AGONISTS if mode in BLOCKERS else BLOCKERS
                    if any(m in other for m in opposite):
                        rules.append("B")
                if rules:
                    candidates.append({"rule": "+".join(rules), "family": fam["slug"], "pdb": s_["pdb_id"],
                        "ligand_entity_id": o.get("ligand_entity_id"), "receptor": s_["receptor_entry_name"],
                        "state": s_.get("structural_state"), "transducer": s_.get("transducer_class"),
                        "representative": s_.get("analysis_unit_representative"),
                        "compound": display(o.get("ligand_name"), comps), "atlas_label": mode,
                        "same_receptor_labels": "; ".join(f"{m}: {' '.join(sorted(p))}" for m, p in
                            sorted(per_receptor[(s_["receptor_entry_name"], ",".join(sorted(comps)))].items())) if comps else ""})
        fam_conf = []
        for key, labels in by.items():
            if len(labels) < 2:
                continue
            for mode, entries in sorted(labels.items()):
                rows.append({"family": fam["slug"], "family_name": fam["name"], "compound": names[key],
                             "components": key, "label": mode, "n_structures": len(entries),
                             "units": " ".join(sorted({u for _, u in entries})),
                             "pdb_ids": " ".join(sorted(p for p, _ in entries))})
            if BLOCKERS <= set(labels):
                fam_conf.append({"ligand": display(names[key], key.split(",")), "components": key,
                                 "labels": {m: sorted({u for _, u in labels[m]}) for m in sorted(labels)}})
        if fam_conf:
            conflicts[fam["slug"]] = sorted(fam_conf, key=lambda x: x["ligand"].lower())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    for c in candidates:
        try:
            g = gpcrdb(c["pdb"])
            c["gpcrdb_state"] = g.get("state")
            c["gpcrdb_ligands"] = "; ".join(f"{l.get('name')}: {l.get('function')}" for l in g.get("ligands") or [])
        except Exception as e:                       # noqa: BLE001 - recorded, not fatal
            c["gpcrdb_state"], c["gpcrdb_ligands"] = "?", f"lookup failed: {type(e).__name__}"
    with OUT_REVIEW.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["rule", "family", "pdb", "ligand_entity_id", "receptor", "state", "transducer",
                                           "representative", "compound", "atlas_label", "gpcrdb_state", "gpcrdb_ligands",
                                           "same_receptor_labels"])
        w.writeheader(); w.writerows(candidates)
    print(f"{len(candidates)} review candidates -> {OUT_REVIEW.relative_to(ROOT)}")
    OUT_OVERLAY.write_text(json.dumps({
        "schema": "curation_pending", "schema_version": "1.0.0", "generated": datetime.date.today().isoformat(),
        "note": "Applied by the site's loader until the next build; the permanent corrections are in "
                "pipeline/phase5/build_payloads.py. Precomputed aggregates are not changed by this file.",
        "corrections": CORRECTIONS,
        "blocker_label_conflicts": conflicts}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len({(r['family'], r['components']) for r in rows})} compound x family pairs with more than one label "
          f"-> {OUT_CSV.relative_to(ROOT)}")
    print("antagonist / inverse agonist conflicts:", {k: [c["ligand"] for c in v] for k, v in conflicts.items()})


if __name__ == "__main__":
    main()
