"""Turn the screen into the review list: every flagged observation, what the record says, what the
geometry and the primary publication say, and a proposed decision. Run after screen_site_class.py.

    python3 curation/site_class_review/build_candidates.py
"""
import csv, glob, json, pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path("site/data/web")
DISTANCE, OVERLAP = 12.0, 0.35          # flag: centroid > 12 Å from the pocket centre, or < 35% core

# Checked by the reviewer on 2026-09-30 and confirmed as not in the orthosteric pocket.
# (suggested target class, other fields to change, what the reviewer and the geometry show)
ROLE = "ligand_role pharmacological_orthosteric_ligand -> allosteric"
CONFIRMED = {
  "8HNN": ("other_site", ROLE, "below the orthosteric pocket between TM3, TM5 and TM6 (5x47, 5x51, 5x62, 6x38, 6x44)"),
  "5O9H": ("lipid_facing_site", ROLE, "extra-helical, TM3-TM4-TM5 outer face; the same ligand (9P2) is already "
           "curated lipid_facing_site in 6C1Q (CURATED_SITE_CLASSES)"),
  "9IYB": ("lipid_facing_site", ROLE, "outside the bundle, lower leaflet, TM2-TM3-TM4-ICL2. The same ligand (A1D5Q) "
           "is curated bitopic_or_multi_region_site in 8XXU/8XXV, but sits in the same place there and reaches no "
           "pocket position; see the related rows"),
  "9K1C": ("lipid_facing_site", ROLE, "outside the bundle, lower leaflet, TM3-TM4-TM5-ICL2"),
  "8TB7": ("intracellular_allosteric_pocket", ROLE, "intracellular face, TM3-TM5-TM6-TM7-H8"),
  "8IKG": ("lipid_facing_site", ROLE, "outside the bundle, TM2-TM3-TM4"),
  "8IKH": ("lipid_facing_site", ROLE, "outside the bundle, TM2-TM3-TM4"),
  "6U1N": ("extracellular_allosteric_pocket",
           "binding_mode Agonist -> PAM; ligand_role -> positive_allosteric_modulator",
           "GPCRdb lists two ligands for 6U1N: iperoxo (IXO) 'Agonist' and LY2119620 (2CU) 'PAM'. Only 2CU is "
           "modelled; the agonist label reached it from the absent iperoxo. The atlas carries LY2119620 as PAM in "
           "4MQT, 7T94, 7T96, 7V68 and Ago-PAM in 6OIK, all extracellular_allosteric_pocket (CURATED_SITE_CLASSES). "
           "Literature: M2/M4 PAM, does not compete at the orthosteric site (Croy et al. 2014, doi:10.1124/mol.114.091751; "
           "Schober et al. 2014, doi:10.1124/mol.114.091785; Kruse et al. 2013, doi:10.1038/nature12735). "
           "The absent iperoxo has no annotated_not_observed record either."),
  "8W8R": ("other_site", ROLE,
           "two copies of U7D (chains F and G), both outside the helical bundle; authors: 'side pocket' "
           "(doi:10.1038/s41589-023-01456-6)"),
  "8W8S": ("other_site", ROLE,
           "two copies of U7D (chains B and C), both outside the helical bundle; authors: 'side pocket' "
           "(doi:10.1038/s41589-023-01456-6)"),
}
# Proposed from geometry plus the publication, after the reviewer's first pass.
# (proposed site class, other fields to change, confidence, evidence, reference)
PROPOSED = {
  "5TZY": ("bitopic_or_multi_region_site", "ligand_role -> allosteric (ago-allosteric site)", "medium",
           "Reviewer: extends from the lipid side into the orthosteric region. Contacts span the TM3-TM4 outer "
           "groove (3x26-3x30, 4x54-4x62) and core positions (3x33, 3x37, 5x43, 6x51, 6x55). The TAK-875 site "
           "MK-8666 shares is described as a 'non-canonical binding pocket' entered 'via the lipid bilayer' "
           "(Srivastava et al. 2014, doi:10.1038/nature13494). The 5TZY paper's 'lipid-facing' pocket is the "
           "AgoPAM's, not MK-8666's. lipid_facing_site is the alternative; bitopic is a permitted transition "
           "from canonical, lipid_facing is not. The same ligand is already curated bitopic in 5TZR.",
           "doi:10.1038/nsmb.3417; doi:10.1038/nature13494"),
  "8EJC": ("bitopic_or_multi_region_site", "ligand_role -> allosteric (ago-allosteric site)", "medium",
           "The flagged ligand is 2YB, TAK-875 (fasiglifam), not a fatty acid. It is curated bitopic in 4PHU, "
           "where the site is described as a 'non-canonical binding pocket' entered via the lipid bilayer "
           "(doi:10.1038/nature13494). The paper's 'orthosteric pocket for fatty acids' refers to other ligands.",
           "doi:10.1073/pnas.2219569120; doi:10.1038/nature13494"),
  "8EJK": ("bitopic_or_multi_region_site", "ligand_role -> allosteric (ago-allosteric site)", "medium",
           "As 8EJC (TAK-875, 2YB).", "doi:10.1073/pnas.2219569120; doi:10.1038/nature13494"),
  "8HQM": ("extended_orthosteric_pocket", "", "medium",
           "Reviewer: slightly outside, above the pocket. The endogenous agonist 9-HODE (8HQN) sits deeper (7.7 A "
           "from the pocket centre, not flagged); NPGLY here shares its upper positions (45x51, 45x52, 6x58, 6x62, "
           "7x27, 7x30, 7x31, 7x34), i.e. the vestibule end of the same pocket. Permitted transition from canonical.",
           "doi:10.1038/s42255-023-00899-4"),
  "8HVI": ("extended_orthosteric_pocket", "", "medium",
           "As 8HQM; NOX-6-7 sits higher still (contacts TM7 7x24-7x31, ECL1, ECL2 only).",
           "doi:10.1038/s42255-023-00899-4"),
}
# Flagged by the screen but the publication places the ligand in the receptor's own orthosteric site.
KEEP = {
  "6LI0": "Recommended keep, reviewer undecided. ECL2 fills GPR52's major pocket, and the ligand sits in the "
          "TM1-TM2-TM7 minor pocket (1x32-1x39, 2x57-2x64, 3x28, 3x32, 7x31-7x42, 45x51), which the authors call a "
          "side pocket (doi:10.1038/s41586-020-2019-0). The same positions are contacted by 45 canonical-pocket "
          "ligands in other receptors (lipid 28, chemokine 6, peptide 4, nucleotide 4), so calling them a separate "
          "site for GPR52 alone would make the class depend on the receptor rather than on the place.",
  "8HMP": "As 6LI0 (same ligand, same place).",
  "8IYX": "Authors: YL-365 binds 'in a portion of the orthosteric binding pocket' (doi:10.1073/pnas.2308435120).",
  "4XNW": "Authors: MRS2500 'recognizes a binding site within the seven transmembrane bundle' (doi:10.1038/nature14287).",
  "7XXH": "Nucleotide agonist at the P2Y1 orthosteric site described for MRS2500 (4XNW); shallow by Class A standards.",
  "8WJX": "As 7XXH.",
  "7PX4": "Antagonist in the A2A pocket, extending into the vestibule (core overlap 0.85).",
  "7PYR": "As 7PX4 (core overlap 0.90).",
  "8XBH": "Centroid 8.3 A from the pocket centre; flagged only on core overlap (0.34) against a family core dominated by other receptors.",
}
# Outside the canonical screen, found while checking it: recorded in another class, also wrong.
RELATED = [dict(status="related_non_canonical", pdb="5TZY", receptor="ffar1_human", component="7OS",
  ligand="AgoPAM AP8", binding_mode="PAM", ligand_role="positive_allosteric_modulator",
  recorded_site_class="bitopic_or_multi_region_site (observation); unresolved (residues)",
  proposed_site_class="lipid_facing_site", other_changes="", confidence="high",
  evidence="Authors: 'a novel lipid-facing AgoPAM-binding pocket outside the transmembrane helical bundle'. "
           "Centroid 19.4 A from the pocket centre, 15.6 A towards the intracellular side, at the helix surface; "
           "contacts TM2-TM5 and ICL2 - the same place as 9K1C, confirmed lipid-facing.",
  reference="doi:10.1038/nsmb.3417", distance_to_pocket="19.4", axial="-15.6", radial="11.6",
  contacted_segments="2 3 4 5 34", decided_by="", decided_on="")]
