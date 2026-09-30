#!/usr/bin/env python3
"""Transducer overlay: the G protein and arrestin chains the viewer bundles left out.

A bundle carries the receptor and its ligands; transducer chains travelled with the auxiliary
content, which was dropped wherever it broke the 450 kB budget - that is, from almost every cryo-EM
complex, which is where the transducers are. This writes them as a separate file per structure,
loaded only when the viewer's Transducer layer is switched on:

    site/data/web/overlay/structures/<PDB>/transducer.cif.gz
    site/data/web/overlay/transducer_index.json   chains, subunits, source and rule

Which chains: the polymer entities the atlas's own polymer role reference calls
transducer_component - by curated UniProt accession first, then by description pattern - so
Galpha, Gbeta, Ggamma, mini-G constructs and arrestins. Nanobodies, scFv16, Fab fragments, fusion
partners (BRIL, T4 lysozyme) and other receptor copies are not transducers and are not written.

What is kept: every residue's backbone (N, CA, C, O), which is what a cartoon is drawn from, and
the whole residue where any of its heavy atoms is within 8 A of a receptor heavy atom, so the
receptor-transducer interface can be read atom by atom and measured. Coordinates are copied
unchanged from the RCSB PDB entry (CC0) in the deposited frame the bundle uses.

    python3 pipeline/overlays/build_transducer_overlay.py [--pdb 7CKZ ...] [--limit N]
"""
from __future__ import annotations
import argparse, datetime, gzip, hashlib, json, re, sys, time, urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from phase3.mmcif import read                                  # noqa: E402

WEB = ROOT / "site/data/web"
OVERLAY = WEB / "overlay"
CACHE = ROOT / "data/cache/coordinates"                        # the cache build_bundles.py reads
INTERFACE = 8.0
BACKBONE = {"N", "CA", "C", "O"}
POLY = json.loads((ROOT / "config/polymer_role_reference.json").read_text(encoding="utf-8"))
TRANSDUCER_ACC = {a for a in POLY["uniprot_accessions"]["transducer_component"] if "_" not in a}
PATTERNS = {rule["role"]: [] for rule in POLY["description_patterns"]}
for rule in POLY["description_patterns"]:
    PATTERNS[rule["role"]] += rule["patterns"]
FIELDS = ["group_PDB", "id", "type_symbol", "label_atom_id", "label_alt_id", "label_comp_id",
          "label_asym_id", "label_entity_id", "label_seq_id", "pdbx_PDB_ins_code", "Cartn_x",
          "Cartn_y", "Cartn_z", "occupancy", "B_iso_or_equiv", "auth_seq_id", "auth_comp_id",
          "auth_asym_id", "auth_atom_id", "pdbx_PDB_model_num"]


def is_transducer(description, accessions):
    """The polymer role reference's rule: accession first, then description. Never an antibody,
    never a chain that carries a fusion partner or a receptor (6E67's second receptor copy is a
    beta2AR-T4L-Galpha(s) fusion, and would otherwise read as a G protein)."""
    d = (description or "").lower()
    if any(p in d for p in PATTERNS.get("antibody_or_nanobody", []) + PATTERNS.get("fusion_partner", [])):
        return False
    if "receptor" in d:
        return False
    if set(accessions) & TRANSDUCER_ACC:
        return True
    return any(p in d for p in PATTERNS.get("transducer_component", []))


def subunit(description):
    d = (description or "").lower()
    if "arrestin" in d:
        return "arrestin"
    gamma = re.search(r"\bgamma\b|subunit gamma|gamma-\d|\bg?gama\b", d)
    if gamma and re.search(r"alpha|\bg[st]-|egt", d):
        return "G alpha"                      # a single-chain Ggamma-Galpha construct: mostly Galpha
    if gamma:
        return "G gamma"
    if re.search(r"\bbeta\b|subunit beta|beta-\d", d):
        return "G beta"
    return "G alpha"


def transducer_entities(pdb_ids):
    """pdb -> [(entity_id, description, auth chains)] for transducer entities, from RCSB records."""
    q = ("query($ids:[String!]!){entries(entry_ids:$ids){rcsb_id polymer_entities{"
         "rcsb_polymer_entity{pdbx_description} rcsb_polymer_entity_container_identifiers{entity_id "
         "auth_asym_ids} uniprots{rcsb_id}}}}")
    out = {}
    for k in range(0, len(pdb_ids), 100):
        body = json.dumps({"query": q, "variables": {"ids": pdb_ids[k:k + 100]}}).encode()
        req = urllib.request.Request("https://data.rcsb.org/graphql", data=body,
                                     headers={"Content-Type": "application/json"})
        for e in json.load(urllib.request.urlopen(req, timeout=180))["data"]["entries"] or []:
            ents = []
            for p in e.get("polymer_entities") or []:
                desc = (p.get("rcsb_polymer_entity") or {}).get("pdbx_description") or ""
                ids = p["rcsb_polymer_entity_container_identifiers"]
                accs = [u["rcsb_id"] for u in p.get("uniprots") or []]
                if is_transducer(desc, accs):
                    ents.append((ids["entity_id"], desc, ids.get("auth_asym_ids") or []))
            if ents:
                out[e["rcsb_id"]] = ents
        time.sleep(0.3)
    return out


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


