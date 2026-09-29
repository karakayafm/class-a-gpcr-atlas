"""Screen canonical-pocket ligand observations for ones that do not sit in the orthosteric pocket.

The site class of a small-molecule observation is assigned from its entity form and the source's
binding-mode annotation; nothing in the pipeline checks it against where the ligand actually is.
This does, from the published payloads and the deposited coordinates, with two measures that do not
depend on each other:

  geometry  - the ligand's heavy-atom centroid against the orthosteric centre of its own structure
              (mean CA of the conserved pocket positions it resolves), split along the bundle axis
              (extracellular +, intracellular -) and across it (radial: distance from the axis, set
              against how far that structure's helices sit from it).
  contacts  - the share of the ligand's contacted positions that belong to its family's orthosteric
              core: positions contacted by at least 40% of the family's canonical-pocket receptors.

Standard library only, like the pipeline. Writes site_class_screen.csv beside this file.
Run from the repository root:  python3 curation/site_class_review/screen_site_class.py
"""
import csv, json, math, pathlib, statistics, collections, re

ROOT = pathlib.Path("site/data/web")
OUT = pathlib.Path(__file__).resolve().parent / "site_class_screen.csv"
POCKET = ["3x32", "3x33", "3x36", "5x42", "5x43", "5x461", "6x48", "6x51", "6x52", "6x55",
          "7x39", "7x42", "7x43", "2x60", "45x52"]
INTRA = ["3x50", "6x30", "6x33", "7x53", "2x39", "5x61", "8x49"]
HELIX_LEVEL = [f"{h}x{i}" for h in range(1, 8) for i in range(30, 61)]


def cif_atoms(pdb):
    hdr, out = [], []
    for line in (ROOT / "structures" / pdb / "viewer.cif").read_text().splitlines():
        if line.startswith("_atom_site."):
            hdr.append(line.strip().split(".")[1]); continue
        if not hdr or not (line.startswith("ATOM") or line.startswith("HETATM")):
            continue
        f = line.split()
        if len(f) < len(hdr): continue
        g = dict(zip(hdr, f))
        try: xyz = (float(g["Cartn_x"]), float(g["Cartn_y"]), float(g["Cartn_z"]))
        except (KeyError, ValueError): continue
        out.append((g["auth_asym_id"], g["auth_seq_id"], g["auth_comp_id"], g["auth_atom_id"],
                    g.get("type_symbol", "").upper(), xyz))
    return out


def mean(pts):
    return tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))


def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))


def load_family(slug):
    S = {s["pdb_id"]: s for s in json.load(open(ROOT / "families" / slug / "structures.json"))["structures"]}
    P = json.load(open(ROOT / "families" / slug / "pocket_detail.json"))["structures"]
    return S, P


def family_core(S, P):
    """Positions contacted by >= 40% of the family's receptors with a canonical-pocket ligand."""
    by_rec = collections.defaultdict(set)
    for p in P:
        rec = S[p["pdb_id"]]["receptor_entry_name"]
        for seg in p["segments"]:
            for r in seg["residues"]:
                if r["binding_site_class"] == "canonical_7tm_pocket" and r["generic_number"]:
                    by_rec[rec].add(r["generic_number"])
    n = len(by_rec)
    c = collections.Counter(g for s in by_rec.values() for g in s)
    return {g for g, k in c.items() if n and k / n >= 0.4}, n


