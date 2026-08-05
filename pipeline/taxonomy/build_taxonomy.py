#!/usr/bin/env python3
"""Phase 1 — Class A taxonomy from the official GPCRdb API.

Hierarchy is taken exactly as GPCRdb models it; family names are never rewritten and no
family is promoted or demoted. Identifiers are separated into source identifiers (GPCRdb
slugs and entry names) and project-generated stable slugs.

    python3 pipeline/taxonomy/build_taxonomy.py [--refresh]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))

from common.canonical import write_json, PARSER_VERSION           # noqa: E402
from common.http import Fetcher, utc_now                          # noqa: E402
import json                                                        # noqa: E402

CFG = json.loads((ROOT / "config/source_endpoints.json").read_text(encoding="utf-8"))
G = CFG["gpcrdb"]


def stable_slug(source_slug: str) -> str:
    """Project-generated identifier. Derived from the source slug, marked as project-made."""
    return "ca-" + source_slug.replace("_", "-")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="ignore cache and re-fetch")
    args = ap.parse_args()

    f = Fetcher(ROOT / "data/cache/gpcrdb", "GPCRdb",
                timeout=G["rate"]["timeout_seconds"], retries=G["rate"]["retries"],
                delay=G["rate"]["delay_seconds"], refresh=args.refresh)

    class_slug = G["class_a_slug"]
    base = G["base"]

    majors = f.get_json(base + G["endpoints"]["protein_family_children"].format(slug=class_slug),
                        f"children_{class_slug}")
    if majors is None:
        print("FATAL: could not retrieve Class A children", file=sys.stderr)
        return 2

    class_name = majors[0]["parent"]["name"] if majors and majors[0].get("parent") else "Class A (Rhodopsin)"

    nodes, receptors = [], []
    nodes.append({
        "level": "class", "source_id": class_slug, "source_id_type": "gpcrdb_family_slug",
        "project_slug": stable_slug(class_slug), "name": class_name,
        "parent_source_id": None, "hierarchy_path": [class_slug],
    })

    for mj in majors:
        m_slug = mj["slug"]
        nodes.append({
            "level": "major_family", "source_id": m_slug, "source_id_type": "gpcrdb_family_slug",
            "project_slug": stable_slug(m_slug), "name": mj["name"],
            "parent_source_id": class_slug, "hierarchy_path": [class_slug, m_slug],
        })
        subs = f.get_json(base + G["endpoints"]["protein_family_children"].format(slug=m_slug),
                          f"children_{m_slug}") or []
        for sb in subs:
            s_slug = sb["slug"]
            nodes.append({
                "level": "receptor_family", "source_id": s_slug,
                "source_id_type": "gpcrdb_family_slug", "project_slug": stable_slug(s_slug),
                "name": sb["name"], "parent_source_id": m_slug,
                "hierarchy_path": [class_slug, m_slug, s_slug],
            })

        prots = f.get_json(base + G["endpoints"]["proteins_in_family"].format(slug=m_slug),
                           f"proteins_{m_slug}") or []
        for p in prots:
            fam = str(p.get("family") or "")
            parts = fam.split("_")
            rf = "_".join(parts[:3]) if len(parts) >= 3 else None
            receptors.append({
                "level": "receptor",
                "source_id": p.get("entry_name"), "source_id_type": "gpcrdb_protein_entry_name",
                "project_slug": stable_slug(str(p.get("entry_name"))),
                "receptor_entry_name": p.get("entry_name"),
                "receptor_display_name": p.get("name"),
                "gene_symbol": (p.get("genes") or [None])[0] if isinstance(p.get("genes"), list) else None,
                "accession": p.get("accession"),
                "species": p.get("species"),
                "source_family_path": fam,
                "receptor_family_source_id": rf,
                "major_family_source_id": m_slug,
                "major_family_name": mj["name"],
                "class_source_id": class_slug,
                "provenance_status": "from_source" if p.get("entry_name") else "unresolved",
            })

    taxonomy = {
        "schema": "taxonomy.schema.json", "schema_version": "1.0.0",
        "parser_version": PARSER_VERSION,
        "source": {"provider": "GPCRdb", "base_url": base,
                   "class_slug": class_slug, "class_name": class_name,
                   "release_or_version": None,
                   "release_note": "The GPCRdb service endpoints used here expose no numeric release; the retrieval timestamp is the version anchor.",
                   "retrieved_at": utc_now(),
                   "license": G["terms"], "license_page": G["license_page"]},
        "counts": {
            "major_families": sum(1 for n in nodes if n["level"] == "major_family"),
            "receptor_families": sum(1 for n in nodes if n["level"] == "receptor_family"),
            "receptors": len(receptors),
        },
        "nodes": nodes,
        "receptors": receptors,
    }

    out = write_json(ROOT / "data/normalized/class_a_taxonomy.json", taxonomy)

    majors = [n for n in nodes if n["level"] == "major_family"]
    # This manifest is the authoritative answer to "how many Class A families are there?".
    # The number is read off the source tree, never assumed; anything downstream that
    # disagrees with this file is wrong.
    fam_manifest = {
        "schema": "family_manifest.schema.json", "schema_version": "1.0.0",
        "parser_version": PARSER_VERSION,
        "class_source_id": class_slug, "class_name": class_name,
        "generated_at": utc_now(),
        "counts": {
            "major_families": len(majors),
            "receptor_families": sum(1 for x in nodes if x["level"] == "receptor_family"),
            "receptor_records": len(receptors),
            "human_receptors": sum(1 for r in receptors if r["species"] == "Homo sapiens"),
            "species": len({r["species"] for r in receptors}),
        },
        "families": [
            {"source_id": n["source_id"], "project_slug": n["project_slug"],
             "name": n["name"],
             "n_receptor_families": sum(1 for x in nodes if x["level"] == "receptor_family"
                                        and x["parent_source_id"] == n["source_id"]),
             "n_receptor_records": sum(1 for r in receptors
                                       if r["major_family_source_id"] == n["source_id"]),
             "n_human_receptors": sum(1 for r in receptors
                                      if r["major_family_source_id"] == n["source_id"]
                                      and r["species"] == "Homo sapiens")}
            for n in majors
        ],
    }
    out2 = write_json(ROOT / "data/manifests/class_a_family_manifest.json", fam_manifest)

    write_json(ROOT / "data/raw/gpcrdb/taxonomy_provenance.json",
               {"records": f.provenance, "generated_at": utc_now()})

    print(json.dumps({"major_families": taxonomy["counts"]["major_families"],
                      "receptor_families": taxonomy["counts"]["receptor_families"],
                      "receptors": taxonomy["counts"]["receptors"],
                      "taxonomy": out, "family_manifest": out2}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