class Grid:
    """Points hashed into cubes of the query radius, so a neighbour test looks at 27 cells."""
    def __init__(self, pts, r):
        self.r, self.cells = r, defaultdict(list)
        for p in pts:
            self.cells[(int(p[0] // r), int(p[1] // r), int(p[2] // r))].append(p)

    def near(self, p):
        cx, cy, cz, r2 = int(p[0] // self.r), int(p[1] // self.r), int(p[2] // self.r), self.r ** 2
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in self.cells.get((cx + dx, cy + dy, cz + dz), ()):
                        if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2 <= r2:
                            return True
        return False


def build(pdb, meta, ents):
    path = fetch(pdb)
    cats = read(path, {"_atom_site", "_entity", "_chem_comp"})
    rows = cats["_atom_site"]
    model = min(int(r.get("pdbx_PDB_model_num", "1") or 1) for r in rows)
    rows = [r for r in rows if int(r.get("pdbx_PDB_model_num", "1") or 1) == model and
            (r.get("type_symbol") or "").upper() not in ("H", "D")]
    rec_chains = set(meta.get("receptor_chains") or [])
    chain_of = {}
    for eid, desc, chains in ents:
        for c in chains:
            if c not in rec_chains:
                chain_of[c] = (eid, desc, subunit(desc))
    chain = lambda r: r.get("auth_asym_id") or r.get("label_asym_id")
    grid = Grid([(float(r["Cartn_x"]), float(r["Cartn_y"]), float(r["Cartn_z"])) for r in rows
                 if r.get("group_PDB") == "ATOM" and chain(r) in rec_chains], INTERFACE)
    tx = [r for r in rows if r.get("group_PDB") == "ATOM" and chain(r) in chain_of]
    if not tx or not grid.cells:
        return None
    interface = set()
    for r in tx:
        key = (chain(r), r.get("auth_seq_id"), r.get("pdbx_PDB_ins_code"))
        if key not in interface and grid.near((float(r["Cartn_x"]), float(r["Cartn_y"]), float(r["Cartn_z"]))):
            interface.add(key)
    out = [r for r in tx if r.get("label_atom_id") in BACKBONE or
           (chain(r), r.get("auth_seq_id"), r.get("pdbx_PDB_ins_code")) in interface]
    ent_ids = {r.get("label_entity_id") for r in out}
    comp_ids = {r.get("label_comp_id") for r in out}
    lines = [f"data_{pdb}_transducer", "#",
             f"# G protein and arrestin chains of {pdb}: backbone throughout, whole residues within",
             f"# {INTERFACE} A of the receptor. Copied unchanged from the RCSB PDB entry (CC0).", "#",
             f"_entry.id {pdb}", "#", "loop_", "_entity.id", "_entity.type", "_entity.pdbx_description"]
    lines += [" ".join(cif_value(e.get(k)) for k in ("id", "type", "pdbx_description"))
              for e in cats["_entity"] if e.get("id") in ent_ids]
    lines += ["#", "loop_", "_chem_comp.id", "_chem_comp.type", "_chem_comp.name"]
    lines += [" ".join(cif_value(c.get(k)) for k in ("id", "type", "name"))
              for c in cats["_chem_comp"] if c.get("id") in comp_ids]
    lines += ["#", "loop_"] + [f"_atom_site.{f}" for f in FIELDS]
    lines += [" ".join(cif_value(r.get(f, "?")) for f in FIELDS) for r in out]
    lines.append("#")
    target = OVERLAY / "structures" / pdb
    target.mkdir(parents=True, exist_ok=True)
    data = gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), mtime=0)
    (target / "transducer.cif.gz").write_bytes(data)
    present = {chain(r) for r in out}
    return {"chains": {c: {"subunit": chain_of[c][2], "description": chain_of[c][1]}
                       for c in sorted(present)},
            "interface_residues": len(interface), "atoms": len(out), "bytes": len(data),
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdb", nargs="*")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    metas = {p.parent.name: json.loads(p.read_text()) for p in (WEB / "structures").glob("*/viewer_meta.json")}
    ids = sorted(p for p in (args.pdb or metas) if p in metas)
    ents = transducer_entities(ids)
    wanted = sorted(ents)[:args.limit] if args.limit else sorted(ents)
    print(f"{len(wanted)} of {len(ids)} structures carry a transducer chain", flush=True)
    index_path = OVERLAY / "transducer_index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"structures": {}}
    if not args.pdb and not args.limit:            # a full run: structures no longer selected go
        for pdb in set(index["structures"]) - set(wanted):
            index["structures"].pop(pdb)
            (OVERLAY / "structures" / pdb / "transducer.cif.gz").unlink(missing_ok=True)
    for i, pdb in enumerate(wanted, 1):
        try:
            entry = build(pdb, metas[pdb], ents[pdb])
        except Exception as e:                      # one bad entry must not stop the rest
            print(f"  {pdb}: failed ({type(e).__name__}: {e})", flush=True); continue
        if entry:
            index["structures"][pdb] = entry
        else:                                       # a rule change can leave nothing to show
            index["structures"].pop(pdb, None)
            (OVERLAY / "structures" / pdb / "transducer.cif.gz").unlink(missing_ok=True)
        print(f"[{i}/{len(wanted)}] {pdb}: " + (", ".join(f"{c} {v['subunit']}" for c, v in entry["chains"].items())
                                                if entry else "no transducer atoms"), flush=True)
    index.update({
        "schema": "transducer_overlay_index", "schema_version": "1.0.0",
        "generated": datetime.date.today().isoformat(),
        "source": "RCSB PDB mmCIF (https://files.rcsb.org/download/<PDB>.cif.gz) and entry records, CC0",
        "rule": "polymer entities classed transducer_component by config/polymer_role_reference.json "
                "(curated UniProt accession, then description pattern; antibodies and nanobodies excluded); "
                f"backbone N/CA/C/O throughout, whole residues within {INTERFACE} A of a receptor heavy atom",
        "note": "Loaded on demand by the viewer's Transducer layer; not part of the viewer bundle."})
    index["structures"] = dict(sorted(index["structures"].items()))
    index_path.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    total = sum(v["bytes"] for v in index["structures"].values())
    print(f"transducer overlays: {len(index['structures'])} structures, {total / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
