#!/usr/bin/env python3
"""Phase 2 freeze: input manifest, output manifest, rule versions, source versions."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.canonical import canonical_dumps, content_sha256, write_json   # noqa: E402
from common.http import utc_now                                           # noqa: E402

def jl(rel):
    rows = [json.loads(l) for l in (ROOT / rel).read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"rows": len(rows), "content_sha256": content_sha256(rows)}

def js(rel):
    return {"content_sha256": content_sha256(json.loads((ROOT / rel).read_text(encoding="utf-8")))}

def agg(d):
    return hashlib.sha256(canonical_dumps(d).encode()).hexdigest()

def main() -> int:
    inputs = {
        "class_a_taxonomy.json": js("data/normalized/class_a_taxonomy.json"),
        "class_a_structure_universe.json": js("data/normalized/class_a_structure_universe.json"),
        "class_a_family_manifest.json": js("data/manifests/class_a_family_manifest.json"),
        "rcsb_entity_payload.json": js("data/raw/rcsb/entity_payload.json"),
    }
    configs = {p.name: content_sha256(json.loads(p.read_text(encoding="utf-8")))
               for p in sorted((ROOT / "config").glob("*.json"))}
    schemas = {p.name: content_sha256(json.loads(p.read_text(encoding="utf-8")))
               for p in sorted((ROOT / "schemas").glob("*.json"))}
    outputs = {n: jl(f"data/intermediate/{n}") for n in sorted([
        "structures.normalized.jsonl", "receptor_instances.jsonl", "entity_inventory.jsonl",
        "ligand_candidates.jsonl", "structure_ligand_observations.jsonl",
        "source_conflicts.jsonl", "manual_review_queue.jsonl"])}
    pilots = {
        "nucleotide/gold_review_table.jsonl": jl("data/pilots/nucleotide/gold_review_table.jsonl"),
        "peptide/entity_challenge.jsonl": jl("data/pilots/peptide/entity_challenge.jsonl"),
        "peptide/polymer_role_confusion_audit.jsonl":
            jl("data/pilots/peptide/polymer_role_confusion_audit.jsonl"),
        "cross_family_edge_cases/edge_cases.jsonl":
            jl("data/pilots/cross_family_edge_cases/edge_cases.jsonl"),
    }
    val = json.loads((ROOT / "reports/phase2/validation_results.json").read_text(encoding="utf-8"))
    freeze = {
        "phase": 2, "generated_at": utc_now(),
        "rule_version": "phase2-rules-1.0.0", "parser_version": "1.0.0",
        "hash_scope": "content_sha256 over canonical JSON with volatile fields stripped",
        "source_versions": {
            "GPCRdb": {"endpoint": "https://gpcrdb.org/services/", "retrieved": "2026-08-03",
                       "licence": "Data CC BY 4.0; code Apache 2.0"},
            "RCSB PDB": {"endpoint": "https://data.rcsb.org/graphql",
                         "operation": "graphql:Entities", "retrieved": "2026-08-04",
                         "licence": "PDB archive files: CC0 1.0"},
            "PDB Chemical Component Dictionary": {"via": "RCSB chem_comp", "retrieved": "2026-08-04"},
            "UniProt": {"used": "accessions relayed from RCSB polymer entities only",
                        "licence": "CC BY 4.0 (verified 2026-08-04)"},
            "GtoPdb": {"used": False, "licence_status": "owner_provided_official_verification"}},
        "named_hashes": {
            "phase2_inputs": agg(inputs),
            "phase2_configs": agg(configs),
            "phase2_schemas": agg(schemas),
            "phase2_outputs": agg(outputs),
            "phase2_pilots": agg(pilots),
            "phase2_validation": content_sha256(val)},
        "input_manifest": inputs, "config_manifest": configs, "schema_manifest": schemas,
        "output_manifest": outputs, "pilot_manifest": pilots,
        "validation": {"total": val["total"], "failed": val["failed"]},
        "counts": {"structures": 1358, "major_families": 11, "receptor_instances": 1517,
                   "entity_inventory_rows": 11039, "ligand_entities": 1331,
                   "observations": 1331, "source_conflicts": 100, "manual_review_items": 144},
        "reproduce": [
            "python3 pipeline/phase2/fetch_entities.py",
            "python3 pipeline/phase2/normalize.py",
            "python3 pipeline/phase2/build_pilots.py",
            "python3 tests/phase2/run_tests.py",
            "python3 pipeline/phase2/freeze_phase_2.py"],
        "cache_note": ("Raw API cache lives under data/cache/ and is NOT part of the production "
                       "payload. data/cache/rcsb_graphql holds 68 batch responses (~22 MB)."),
    }
    out = write_json(ROOT / "releases/phase2/freeze.json", freeze)
    (ROOT / "releases/phase2/NAMED_HASHES.txt").write_text(
        "\n".join(f"{v}  {k}" for k, v in sorted(freeze["named_hashes"].items())) + "\n",
        encoding="utf-8")
    print(json.dumps({"named_hashes": freeze["named_hashes"],
                      "artifact": {k: out[k] for k in ("bytes", "content_sha256")}}, indent=1))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
