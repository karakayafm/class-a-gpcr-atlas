"""Every lipid and detergent in the viewer bundles, and every one the atlas counts as a ligand.

Two outputs, for two decisions:

  lipid_components.csv   one row per chemical component found in any bundle that is a membrane
                         lipid or a detergent - by the component reference, or by its name. This is
                         what a "Show lipids" layer would draw.
  lipid_as_ligand.csv    one row per observation whose ligand is such a component. Lipid receptors
                         have lipid ligands (LPA, S1P, prostaglandins, fatty acids), so nothing here
                         is demoted automatically: each row says why it was flagged and waits for a
                         decision.

Standard library only. Run from the repository root:
    python3 curation/lipid_review/audit_lipids.py
"""
import collections, csv, glob, json, pathlib, re

ROOT = pathlib.Path("site/data/web")
HERE = pathlib.Path(__file__).resolve().parent
REF = json.load(open("config/component_reference.json"))
CURATED = {k: v[1] for k, v in REF["curated_components"].items()}
LIPID_ROLES = {"membrane_lipid", "detergent"}
# Names the component reference does not cover: phospholipids and lysolipids written out
# systematically, sterols and their esters, monoacylglycerols, and the common detergents.
NAME_RULES = [
    ("membrane_lipid", r"PHOSPHATIDYL|PHOSPHOCHOLINE|PHOSPHOETHANOLAMINE|PHOSPHOSERINE|GLYCERO-?3-?PHOSPHO|"
                       r"PHOSPHORYL\].*OXY-PROPAN|INOSITOL.*PHOSPHO|PHOSPHO.*INOSITOL|"
                       r"(HEXADECANOYL|OCTADECANOYL|OCTADEC-9-ENOYL|OLEOYL|PALMITOYL).*(OXY)?-?PROPAN"),
    ("membrane_lipid", r"CHOLESTER|STEROL\b|HEMISUCCINATE|\bLANOSTEROL|ERGOSTEROL"),
    ("membrane_lipid", r"MONOOLEIN|MONO-?OLEOYL|GLYCERYL MONO|1-OLEOYL-R-GLYCEROL|\b2,3-DIHYDROXYPROPYL.*(OCTADEC|HEXADEC)"),
    ("membrane_lipid", r"^(PALMITIC|OLEIC|STEARIC|MYRISTIC|LAURIC|DECANOIC|HEXADECANOIC|OCTADECANOIC) ACID$"),
    ("detergent", r"MALTOSIDE|GLUCOSIDE|GLUCOPYRANOSIDE|DIGITONIN|NEOPENTYL|GLYCO-?DIOSGENIN|\bGDN\b|"
                  r"DODECYL|LAURYL|OCTYL.*GLUC|CHOLAMIDOPROPYL|\bCHAPS"),
]


def cif_tokens(text):
    """mmCIF values: bare words, quoted strings and ;-delimited multi-line text fields."""
    i, n, out = 0, len(text), []
    while i < n:
        c = text[i]
        if c == ";" and (i == 0 or text[i - 1] == "\n"):
            j = text.find("\n;", i + 1)
            out.append(text[i + 1:j].strip()); i = j + 2; continue
        if c in " \t\n\r":
            i += 1; continue
        if c in "'\"":
            j = i + 1
            while j < n and not (text[j] == c and (j + 1 == n or text[j + 1] in " \t\n\r")):
                j += 1
            out.append(text[i + 1:j]); i = j + 1; continue
        j = i
        while j < n and text[j] not in " \t\n\r":
            j += 1
        out.append(text[i:j]); i = j
    return out


def entity_names(cif_text):
    """component id -> name, from the chem_comp category of a bundle."""
    m = re.search(r"loop_\s*\n((?:_chem_comp\.\S+\s*\n)+)(.*?)\n#", cif_text, re.S)
    if not m:
        return {}
    hdr = re.findall(r"_chem_comp\.(\S+)", m.group(1))
    toks = cif_tokens(m.group(2))
    rows = [toks[k:k + len(hdr)] for k in range(0, len(toks) - len(hdr) + 1, len(hdr))]
    return {r[hdr.index("id")]: r[hdr.index("name")].upper() for r in rows}


def classify(comp, name):
    if comp in CURATED:
        return CURATED[comp], "component reference"
    for role, pat in NAME_RULES:
        hit = re.search(pat, name or "")
        if hit:
            return role, "name matches '" + hit.group(0)[:30] + "'"
    return None, ""


def main():
    obs_by_pdb = {}
    for f in glob.glob(str(ROOT / "families/*/structures.json")):
        for s in json.load(open(f))["structures"]:
            obs_by_pdb[s["pdb_id"]] = (s, pathlib.Path(f).parent.name)
    comps = collections.defaultdict(lambda: dict(name="", role="", basis="", structures=set(),
                                                 as_ligand=set()))
    ligand_rows = []
    for pdb_dir in sorted((ROOT / "structures").iterdir()):
        cif = pdb_dir / "viewer.cif"
        if not cif.exists():
            continue
        text = cif.read_text()
        names = entity_names(text)
        present = collections.Counter(l.split()[5] for l in text.splitlines() if l.startswith("HETATM"))
        s, fam = obs_by_pdb.get(pdb_dir.name, (None, ""))
        ligand_comps = {}
        for o in (s or {}).get("observations", []):
            for c in o.get("ligand_components") or []:
                ligand_comps[c] = o
        for comp in set(present) | set(ligand_comps):
            role, basis = classify(comp, names.get(comp, ""))
            if role not in LIPID_ROLES:
                continue
            e = comps[comp]
            e.update(name=names.get(comp, e["name"]) or e["name"], role=role, basis=basis)
            if comp in present:
                e["structures"].add(pdb_dir.name)
            if comp in ligand_comps:
                o = ligand_comps[comp]
                e["as_ligand"].add(pdb_dir.name)
                ligand_rows.append(dict(
                    pdb=pdb_dir.name, family=fam, receptor=s["receptor_entry_name"], apo_status=s["apo_status"],
                    component=comp, component_name=names.get(comp, ""), lipid_class=role, basis=basis,
                    recorded_ligand_name=o.get("ligand_name", ""), binding_mode=o.get("binding_mode", ""),
                    ligand_role=o.get("ligand_role", ""), binding_site_class=o.get("binding_site_class", ""),
                    other_ligands="; ".join(sorted({(x.get("ligand_name") or "")[:40] for x in s["observations"]
                                                    if comp not in (x.get("ligand_components") or [])})),
                    name_matches_component="yes" if (o.get("ligand_name") or "").upper()[:12] in names.get(comp, "") else "no",
                    hetero_groups_in_bundle=" ".join(f"{k}x{v}" for k, v in sorted(present.items()))))
    with open(HERE / "lipid_components.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["component", "name", "lipid_class", "basis", "structures_with_it_in_bundle",
                    "structures_counting_it_as_ligand", "example_pdbs"])
        for comp, e in sorted(comps.items(), key=lambda kv: -len(kv[1]["structures"])):
            w.writerow([comp, e["name"], e["role"], e["basis"], len(e["structures"]), len(e["as_ligand"]),
                        " ".join(sorted(e["structures"])[:8])])
    cols = list(ligand_rows[0]) if ligand_rows else []
    with open(HERE / "lipid_as_ligand.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(ligand_rows)
    n_struct = len({p for e in comps.values() for p in e["structures"]})
    print(f"lipid/detergent components: {len(comps)}; bundles carrying one: {n_struct}; "
          f"observations counting one as a ligand: {len(ligand_rows)}")


if __name__ == "__main__":
    main()
