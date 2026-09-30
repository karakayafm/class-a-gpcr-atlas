#!/usr/bin/env python3
"""Lipid overlay: the membrane lipids and detergents the viewer bundles left out.

A viewer bundle carries the receptor, its approved ligands and - only where the whole of it fits a
450 kB budget - the auxiliary and environment chains. Lipids travelled with those chains, so a
cryo-EM complex whose G protein broke the budget lost its cholesterol too: 289 structures whose
deposited models carry lipids or detergents show none.

build_bundles.py now puts receptor-contacting lipids into every bundle, which takes effect at the
next full build. Until then, this writes them beside the frozen bundles, the way
overlay/structures/<PDB>/receptor_residues.json sits beside them:

    site/data/web/overlay/structures/<PDB>/lipids.cif   the lipid residues, in the deposited frame
    site/data/web/overlay/lipids_index.json             which structures have one, from what source

The rule is the one build_bundles.py applies: a component the component reference classes as
membrane_lipid or detergent, any heavy atom within 6 A of a receptor-chain heavy atom, and never a
component the structure counts as its ligand. Coordinates are copied from the RCSB PDB entry
unchanged (CC0); nothing is modelled.

    python3 pipeline/overlays/build_lipid_overlay.py [--pdb 7CKZ 8FYX ...] [--limit N]
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from phase3.mmcif import read                                  # noqa: E402

WEB = ROOT / "site/data/web"
OVERLAY = WEB / "overlay"
CACHE = ROOT / "data/cache/coordinates"     # the cache build_bundles.py reads
SHELL = 6.0
REF = json.loads((ROOT / "config/component_reference.json").read_text(encoding="utf-8"))
LIPIDS = {k for k, v in REF["curated_components"].items() if v[1] in ("membrane_lipid", "detergent")}
FIELDS = ["group_PDB", "id", "type_symbol", "label_atom_id", "label_alt_id", "label_comp_id",
          "label_asym_id", "label_entity_id", "label_seq_id", "pdbx_PDB_ins_code", "Cartn_x",
          "Cartn_y", "Cartn_z", "occupancy", "B_iso_or_equiv", "auth_seq_id", "auth_comp_id",
          "auth_asym_id", "auth_atom_id", "pdbx_PDB_model_num"]


def deposited_lipids(pdb_ids):
    """Which of these entries carry a lipid or detergent component, from RCSB's entry records."""
    q = ("query($ids:[String!]!){entries(entry_ids:$ids){rcsb_id nonpolymer_entities{"
         "rcsb_nonpolymer_entity_container_identifiers{nonpolymer_comp_id}}}}")
    found = set()
    for k in range(0, len(pdb_ids), 150):
        body = json.dumps({"query": q, "variables": {"ids": pdb_ids[k:k + 150]}}).encode()
        req = urllib.request.Request("https://data.rcsb.org/graphql", data=body,
                                     headers={"Content-Type": "application/json"})
        data = json.load(urllib.request.urlopen(req, timeout=120))["data"]["entries"] or []
        for e in data:
            comps = {n["rcsb_nonpolymer_entity_container_identifiers"]["nonpolymer_comp_id"]
                     for n in e.get("nonpolymer_entities") or []}
            if comps & LIPIDS:
                found.add(e["rcsb_id"])
        time.sleep(0.3)
    return found


def fetch(pdb):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{pdb}.cif.gz"
    if not path.exists():
        with urllib.request.urlopen(f"https://files.rcsb.org/download/{pdb}.cif.gz", timeout=180) as r:
            path.write_bytes(r.read())
        time.sleep(0.2)
    return path


def cif_value(v):
    v = "" if v is None else str(v)
    if v == "":
        return "?"
    if " " in v or v.startswith(("_", "#", "'", '"', ";")):
        return '"' + v + '"' if "'" in v else "'" + v + "'"
    return v


def bundle_components(pdb):
    text = (WEB / "structures" / pdb / "viewer.cif").read_text()
    return {line.split()[5] for line in text.splitlines() if line.startswith("HETATM")}


