"""Find ligands curated in one structure and left uncurated in another.

pipeline/phase5/build_payloads.py carries hand-curated site classes (CURATED_SITE_CLASSES) keyed by
ligand entity. A correction made for one deposition does not reach the next deposition of the same
chemical component, so the same ligand can sit in two classes across the atlas. This lists every
published observation whose component is curated elsewhere to a class it does not carry.

    python3 curation/site_class_review/check_curation_gaps.py
"""
import collections, glob, json, re, pathlib

src = pathlib.Path("pipeline/phase5/build_payloads.py").read_text()
block = src[src.index("CURATED_SITE_CLASSES={"):]
block = block[:block.index("}")]
curated = dict(re.findall(r'"([0-9A-Z]{4}:LE:np:[^":]+)(?::[a-z]+)?"\s*:\s*"([a-z_]+)"', block))
by_comp = collections.defaultdict(set)
for key, cls in curated.items():
    by_comp[key.split(":")[3]].add((key[:4], cls))
gaps = []
for f in sorted(glob.glob("site/data/web/families/*/structures.json")):
    for s in json.load(open(f))["structures"]:
        for o in s["observations"]:
            for comp in o.get("ligand_components") or []:
                if comp not in by_comp or s["pdb_id"] in {p for p, _ in by_comp[comp]}:
                    continue
                targets = sorted({c for _, c in by_comp[comp]})
                if o["binding_site_class"] not in targets:
                    gaps.append((comp, s["pdb_id"], s["receptor_entry_name"], o["binding_mode"],
                                 o["binding_site_class"], targets, sorted(p for p, _ in by_comp[comp])))
print(f"{len(curated)} curated entries over {len(by_comp)} components; {len(gaps)} gaps")
for g in sorted(gaps):
    print("  %-6s %s %-12s %-12s recorded %-24s curated elsewhere as %s in %s" % (
        g[0], g[1], g[2], g[3], g[4], ", ".join(g[5]), " ".join(g[6])))
