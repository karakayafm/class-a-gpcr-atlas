#!/usr/bin/env python3
"""Write the Phase 1 freeze: six named hashes over the phase's artefacts.

Each hash is a ``content_sha256`` — computed after volatile fields are stripped — so re-running
the pipeline on a later date reproduces every value here unless the science itself changed.
The aggregate hashes are taken over the sorted list of member hashes, not over concatenated
bytes, so a member can be reformatted without moving the aggregate.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from common.canonical import content_sha256, canonical_dumps, write_json   # noqa: E402
from common.http import utc_now                                           # noqa: E402

PILOT = "001_006"


def h(rel: str) -> str:
    return content_sha256(json.loads((ROOT / rel).read_text(encoding="utf-8")))


def aggregate(members: dict[str, str]) -> str:
    return hashlib.sha256(canonical_dumps(members).encode("utf-8")).hexdigest()


def main() -> int:
    taxonomy = h("data/normalized/class_a_taxonomy.json")
    manifest = h("data/manifests/class_a_family_manifest.json")
    universe = h("data/normalized/class_a_structure_universe.json")
    availability = h("data/normalized/component_inventory_availability.json")

    pilot_members = {f: h(f"data/normalized/families/{PILOT}/{f}") for f in sorted([
        "receptors.json", "structures.json", "component_inventory.json",
        "source_manifest.json", "unresolved_records.json"])}
    pilot = aggregate(pilot_members)

    config_members = {p.name: content_sha256(json.loads(p.read_text(encoding="utf-8")))
                      for p in sorted((ROOT / "config").glob("*.json"))}
    schema_members = {str(p.relative_to(ROOT / "schemas")):
                      content_sha256(json.loads(p.read_text(encoding="utf-8")))
                      for p in sorted((ROOT / "schemas").rglob("*.json"))}
    governance = aggregate({**config_members,
                            **{f"schemas/{k}": v for k, v in schema_members.items()}})

    freeze = {
        "phase": 1,
        "generated_at": utc_now(),
        "hash_algorithm": "sha256",
        "hash_scope": "content_sha256: canonical JSON with volatile fields stripped "
                      "(config/project.json defines the volatile key set)",
        "named_hashes": {
            "class_a_taxonomy": taxonomy,
            "class_a_family_manifest": manifest,
            "class_a_structure_universe": universe,
            "component_inventory_availability": availability,
            "pilot_family_001_006": pilot,
            "governance_and_schemas": governance,
        },
        "members": {
            "pilot_family_001_006": pilot_members,
            "governance_and_schemas": {"config": config_members, "schemas": schema_members},
        },
        "counts": {
            "class_a_major_families": 11,
            "class_a_receptor_families": 61,
            "class_a_receptor_records": 29867,
            "class_a_human_receptors": 287,
            "class_a_structures": 1358,
            "structures_with_rcsb_metadata": 1356,
            "pilot_structures": 100,
            "pilot_entities": 560,
        },
        "reproduce": [
            "python3 pipeline/taxonomy/build_taxonomy.py",
            "python3 pipeline/universe/build_structure_universe.py",
            "python3 pipeline/inventory/build_component_inventory.py",
            "python3 pipeline/families/extract_family.py --family 001_006",
            "python3 tests/run_tests.py",
            "python3 pipeline/freeze_phase_1.py",
        ],
    }
    out = write_json(ROOT / "data/freezes/phase_1/freeze.json", freeze)
    lines = [f"{v}  {k}" for k, v in sorted(freeze["named_hashes"].items())]
    (ROOT / "data/freezes/phase_1/NAMED_HASHES.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"named_hashes": freeze["named_hashes"], "artifact": out}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