def build(pdb, meta):
    path = fetch(pdb)
    cats = read(path, {"_atom_site", "_entity", "_chem_comp"})
    rows = cats["_atom_site"]
    model = min(int(r.get("pdbx_PDB_model_num", "1") or 1) for r in rows)
    rows = [r for r in rows if int(r.get("pdbx_PDB_model_num", "1") or 1) == model and
            (r.get("type_symbol") or "").upper() not in ("H", "D")]
    rec_chains = set(meta.get("receptor_chains") or [])
    ligand = {(str(c), str(s)) for o in meta.get("observations") or []
              for c, s in ((o.get("ligand_selection") or {}).get("residues") or [])}
    auth = lambda r: (r.get("auth_asym_id") or r.get("label_asym_id"), r.get("auth_seq_id"))
    rec = [(float(r["Cartn_x"]), float(r["Cartn_y"]), float(r["Cartn_z"])) for r in rows
           if r.get("group_PDB") == "ATOM" and auth(r)[0] in rec_chains]
    keep = set()
    for r in rows:
        key = auth(r)
        if (r.get("group_PDB") != "HETATM" or r.get("label_comp_id") not in LIPIDS or key in keep
                or key in ligand):
            continue
        x, y, z = float(r["Cartn_x"]), float(r["Cartn_y"]), float(r["Cartn_z"])
        if any((x - a) ** 2 + (y - b) ** 2 + (z - c) ** 2 <= SHELL ** 2 for a, b, c in rec):
            keep.add(key)
    out = [r for r in rows if r.get("group_PDB") == "HETATM" and auth(r) in keep]
    if not out:
        return None
    # NGL's mmCIF reader needs chem_comp (and reads entity); both are copied for the components kept.
    ent_ids = {r.get("label_entity_id") for r in out}
    comp_ids = {r.get("label_comp_id") for r in out}
    lines = [f"data_{pdb}_lipids", "#",
             f"# Membrane lipids and detergents within {SHELL} A of the receptor in {pdb},",
             "# copied unchanged from the RCSB PDB entry (CC0). Atlas lipid overlay.", "#",
             f"_entry.id {pdb}", "#", "loop_", "_entity.id", "_entity.type", "_entity.pdbx_description"]
    lines += [" ".join(cif_value(e.get(k)) for k in ("id", "type", "pdbx_description"))
              for e in cats["_entity"] if e.get("id") in ent_ids]
    lines += ["#", "loop_", "_chem_comp.id", "_chem_comp.type", "_chem_comp.name"]
    lines += [" ".join(cif_value(c.get(k)) for k in ("id", "type", "name"))
              for c in cats["_chem_comp"] if c.get("id") in comp_ids]
    lines += ["#", "loop_"] + [f"_atom_site.{f}" for f in FIELDS]
    for r in out:
        lines.append(" ".join(cif_value(r.get(f, "?")) for f in FIELDS))
    lines.append("#")
    target = OVERLAY / "structures" / pdb
    target.mkdir(parents=True, exist_ok=True)
    (target / "lipids.cif").write_text("\n".join(lines) + "\n", encoding="utf-8")
    comps = {}
    for key in keep:
        comp = next(r["label_comp_id"] for r in out if auth(r) == key)
        comps[comp] = comps.get(comp, 0) + 1
    return {"residues": len(keep), "atoms": len(out), "components": dict(sorted(comps.items())),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdb", nargs="*")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    metas = {p.parent.name: json.loads(p.read_text()) for p in (WEB / "structures").glob("*/viewer_meta.json")}
    # Only bundles that show no lipid now; the rest already carry theirs.
    wanted = sorted(p for p in (args.pdb or metas) if p in metas and not (bundle_components(p) & LIPIDS))
    wanted = sorted(deposited_lipids(wanted))
    if args.limit:
        wanted = wanted[:args.limit]
    index_path = OVERLAY / "lipids_index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"structures": {}}
    for i, pdb in enumerate(wanted, 1):
        try:
            entry = build(pdb, metas[pdb])
        except Exception as e:                      # one bad entry must not stop the rest
            print(f"  {pdb}: failed ({type(e).__name__}: {e})"); continue
        if entry:
            index["structures"][pdb] = entry
        print(f"[{i}/{len(wanted)}] {pdb}: ", flush=True, end="")
        print("" + (f"{entry['residues']} residues" if entry else "none near the receptor"))
    index.update({
        "schema": "lipid_overlay_index", "schema_version": "1.0.0",
        "generated": datetime.date.today().isoformat(),
        "source": "RCSB PDB mmCIF (https://files.rcsb.org/download/<PDB>.cif.gz), CC0",
        "rule": f"component reference membrane_lipid or detergent; heavy atom within {SHELL} A of a "
                "receptor-chain heavy atom; not a component the structure counts as its ligand",
        "components": sorted(LIPIDS),
        "note": "Interim: build_bundles.py includes these lipids in the bundles from the next full build."})
    index["structures"] = dict(sorted(index["structures"].items()))
    index_path.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    print(f"lipid overlays: {len(index['structures'])} structures -> {index_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
