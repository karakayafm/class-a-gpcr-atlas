#!/usr/bin/env python3
"""Phase 3 freeze: input/output manifests, source and rule versions, per-family hashes."""
from __future__ import annotations
import gzip, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from common.canonical import canonical_dumps, content_sha256, write_json   # noqa: E402
from common.http import utc_now                                           # noqa: E402
P3, CON = ROOT/"data/intermediate/phase3", ROOT/"data/contacts"

def jl(p):
    rows=[json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"rows":len(rows),"content_sha256":content_sha256(rows)}
def agg(d): return hashlib.sha256(canonical_dumps(d).encode()).hexdigest()

def main() -> int:
    fam, fam_rows = {}, []
    for f in sorted((CON/"by_family").glob("*/residue_pair_contacts.jsonl.gz")):
        rows=[json.loads(l) for l in gzip.open(f,"rt")]
        fam[f.parent.name]={"rows":len(rows),"content_sha256":content_sha256(rows)}
        fam_rows+=rows
    fam_rows.sort(key=lambda r:r["contact_id"])
    inputs={
      "phase2_freeze.json":{"content_sha256":content_sha256(json.loads(
          (ROOT/"releases/phase2/freeze.json").read_text(encoding="utf-8")))},
      "structures.normalized.jsonl":jl(ROOT/"data/intermediate/structures.normalized.jsonl"),
      "structure_ligand_observations.jsonl":jl(ROOT/"data/intermediate/structure_ligand_observations.jsonl"),
      "receptor_instances.jsonl":jl(ROOT/"data/intermediate/receptor_instances.jsonl"),
      "entity_inventory.jsonl":jl(ROOT/"data/intermediate/entity_inventory.jsonl"),
      "gpcrdb_receptor_residues.json":{"content_sha256":content_sha256(json.loads(
          (ROOT/"data/raw/gpcrdb/receptor_residues.json").read_text(encoding="utf-8")))},
    }
    outputs={n:jl(P3/n) for n in sorted([
      "coordinate_manifest.jsonl","receptor_instance_chain_crosswalk.jsonl",
      "receptor_residue_mapping.jsonl","ligand_coordinate_mapping.jsonl",
      "observation_coordinate_context.jsonl","site_class_review.jsonl",
      "review_resolutions.jsonl","contact_eligibility.jsonl","excluded_observations.jsonl",
      "tethered_ligand_candidates.jsonl"])}
    outputs["observation_contact_summary.jsonl"]=jl(CON/"observation_contact_summary.jsonl")
    configs={p.name:content_sha256(json.loads(p.read_text(encoding="utf-8")))
             for p in sorted((ROOT/"config/phase3").glob("*.json"))}
    schemas={p.name:content_sha256(json.loads(p.read_text(encoding="utf-8")))
             for p in sorted((ROOT/"schemas/phase3").glob("*.json"))}
    val=json.loads((ROOT/"reports/phase3/validation_results.json").read_text(encoding="utf-8"))
    reg=json.loads((ROOT/"data/pilots/phase3/aminergic_regression/regression_summary.json")
                   .read_text(encoding="utf-8"))
    named={
      "coordinate_manifest_sha":outputs["coordinate_manifest.jsonl"]["content_sha256"],
      "receptor_chain_crosswalk_sha":outputs["receptor_instance_chain_crosswalk.jsonl"]["content_sha256"],
      "receptor_residue_mapping_sha":outputs["receptor_residue_mapping.jsonl"]["content_sha256"],
      "ligand_coordinate_mapping_sha":outputs["ligand_coordinate_mapping.jsonl"]["content_sha256"],
      "contact_eligibility_sha":outputs["contact_eligibility.jsonl"]["content_sha256"],
      "raw_exact_distance_contacts_sha":content_sha256(fam_rows),
      "contacts_4A_sha":content_sha256([r for r in fam_rows if r["within_4A"]]),
      "contacts_4_5A_sha":content_sha256([r for r in fam_rows if r["within_4_5A"]]),
      "contacts_5A_sha":content_sha256([r for r in fam_rows if r["within_5A"]]),
      "per_family_contacts_sha":agg(fam),
      "aminergic_regression_crosswalk_sha":jl(
          ROOT/"data/pilots/phase3/aminergic_regression/exact_crosswalk.jsonl")["content_sha256"],
      "manual_review_queue_sha":outputs["review_resolutions.jsonl"]["content_sha256"],
    }
    d=ROOT/"releases/phase3"; d.mkdir(parents=True,exist_ok=True)
    write_json(d/"INPUT_MANIFEST.json",{"generated_at":utc_now(),"inputs":inputs})
    write_json(d/"OUTPUT_MANIFEST.json",{"generated_at":utc_now(),"outputs":outputs,
                                         "per_family_contacts":fam})
    write_json(d/"SOURCE_VERSIONS.json",{"generated_at":utc_now(),"sources":{
      "RCSB coordinates":{"endpoint":"https://files.rcsb.org/download/{PDB_ID}.cif.gz",
        "retrieved":"2026-08-04","licence":"PDB archive files: CC0 1.0","files":1358},
      "RCSB Data API (GraphQL)":{"retrieved":"2026-08-04 (Phase 2)","licence":"CC0 1.0"},
      "GPCRdb residues":{"endpoint":"https://gpcrdb.org/services/residues/extended/{entry}/",
        "retrieved":"2026-08-04","licence":"Data CC BY 4.0","receptors":200,"residues":79068},
      "UniProt":{"used":"accessions relayed from RCSB only","licence":"CC BY 4.0 (verified 2026-08-04)"}}})
    write_json(d/"RULE_VERSIONS.json",{"generated_at":utc_now(),
      "rule_version":"phase3-rules-1.0.0","mmcif_parser":"mmcif-reader-1.0.0",
      "coordinate_parser":"phase3-coordinates-1.0.0",
      "float_serialisation":"round(x, 6); display rounding is a separate field",
      "row_order":"sorted by contact_id / pdb_id; gzip written with mtime=0",
      "null_representation":"JSON null; absent source distinguished from null value",
      "string_normalisation":"source strings verbatim; generic numbers normalised only for regression comparison",
      "configs":configs,"schemas":schemas})
    write_json(d/"FAMILY_HASHES.json",{"generated_at":utc_now(),"per_family":fam,
      "global_chain":agg(fam)})
    (d/"NAMED_HASHES.txt").write_text(
        "\n".join(f"{v}  {k}" for k,v in sorted(named.items()))+"\n",encoding="utf-8")
    (d/"VALIDATION_REPORT.md").write_text(
        f"# Phase 3 validation\n\n{val['total']} checks, {val['failed']} failed.\n\n"
        + "\n".join(f"- {c['group']} :: {c['name']} — {c['result']}"
                    for c in val["checks"]) + "\n", encoding="utf-8")
    lines=[]
    for base in (P3, CON, ROOT/"config/phase3", ROOT/"schemas/phase3",
                 ROOT/"data/pilots/phase3", ROOT/"releases/phase3"):
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.name!="checksums.sha256":
                h=hashlib.sha256(p.read_bytes()).hexdigest()
                lines.append(f"{h}  {p.relative_to(ROOT)}")
    (d/"checksums.sha256").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"named_hashes":named,"families":len(fam),
                      "contacts":len(fam_rows),"files_checksummed":len(lines)},indent=1))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
