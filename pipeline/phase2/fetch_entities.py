#!/usr/bin/env python3
"""Phase 2 — complete entity retrieval for every Class A structure.

One GraphQL request per batch of entries replaces ~7,500 REST requests. The response carries
everything the entity inventory needs and nothing it does not: polymer entities with UniProt
alignment and mutation strings, non-polymer entities with their CCD record and per-instance
chain/sequence identifiers, branched entities, and the entry-level solvent atom count.

Water is deliberately *not* requested per instance. It is summarised at structure level
(``deposited_solvent_atom_count``), because a per-water inventory row would be tens of thousands
of records that no downstream stage reads.

    python3 pipeline/phase2/fetch_entities.py [--batch 20] [--refresh]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))

from common.canonical import write_json, PARSER_VERSION            # noqa: E402
from common.http import utc_now                                    # noqa: E402

ENDPOINT = "https://data.rcsb.org/graphql"
UA = "class-a-gpcr-atlas/2.0 (Phase 2 entity inventory; contact via repository)"
CACHE = ROOT / "data/cache/rcsb_graphql"

# Every field here is consumed by a later stage. Nothing is fetched "in case".
QUERY = """
query Entities($ids: [String!]!) {
  entries(entry_ids: $ids) {
    rcsb_id
    rcsb_entry_info {
      polymer_entity_count nonpolymer_entity_count branched_entity_count
      solvent_entity_count deposited_solvent_atom_count
      deposited_atom_count deposited_model_count
      polymer_composition selected_polymer_entity_types
    }
    rcsb_accession_info { deposit_date initial_release_date revision_date }
    struct { title }
    exptl { method }
    polymer_entities {
      rcsb_id
      rcsb_polymer_entity { pdbx_description pdbx_number_of_molecules pdbx_mutation formula_weight }
      entity_poly { rcsb_entity_polymer_type type rcsb_sample_sequence_length pdbx_seq_one_letter_code_can }
      rcsb_polymer_entity_container_identifiers {
        entity_id auth_asym_ids asym_ids uniprot_ids
      }
      rcsb_entity_source_organism { ncbi_scientific_name ncbi_taxonomy_id }
      rcsb_entity_host_organism { ncbi_scientific_name }
      rcsb_polymer_entity_align {
        reference_database_accession reference_database_name
        aligned_regions { entity_beg_seq_id ref_beg_seq_id length }
      }
      rcsb_polymer_entity_annotation { type name annotation_id }
      uniprots { rcsb_id }
    }
    nonpolymer_entities {
      rcsb_id
      rcsb_nonpolymer_entity { pdbx_description formula_weight pdbx_number_of_molecules }
      rcsb_nonpolymer_entity_container_identifiers {
        entity_id nonpolymer_comp_id auth_asym_ids asym_ids
      }
      nonpolymer_comp {
        chem_comp { id name formula formula_weight type mon_nstd_parent_comp_id }
        rcsb_chem_comp_descriptor { InChIKey }
        rcsb_chem_comp_info { atom_count_heavy }
      }
      nonpolymer_entity_instances {
        rcsb_nonpolymer_entity_instance_container_identifiers {
          entity_id auth_asym_id asym_id auth_seq_id comp_id
        }
        rcsb_nonpolymer_instance_annotation { type name annotation_id description }
      }
    }
    branched_entities {
      rcsb_id
      rcsb_branched_entity { pdbx_description formula_weight }
      rcsb_branched_entity_container_identifiers { entity_id auth_asym_ids asym_ids }
    }
  }
}
"""


def post(ids: list[str], timeout: float, retries: int) -> tuple[dict | None, str | None, int]:
    body = json.dumps({"query": QUERY, "variables": {"ids": ids}}).encode("utf-8")
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                ENDPOINT, data=body,
                headers={"Content-Type": "application/json", "Accept": "application/json",
                         "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                raw = fh.read()
            payload = json.loads(raw.decode("utf-8"))
            if "errors" in payload:
                msgs = "; ".join(e.get("message", "?") for e in payload["errors"][:3])
                # A GraphQL error is a real answer, not a transport failure: do not retry it.
                return None, f"graphql_error: {msgs}", attempt
            return payload, None, attempt
        except urllib.error.HTTPError as exc:
            last = f"http_{exc.code}"
        except Exception as exc:
            last = type(exc).__name__
        time.sleep(0.8 * (attempt + 1))
    return None, last or "failed", retries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args()

    uni = json.loads((ROOT / "data/normalized/class_a_structure_universe.json")
                     .read_text(encoding="utf-8"))
    # Only entries RCSB actually serves. The two GPCRdb-only ids stay in the universe and are
    # carried through Phase 2 with an explicit completeness flag, never silently dropped.
    ids = sorted(s["pdb_id"] for s in uni["structures"]
                 if "rcsb_unresolved" not in s["qc_flags"])
    unserved = sorted(s["pdb_id"] for s in uni["structures"]
                      if "rcsb_unresolved" in s["qc_flags"])
    CACHE.mkdir(parents=True, exist_ok=True)

    batches = [ids[i:i + args.batch] for i in range(0, len(ids), args.batch)]
    entries: dict[str, dict] = {}
    provenance: list[dict] = []
    failures: list[dict] = []

    for i, batch in enumerate(batches, 1):
        key = hashlib.sha256(("|".join(batch)).encode()).hexdigest()[:24]
        cpath = CACHE / f"entities_{key}.json"
        if cpath.exists() and not args.refresh:
            payload = json.loads(cpath.read_text(encoding="utf-8"))
            cache_hit, err, tries = True, None, 0
        else:
            payload, err, tries = post(batch, args.timeout, args.retries)
            cache_hit = False
            if payload is not None:                 # only a successful body touches the cache
                cpath.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        rec = {
            "provider": "RCSB PDB", "operation": "graphql:Entities", "endpoint": ENDPOINT,
            "entry_ids": batch, "batch_index": i, "retrieved_at": utc_now(),
            "cache_path": str(cpath.relative_to(ROOT)), "cache_hit": cache_hit,
            "retry_count": tries, "success": payload is not None, "error_message": err,
        }
        if payload is not None:
            rec["response_sha256"] = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            got = {e["rcsb_id"].upper(): e for e in (payload.get("data", {}).get("entries") or [])
                   if e}
            entries.update(got)
            rec["entries_returned"] = len(got)
            for missing in set(batch) - set(got):
                failures.append({"pdb_id": missing, "reason": "absent_from_graphql_response",
                                 "batch_index": i})
        else:
            for pid in batch:
                failures.append({"pdb_id": pid, "reason": err, "batch_index": i})
        provenance.append(rec)
        if i % 10 == 0 or i == len(batches):
            print(f"  batch {i}/{len(batches)}  entries={len(entries)}", file=sys.stderr)

    out = write_json(ROOT / "data/raw/rcsb/entity_payload.json", {
        "schema": "raw_entity_payload", "parser_version": PARSER_VERSION,
        "generated_at": utc_now(),
        "source": {"provider": "RCSB PDB", "operation": "graphql:Entities",
                   "endpoint": ENDPOINT, "query_sha256": hashlib.sha256(
                       QUERY.encode()).hexdigest()},
        "counts": {"requested": len(ids), "returned": len(entries),
                   "not_served_by_rcsb": len(unserved), "failures": len(failures)},
        "not_served_by_rcsb": unserved,
        "failures": failures,
        "entries": entries,
    })
    write_json(ROOT / "data/raw/rcsb/entity_fetch_provenance.json",
               {"generated_at": utc_now(), "requests": provenance})
    print(json.dumps({"requested": len(ids), "returned": len(entries),
                      "failures": len(failures), "batches": len(batches),
                      "artifact": {k: out[k] for k in ("bytes", "content_sha256")}}, indent=1))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