def main():
    rows = []
    for fam_dir in sorted((ROOT / "families").iterdir()):
        slug = fam_dir.name
        S, P = load_family(slug)
        core, n_rec = family_core(S, P)
        fam_name = json.load(open(fam_dir / "summary.json"))["family_name"]
        for p in P:
            s = S[p["pdb_id"]]
            comps = collections.defaultdict(dict)
            for seg in p["segments"]:
                for r in seg["residues"]:
                    if r["binding_site_class"] == "canonical_7tm_pocket" and r["generic_number"]:
                        comps[r["ligand_residue_name"]][r["generic_number"]] = (r["chain"], str(r["auth_seq_id"]))
            if not comps: continue
            rr = json.load(open(ROOT / "overlay" / "structures" / p["pdb_id"] / "receptor_residues.json"))["residues"]
            # The pocket centre is taken on the chain the contacts are on. Where the asymmetric unit
            # holds two receptor copies, the residue table names one of them and the contacts may
            # be on the other; the copies share their numbering, so the table's residue numbers are
            # read on the contacts' chain.
            contact_chain = collections.Counter(c for cp in comps.values() for c, _ in cp.values()).most_common(1)[0][0]
            own = [r for r in rr if r["c"] == contact_chain]
            gen = {r["p"]: (contact_chain, r["n"]) for r in (own or rr)}
            atoms = cif_atoms(p["pdb_id"])
            ca = {(a[0], a[1]): a[5] for a in atoms if a[3] == "CA"}
            pocket_ca = [ca[gen[g]] for g in POCKET if g in gen and gen[g] in ca]
            intra_ca = [ca[gen[g]] for g in INTRA if g in gen and gen[g] in ca]
            helix_ca = [ca[gen[g]] for g in HELIX_LEVEL if g in gen and gen[g] in ca]
            for comp, pos in comps.items():
                obs = [o for o in s["observations"] if comp in (o.get("ligand_components") or [])]
                keys = set(pos.values())
                res_atoms = [a[5] for a in atoms if (a[0], a[1]) in keys and a[4] != "H"]
                # A component can occur more than once in the file - a second copy in the
                # asymmetric unit, or one at a crystal contact. Each copy is taken whole, and the
                # one with most atoms near the contacted residues is the ligand of this observation;
                # averaging over copies put the centroid in the space between them.
                copies = collections.defaultdict(list)
                for a in atoms:
                    if a[2] == comp and a[4] != "H":
                        copies[(a[0], a[1])].append(a[5])
                def near(xyz): return any(norm(sub(xyz, r)) <= 4.5 for r in res_atoms)
                scored = [(sum(near(x) for x in pts), pts) for pts in copies.values()]
                scored = [x for x in scored if x[0]]
                lig = max(scored, key=lambda x: x[0])[1] if scored else []
                row = dict(family=fam_name, pdb=p["pdb_id"], receptor=s["receptor_entry_name"],
                           component=comp, ligand=obs[0]["ligand_name"] if obs else "",
                           binding_mode=";".join(sorted({o["binding_mode"] or "" for o in obs})),
                           ligand_role=";".join(sorted({o["ligand_role"] or "" for o in obs})),
                           method=s["experimental_method"], n_positions=len(pos),
                           core_overlap=round(len(set(pos) & core) / len(pos), 2) if pos else "",
                           family_core_size=len(core),
                           contacted_segments=" ".join(sorted({re.sub(r"x.*", "", g) for g in pos},
                                                              key=lambda x: (len(x), x))),
                           positions=" ".join(sorted(pos, key=lambda g: (int(g.split("x")[0][0]), g))))
                if len(pocket_ca) >= 4 and len(intra_ca) >= 3 and lig:
                    O, I, L = mean(pocket_ca), mean(intra_ca), mean(lig)
                    axis = sub(O, I); axis = tuple(x / norm(axis) for x in axis)
                    v = sub(L, O); ax = dot(v, axis)
                    radial = norm(sub(v, tuple(ax * x for x in axis)))
                    # how far this structure's helices sit from the axis, at pocket level
                    rads = [norm(sub(sub(h, O), tuple(dot(sub(h, O), axis) * x for x in axis)))
                            for h in helix_ca if abs(dot(sub(h, O), axis)) < 8]
                    row.update(distance_to_pocket=round(norm(v), 1), axial=round(ax, 1),
                               radial=round(radial, 1),
                               bundle_radius=round(statistics.median(rads), 1) if rads else "")
                rows.append(row)
    cols = ["family", "pdb", "receptor", "component", "ligand", "binding_mode", "ligand_role", "method",
            "distance_to_pocket", "axial", "radial", "bundle_radius", "core_overlap",
            "family_core_size", "n_positions", "contacted_segments", "positions"]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    print("observations screened:", len(rows), "->", OUT)


if __name__ == "__main__":
    main()
