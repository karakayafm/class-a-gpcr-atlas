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
import csv, datetime, json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "site/data/web"
OUT_CSV = Path(__file__).with_name("label_conflicts.csv")
OUT_OVERLAY = WEB / "overlay/curation_pending.json"

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
}
BLOCKERS = {"Antagonist", "Inverse agonist"}


def main():
    manifest = json.loads((WEB / "global/manifest.json").read_text())
    rows, conflicts = [], {}
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
                fam_conf.append({"ligand": names[key], "components": key,
                                 "labels": {m: sorted({u for _, u in labels[m]}) for m in sorted(labels)}})
        if fam_conf:
            conflicts[fam["slug"]] = sorted(fam_conf, key=lambda x: x["ligand"].lower())
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
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