for _pdb, _d, _ax, _rad in (("8XXU", "30.5", "-22.3", "20.8"), ("8XXV", "30.3", "-22.3", "20.5")):
    RELATED.append(dict(status="existing_curation_questioned", pdb=_pdb, receptor="pd2r2_human", component="A1D5Q",
      ligand="", binding_mode="Agonist", ligand_role="",
      recorded_site_class="bitopic_or_multi_region_site (CURATED_SITE_CLASSES); unresolved (residues)",
      proposed_site_class="lipid_facing_site", other_changes="", confidence="high",
      evidence="Curated bitopic, but the ligand is ~30 A below and outside the helical bundle and contacts only "
               "TM2-TM5 outer faces and ICL2 (2x42, 3x41-3x52, 4x38-4x49, 5x53, 34x52-34x57) - no pocket position. "
               "Same place as in 9IYB, confirmed not orthosteric.",
      reference="", distance_to_pocket=_d, axial=_ax, radial=_rad, contacted_segments="2 3 4 5 34",
      decided_by="", decided_on=""))
DAY = "2026-09-30"
DECISIONS = {
  "8EJC": dict(status="accepted", on=DAY), "8EJK": dict(status="accepted", on=DAY),
  "5TZY": dict(status="accepted", on=DAY), "8HQM": dict(status="accepted", on=DAY),
  "8HVI": dict(status="accepted", on=DAY), "6LI0": dict(status="accepted_keep", on=DAY),
  "8HMP": dict(status="accepted_keep", on=DAY),
  "MRGPR": dict(status="accepted_keep", on=DAY, proposed="canonical_7tm_pocket"),
  "8XXU": dict(status="not_a_ligand", on=DAY, proposed="(none - membrane lipid)",
               note="Reviewer: apo structure. A1D5Q is phosphatidylinositol (1-palmitoyl-2-oleoyl), a membrane "
                    "lipid, and is not to be counted as a ligand; it is to be shown under a lipid layer instead."),
  "8XXV": dict(status="not_a_ligand", on=DAY, proposed="(none - membrane lipid)",
               note="As 8XXU: apo; A1D5Q is phosphatidylinositol."),
  "9IYB": dict(status="not_a_ligand", on=DAY, proposed="(none - membrane lipid)",
               note="The record names this observation PGD2 (Agonist), but the only hetero group modelled is A1D5Q, "
                    "phosphatidylinositol - the same lipid as 8XXU/8XXV. PGD2 is annotated and absent from the "
                    "coordinates, and its label reached the lipid, as iperoxo's reached LY2119620 in 6U1N."),
}
SHALLOW = ("mrgx1_human", "mrgx2_human", "mrgx4_human", "mrgrd_human")   # MRGPR family


