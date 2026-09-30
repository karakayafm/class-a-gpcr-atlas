#!/usr/bin/env python3
"""Receptor copies: which structures deposit the receptor as a dimer or larger oligomer.

The viewer draws one receptor chain. Where the deposited biological assembly holds more than one
copy of the receptor, the structure page says so and links to the assembly at RCSB, rather than
the atlas drawing the other copies itself.

    site/data/web/overlay/receptor_copies.json

The rule: count the receptor's chains (the polymer entities of the bundle's receptor instances,
plus any other entity carrying the same receptor UniProt accession, e.g. a second construct) that
the PDB's first biological assembly contains. Two or more is flagged. Copies that are only in the
asymmetric unit - crystal packing - are recorded but not flagged. A first assembly is itself often
an author's or software's call for a crystal, so the note says "deposited as", not "is a dimer".

The receptor's UniProt accession comes from its entry name via UniProt, so accessions of fusion
partners, G proteins and tethered ligands carried on the receptor entity never count as receptors.

    python3 pipeline/overlays/build_receptor_copies.py
"""
from __future__ import annotations
import datetime, json, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "site/data/web"
OUT = WEB / "overlay/receptor_copies.json"
Q = ("query($ids:[String!]!){entries(entry_ids:$ids){rcsb_id "
     "assemblies{pdbx_struct_assembly{oligomeric_details} pdbx_struct_assembly_gen{asym_id_list}} "
     "polymer_entities{rcsb_polymer_entity_container_identifiers{entity_id asym_ids auth_asym_ids} "
     "uniprots{rcsb_id}}}}")


def post(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request("https://data.rcsb.org/graphql", data=body,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=180))["data"]


def accessions(entry_names):
    """UniProt entry name -> accession. An unreviewed entry's name is its accession."""
    out = {}
    names = sorted(entry_names)
    for k in range(0, len(names), 40):
        q = " OR ".join(f"id:{n.upper()}" for n in names[k:k + 40])
        url = ("https://rest.uniprot.org/uniprotkb/search?fields=accession,id&format=tsv&size=500&query="
               + urllib.parse.quote(q))
        for line in urllib.request.urlopen(url, timeout=120).read().decode().splitlines()[1:]:
            acc, name = line.split("\t")
            out[name.lower()] = acc
        time.sleep(0.3)
    for n in names:
        out.setdefault(n, n.split("_")[0].upper())
    return out


def main():
    metas = {p.parent.name: json.loads(p.read_text()) for p in (WEB / "structures").glob("*/viewer_meta.json")}
    acc = accessions({m["receptor_entry_name"] for m in metas.values()})
    ids = sorted(metas)
    entries = {}
    for k in range(0, len(ids), 100):
        for e in post(Q, {"ids": ids[k:k + 100]})["entries"] or []:
            if e:
                entries[e["rcsb_id"]] = e
        time.sleep(0.3)
    flagged, packing = {}, {}
    for pdb, m in metas.items():
        e = entries.get(pdb)
        if not e:
            continue
        eids = {i["polymer_entity_id"] for i in m["receptor_instances"]}
        receptor_acc = acc[m["receptor_entry_name"]]
        asyms, auth = [], {}
        for pe in e["polymer_entities"]:
            ci = pe["rcsb_polymer_entity_container_identifiers"]
            accs = {u["rcsb_id"] for u in pe.get("uniprots") or []}
            if ci["entity_id"] in eids or receptor_acc in accs:
                asyms += ci["asym_ids"]
                auth.update(zip(ci["asym_ids"], ci.get("auth_asym_ids") or ci["asym_ids"]))
        a1 = (e.get("assemblies") or [None])[0]
        in_a1 = set(sum((g["asym_id_list"] for g in a1["pdbx_struct_assembly_gen"]), [])) if a1 else set()
        copies_a1 = sorted(auth[a] for a in asyms if a in in_a1)
        record = {"copies_asymmetric_unit": len(asyms), "copies_assembly_1": len(copies_a1),
                  "chains_assembly_1": copies_a1,
                  "assembly_1_oligomeric_state": (a1 or {}).get("pdbx_struct_assembly", {}).get("oligomeric_details"),
                  "method": m.get("experimental_method")}
        if len(copies_a1) > 1:
            flagged[pdb] = record
        elif len(asyms) > 1:
            packing[pdb] = record
    OUT.write_text(json.dumps({
        "schema": "receptor_copies_overlay", "schema_version": "1.0.0",
        "generated": datetime.date.today().isoformat(),
        "source": "RCSB PDB entry and assembly records (data.rcsb.org GraphQL), UniProt entry names, CC0/CC BY",
        "rule": "chains of the receptor (bundle receptor entities, or any entity carrying the receptor's UniProt "
                "accession) contained in the PDB's first biological assembly; two or more is flagged",
        "note": "The viewer draws one receptor chain. A first assembly of a crystal structure is the "
                "depositor's or software's assignment and is not by itself evidence of a biological dimer.",
        "structures": dict(sorted(flagged.items())),
        "asymmetric_unit_only": dict(sorted(packing.items()))}, indent=1) + "\n", encoding="utf-8")
    print(f"flagged {len(flagged)} structures (assembly 1); {len(packing)} with copies only in the "
          f"asymmetric unit; {len(set(metas) - set(entries))} not at RCSB -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
