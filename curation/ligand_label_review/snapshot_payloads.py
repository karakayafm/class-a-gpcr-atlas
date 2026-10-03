#!/usr/bin/env python3
"""Snapshot the published payloads' labels, so a build can be diffed family by family.

    python3 curation/ligand_label_review/snapshot_payloads.py before.json
    # ... run the build ...
    python3 curation/ligand_label_review/snapshot_payloads.py after.json
    python3 curation/ligand_label_review/snapshot_payloads.py --diff before.json after.json

Records, per family: the number of structures, the binding-mode and ligand-role tallies, the apo and
ligand-status tallies, and the contact-map group counts (contact-eligible canonical-pocket observations
on representative units). Also records every observation's label, so the diff can name what moved.
"""
from __future__ import annotations
import json, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "site/data/web"
AGO = {"Agonist", "Agonist (partial)"}
BLK = {"Antagonist", "Inverse agonist"}


def contact_rows(structures):
    """What the contact map compares: canonical pocket, contact eligible, representative unit."""
    for s in structures:
        if not s.get("analysis_unit_representative"):
            continue
        for o in s.get("observations", []):
            if o.get("generic_contact_eligibility") != "yes":
                continue
            if o.get("production_status") != "production_contact_eligible":
                continue
            if o.get("binding_site_class") != "canonical_7tm_pocket":
                continue
            yield s, o


def groups(structures):
    out = {}
    for name, keys in (("agonist", AGO), ("blocker", BLK),
                       ("antagonist", {"Antagonist"}), ("inverse_agonist", {"Inverse agonist"})):
        units, pdbs = set(), set()
        for s, o in contact_rows(structures):
            if o.get("binding_mode") in keys:
                units.add(s["receptor_entry_name"]); pdbs.add(s["pdb_id"])
        out[name] = [len(units), len(pdbs)]
    ago = {s["receptor_entry_name"] for s, o in contact_rows(structures) if o.get("binding_mode") in AGO}
    blk = {s["receptor_entry_name"] for s, o in contact_rows(structures) if o.get("binding_mode") in BLK}
    inv = {s["receptor_entry_name"] for s, o in contact_rows(structures) if o.get("binding_mode") == "Inverse agonist"}
    out["paired_agonist_blocker"] = len(ago & blk)
    out["paired_agonist_inverse"] = len(ago & inv)
    return out


def snapshot() -> dict:
    manifest = json.loads((WEB / "global/manifest.json").read_text())
    fams, labels = {}, {}
    for fam in manifest["families"]:
        path = WEB / "families" / fam["slug"] / "structures.json"
        if not path.exists():
            continue
        structures = json.loads(path.read_text())["structures"]
        modes, roles = Counter(), Counter()
        for s in structures:
            for o in s.get("observations", []):
                modes[o.get("binding_mode")] += 1
                roles[o.get("ligand_role")] += 1
                if o.get("ligand_entity_id"):
                    labels[o["ligand_entity_id"]] = [o.get("binding_mode"), o.get("ligand_role"),
                                                     o.get("binding_site_class")]
        fams[fam["slug"]] = {
            "structures": len(structures),
            "observations": sum(modes.values()),
            "apo": Counter(s.get("apo_status") for s in structures),
            "ligand_status": Counter(s.get("ligand_status") for s in structures),
            "modes": modes, "roles": roles, "groups": groups(structures),
        }
    return {"families": fams, "labels": labels}


def fmt(c):
    return {k: v for k, v in sorted((c or {}).items(), key=lambda kv: str(kv[0]))}


def diff(a: dict, b: dict) -> None:
    fa, fb = a["families"], b["families"]
    changed = 0
    for slug in sorted(set(fa) | set(fb)):
        x, y = fa.get(slug), fb.get(slug)
        if x is None or y is None:
            print(f"{slug}: {'added' if x is None else 'removed'}"); changed += 1; continue
        lines = []
        for key in ("structures", "observations"):
            if x[key] != y[key]:
                lines.append(f"    {key}: {x[key]} -> {y[key]}")
        for key in ("apo", "ligand_status", "modes", "roles"):
            xa, ya = fmt(x[key]), fmt(y[key])
            for k in sorted(set(xa) | set(ya)):
                if xa.get(k, 0) != ya.get(k, 0):
                    lines.append(f"    {key}[{k}]: {xa.get(k, 0)} -> {ya.get(k, 0)}")
        for k, v in x["groups"].items():
            if v != y["groups"][k]:
                lines.append(f"    group {k}: {v} -> {y['groups'][k]}")
        if lines:
            changed += 1
            print(f"\n{slug}"); print("\n".join(lines))
    la, lb = a["labels"], b["labels"]
    moved = [(k, la.get(k), lb.get(k)) for k in sorted(set(la) | set(lb)) if la.get(k) != lb.get(k)]
    print(f"\n--- {len(moved)} observation(s) changed label/role/site ---")
    for k, v0, v1 in moved:
        print(f"  {k}\n      {v0}\n   -> {v1}")
    print(f"\n{changed} family/families changed.")


def main() -> int:
    if sys.argv[1:2] == ["--diff"]:
        diff(json.loads(Path(sys.argv[2]).read_text()), json.loads(Path(sys.argv[3]).read_text()))
        return 0
    out = Path(sys.argv[1])
    out.write_text(json.dumps(snapshot(), indent=1, default=lambda o: dict(o)) + "\n")
    print(f"snapshot -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