def main():
    screen = list(csv.DictReader(open(HERE / "site_class_screen.csv")))
    refs = {}
    for f in glob.glob(str(ROOT / "families/*/references.json")):
        for s in json.load(open(f))["structure_sources"]:
            refs[s["pdb_id"]] = s.get("primary_citation") or {}
    num = lambda r, k: float(r[k]) if r[k] not in ("", None) else None
    out = []
    for r in screen:
        d, ov = num(r, "distance_to_pocket"), num(r, "core_overlap")
        flagged = (d is not None and d > DISTANCE) or (ov is not None and ov < OVERLAP)
        if not (flagged or r["pdb"] in CONFIRMED):
            continue
        c = refs.get(r["pdb"], {})
        row = {k: r[k] for k in ("pdb", "receptor", "component", "ligand", "binding_mode", "ligand_role",
                                 "method", "distance_to_pocket", "axial", "radial", "bundle_radius",
                                 "core_overlap", "contacted_segments", "positions")}
        row.update(recorded_site_class="canonical_7tm_pocket",
                   primary_citation=(c.get("doi") and "doi:" + c["doi"]) or "", decided_by="", decided_on="")
        if r["pdb"] in CONFIRMED:
            site, other, note = CONFIRMED[r["pdb"]]
            row.update(status="confirmed_misclassified", proposed_site_class=site, other_changes=other,
                       confidence="confirmed", evidence=note, reference=row["primary_citation"], decided_on="2026-09-30")
        elif r["pdb"] in PROPOSED:
            site, other, conf, ev, ref = PROPOSED[r["pdb"]]
            row.update(status="proposed_reclassification", proposed_site_class=site, other_changes=other,
                       confidence=conf, evidence=ev, reference=ref)
        elif r["pdb"] in KEEP:
            row.update(status="keep", proposed_site_class="canonical_7tm_pocket", other_changes="",
                       confidence="", evidence=KEEP[r["pdb"]], reference=row["primary_citation"])
        elif r["receptor"] in SHALLOW:
            row.update(status="policy_decision", proposed_site_class="canonical_7tm_pocket (recommended)",
                       other_changes="", confidence="",
                       evidence="Recommended: keep canonical_7tm_pocket. The atlas's site classes are defined by the ligand's relation to the orthosteric ligand, not by place: in MRGPRX1 the small-molecule agonist (8DWH) shares 10 of its 13 positions with the peptide agonist BAM8-22 (8DWG), while the PAM ML382 in 8DWG sits in the TM1-TM2-TM3-TM6-TM7 region (3x32, 3x33, 6x51, 7x38) that is the classical pocket elsewhere, shares none, and is already curated extracellular_allosteric_pocket. The shallow TM3-TM6 site is therefore these receptors' orthosteric site (MrgD: 'beta-alanine is bound to a shallow pocket at the extracellular domains'). extended_orthosteric_pocket would describe a pocket reaching up from the classical one, which is not what these ligands do.",
                       reference=row["primary_citation"])
        else:
            row.update(status="unreviewed", proposed_site_class="", other_changes="", confidence="",
                       evidence="", reference=row["primary_citation"])
        out.append(row)
    out.extend(RELATED)
    # The reviewer's decisions, recorded where they were made.
    for row in out:
        d = DECISIONS.get(row["pdb"]) or (DECISIONS.get("MRGPR") if row["status"] == "policy_decision" else None)
        if d and not (row["pdb"] == "5TZY" and row["component"] == "7OS" and "7OS" not in d.get("components", "7OS")):
            row.update(status=d["status"], decided_on=d["on"])
            if d.get("note"):
                row["evidence"] = d["note"] + " " + row.get("evidence", "")
            if "proposed" in d:
                row["proposed_site_class"] = d["proposed"]
    order = {"confirmed_misclassified": 0, "not_a_ligand": 1, "accepted": 2, "proposed_reclassification": 3,
             "related_non_canonical": 4, "existing_curation_questioned": 5, "accepted_keep": 6,
             "policy_decision": 7, "keep": 8, "unreviewed": 9}
    out.sort(key=lambda r: (order[r["status"]], r["receptor"], r["pdb"]))
    cols = ["status", "pdb", "receptor", "component", "ligand", "binding_mode", "ligand_role",
            "recorded_site_class", "proposed_site_class", "other_changes", "confidence", "evidence",
            "reference", "method", "distance_to_pocket", "axial", "radial", "bundle_radius",
            "core_overlap", "contacted_segments", "positions", "decided_by", "decided_on"]
    with open(HERE / "site_class_candidates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(out)
    from collections import Counter
    print(Counter(r["status"] for r in out), "->", HERE / "site_class_candidates.csv")


if __name__ == "__main__":
    main()
