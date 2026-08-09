#!/usr/bin/env python3
"""E3: cache and normalize CCD cross-references from live primary APIs."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import gzip
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/source_endpoints.json"
UNIVERSE = ROOT / "data/normalized/class_a_structure_universe.json"
OBSERVATIONS = ROOT / "data/intermediate/structure_ligand_observations.jsonl"
CONTACTS = ROOT / "data/contacts/by_family"
OUTPUT = ROOT / "data/intermediate/enrichment/chemical_xrefs.json"
SCHEMA = ROOT / "schemas/enrichment/chemical_xref.schema.json"
REPORT = ROOT / "reports/enrichment_xrefs.md"
USER_AGENT = "class-a-gpcr-atlas/5.0 (chemical xref enrichment; contact via repository)"
TODAY = dt.date.today().isoformat()


class CachedProvider:
    def __init__(self, name: str, cache_dir: Path, settings: dict, refresh: bool):
        self.name = name
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = settings["timeout_seconds"]
        self.retries = settings["retries"]
        self.delay = settings["delay_seconds"]
        self.workers = min(4, settings["max_workers"])
        self.refresh = refresh
        self.network_requests = 0
        self.cache_hits = 0
        self.http_errors = 0
        self.transport_errors = 0
        self._lock = threading.Lock()
        self._last_request = 0.0

    def _wait_for_slot(self) -> None:
        with self._lock:
            remaining = self.delay - (time.monotonic() - self._last_request)
            if remaining > 0:
                time.sleep(remaining)
            self._last_request = time.monotonic()
            self.network_requests += 1

    def request(self, key: str, url: str, body: dict | None = None) -> dict | list | None:
        cache = self.cache_dir / f"{key}.json"
        if cache.exists() and not self.refresh:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            # A transport marker is not a scientific response and must be retried.
            # HTTP no-match bodies remain valid cache entries.
            if not (isinstance(cached, dict) and "_fetch_error" in cached):
                with self._lock:
                    self.cache_hits += 1
                return cached
        encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        last_error = None
        for attempt in range(self.retries + 1):
            self._wait_for_slot()
            try:
                request = urllib.request.Request(url, data=encoded, headers=headers,
                                                 method="POST" if encoded is not None else "GET")
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                cache.write_bytes(raw)
                return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as error:
                raw = error.read()
                if raw:
                    cache.write_bytes(raw)
                with self._lock:
                    self.http_errors += 1
                if error.code in {204, 400, 404}:
                    if raw:
                        try:
                            return json.loads(raw.decode("utf-8"))
                        except Exception:
                            return None
                    cache.write_text(json.dumps({"_http_status": error.code}), encoding="utf-8")
                    return None
                last_error = f"HTTP {error.code}"
            except Exception as error:
                last_error = f"{type(error).__name__}: {error}"
            if attempt < self.retries:
                time.sleep(0.5 * (attempt + 1))
        with self._lock:
            self.transport_errors += 1
        marker = {"_fetch_error": last_error, "provider": self.name, "url": url}
        cache.write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
        return marker

    def map(self, jobs: list[tuple[str, str, dict | None]]) -> dict[str, object]:
        def run(job: tuple[str, str, dict | None]):
            key, url, body = job
            return key, self.request(key, url, body)
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
            for key, value in executor.map(run, jobs):
                results[key] = value
        return results


def scope_codes() -> tuple[list[str], dict[str, int]]:
    structures = json.loads(UNIVERSE.read_text(encoding="utf-8"))["structures"]
    gpcrdb = {
        ligand["PDB"].upper() for structure in structures
        for ligand in ((structure.get("gpcrdb_structure_record") or {}).get("raw_ligand_annotation") or [])
        if ligand.get("PDB")
    }
    observations = set()
    for line in OBSERVATIONS.read_text(encoding="utf-8").splitlines():
        ligand_id = json.loads(line).get("ligand_entity_id", "")
        parts = ligand_id.split(":")
        if len(parts) >= 4 and parts[2] == "np":
            observations.add(parts[3].upper())
    contacts = set()
    for path in sorted(CONTACTS.glob("*/residue_pair_contacts.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                code = json.loads(line).get("ligand_residue_name")
                if code:
                    contacts.add(code.upper())
    union = sorted(gpcrdb | observations | contacts)
    return union, {"gpcrdb": len(gpcrdb), "observations": len(observations),
                   "contacts": len(contacts), "union": len(union)}


def source_ids(registry: dict) -> dict[str, int]:
    found = {item["name"]: int(item["sourceID"]) for item in registry.get("sources", [])}
    required = {"rcsb_pdb", "chembl", "gtopdb", "pubchem"}
    if not required <= found.keys():
        raise RuntimeError(f"UniChem registry lacks sources: {sorted(required - found.keys())}")
    return {name: found[name] for name in sorted(required)}


def source_candidates(unichem: dict | None, short_name: str) -> list[str]:
    values = set()
    if isinstance(unichem, dict):
        for compound in unichem.get("compounds", []):
            for source in compound.get("sources", []):
                if source.get("shortName") == short_name and source.get("compoundId"):
                    values.add(str(source["compoundId"]))
    return sorted(values)


def standard_inchi_key(unichem: dict | None) -> str | None:
    keys = {compound.get("standardInchiKey") for compound in (unichem or {}).get("compounds", [])
            if compound.get("standardInchiKey")}
    return next(iter(keys)) if len(keys) == 1 else None


def rcsb_candidates(rcsb: dict | None, resource: str) -> list[str]:
    if not isinstance(rcsb, dict):
        return []
    return sorted({str(item["resource_accession_code"])
                   for item in rcsb.get("rcsb_chem_comp_related", []) or []
                   if item.get("resource_name") == resource and item.get("resource_accession_code")})


def normalize_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def direct_basis(unichem_values: list[str], rcsb_values: list[str], selected: str) -> str:
    in_u, in_r = selected in unichem_values, selected in rcsb_values
    if in_u and in_r:
        return "unichem_and_rcsb_direct"
    return "unichem_pdb_direct" if in_u else "rcsb_related_direct"


def choose_pubchem(code: str, candidates: list[str], payload: dict | None,
                   name: str | None, inchi_key: str | None, basis_by_id: dict[str, str]):
    properties = ((payload or {}).get("PropertyTable") or {}).get("Properties") or []
    verified = {str(item.get("CID")): item for item in properties if item.get("CID") is not None}
    candidates = [candidate for candidate in candidates if candidate in verified]
    if not candidates:
        return None, {"source": "pubchem", "reason": "no_verified_candidate", "candidates": []}
    approximate = False
    basis = basis_by_id[candidates[0]] if len(candidates) == 1 else None
    if len(candidates) > 1:
        exact_keys = [candidate for candidate in candidates
                      if inchi_key and verified[candidate].get("InChIKey") == inchi_key]
        if len(exact_keys) != 1:
            reason = ("multiple_full_inchikey_candidates" if len(exact_keys) > 1
                      else "no_full_inchikey_candidate")
            return None, {"source": "pubchem", "reason": reason,
                          "candidates": exact_keys or candidates}
        candidates = exact_keys
        basis = "pubchem_unique_full_inchikey"
    selected = candidates[0]
    item = verified[selected]
    if inchi_key and item.get("InChIKey") and item["InChIKey"] != inchi_key:
        approximate = True
        basis = f"{basis}_structure_key_mismatch"
    return {
        "id": selected, "label": item.get("Title"),
        "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{selected}",
        "approximate": approximate, "basis": basis, "retrieved": TODAY,
    }, None


def choose_chembl(candidates: list[str], payload: dict | None, inchi_key: str | None,
                  basis_by_id: dict[str, str]):
    if len(candidates) != 1:
        return None, {"source": "chembl", "reason": "multiple_direct_candidates",
                      "candidates": candidates}
    selected = candidates[0]
    if not isinstance(payload, dict) or payload.get("molecule_chembl_id") != selected:
        return None, {"source": "chembl", "reason": "candidate_not_verified",
                      "candidates": candidates}
    structure = payload.get("molecule_structures") or {}
    key = structure.get("standard_inchi_key")
    approximate = bool(inchi_key and key and key != inchi_key)
    basis = basis_by_id[selected] + ("_structure_key_mismatch" if approximate else "")
    return {
        "id": selected, "label": payload.get("pref_name"),
        "url": f"https://www.ebi.ac.uk/chembl/explore/compound/{selected}",
        "approximate": approximate, "basis": basis, "retrieved": TODAY,
    }, None


def choose_gtopdb(payload: object, name_payload: object, name: str | None):
    if isinstance(payload, list) and len(payload) == 1 and payload[0].get("ligandId"):
        item = payload[0]
        return {
            "id": str(item["ligandId"]), "label": item.get("name"),
            "url": f"https://www.guidetopharmacology.org/GRAC/LigandDisplayForward?ligandId={item['ligandId']}",
            "approximate": False, "basis": "gtopdb_exact_full_inchikey", "retrieved": TODAY,
        }, None
    if isinstance(name_payload, list):
        matches = [item for item in name_payload if item.get("ligandId") and
                   normalize_name(item.get("name")) == normalize_name(name)]
        if len(matches) == 1:
            item = matches[0]
            return {
                "id": str(item["ligandId"]), "label": item.get("name"),
                "url": f"https://www.guidetopharmacology.org/GRAC/LigandDisplayForward?ligandId={item['ligandId']}",
                "approximate": True, "basis": "gtopdb_exact_normalized_name", "retrieved": TODAY,
            }, None
        if len(matches) > 1:
            return None, {"source": "gtopdb", "reason": "multiple_name_matches",
                          "candidates": [str(item["ligandId"]) for item in matches]}
    return None, {"source": "gtopdb", "reason": "no_exact_structure_or_name_match",
                  "candidates": []}


def cache_outcomes(cache_dir: Path) -> Counter:
    outcomes = Counter()
    for path in cache_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            outcomes["parse_error"] += 1
            continue
        if isinstance(payload, dict) and "_fetch_error" in payload:
            outcomes["transport_marker"] += 1
        elif isinstance(payload, dict) and "_http_status" in payload:
            outcomes["http_status_marker"] += 1
        elif isinstance(payload, dict) and ("error" in payload or "error_message" in payload or
                                            "Fault" in payload):
            outcomes["api_error_or_no_match_body"] += 1
        else:
            outcomes["response_body"] += 1
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    codes, scope = scope_codes()
    if len(codes) != 580:
        raise RuntimeError(f"scope changed: expected 580 CCD codes, found {len(codes)}")

    providers = {
        name: CachedProvider(name, ROOT / f"data/cache/{name}", config[name]["rate"], args.refresh)
        for name in ("rcsb_chemcomp", "unichem", "gtopdb", "chembl", "pubchem")
    }
    registry = providers["unichem"].request("sources", config["unichem"]["sources"])
    ids = source_ids(registry)

    rcsb_jobs = [(code, config["rcsb_chemcomp"]["base"] + code, None) for code in codes]
    rcsb = providers["rcsb_chemcomp"].map(rcsb_jobs)
    unichem_jobs = [(code, config["unichem"]["compounds"],
                     {"compound": code, "type": "sourceID", "sourceID": ids["rcsb_pdb"]})
                    for code in codes]
    unichem = providers["unichem"].map(unichem_jobs)

    meta = {}
    for code in codes:
        rc = rcsb.get(code) if isinstance(rcsb.get(code), dict) else {}
        uc = unichem.get(code) if isinstance(unichem.get(code), dict) else {}
        chem = rc.get("chem_comp") or {}
        key = standard_inchi_key(uc) or ((rc.get("rcsb_chem_comp_descriptor") or {})
                                         .get("InChIKey"))
        chembl_u, chembl_r = source_candidates(uc, "chembl"), rcsb_candidates(rc, "ChEMBL")
        pubchem_u, pubchem_r = source_candidates(uc, "pubchem"), rcsb_candidates(rc, "PubChem")
        chembl_candidates = sorted(set(chembl_u + chembl_r))
        pubchem_candidates = sorted(set(pubchem_u + pubchem_r), key=lambda value: (len(value), value))
        meta[code] = {
            "name": chem.get("name"), "formula": chem.get("formula"), "inchi_key": key,
            "chembl_candidates": chembl_candidates, "pubchem_candidates": pubchem_candidates,
            "chembl_basis": {value: direct_basis(chembl_u, chembl_r, value)
                              for value in chembl_candidates},
            "pubchem_basis": {value: direct_basis(pubchem_u, pubchem_r, value)
                               for value in pubchem_candidates},
        }

    chembl_jobs = []
    pubchem_jobs = []
    gtopdb_jobs = []
    for code, item in meta.items():
        if len(item["chembl_candidates"]) == 1:
            cid = item["chembl_candidates"][0]
            chembl_jobs.append((code, config["chembl"]["base"] + cid + ".json", None))
        if item["pubchem_candidates"]:
            joined = ",".join(item["pubchem_candidates"])
            url = (config["pubchem"]["base"] + joined +
                   "/property/Title,IUPACName,InChIKey/JSON")
            pubchem_jobs.append((code, url, None))
        if item["inchi_key"]:
            url = config["gtopdb"]["base"] + "ligands?" + urllib.parse.urlencode(
                {"inchikey": item["inchi_key"]})
            gtopdb_jobs.append((code, url, None))
    chembl = providers["chembl"].map(chembl_jobs)
    pubchem = providers["pubchem"].map(pubchem_jobs)
    gtopdb = providers["gtopdb"].map(gtopdb_jobs)

    name_jobs = []
    for code, item in meta.items():
        exact = gtopdb.get(code)
        if not (isinstance(exact, list) and len(exact) == 1) and item["name"]:
            url = config["gtopdb"]["base"] + "ligands?" + urllib.parse.urlencode(
                {"name": item["name"]})
            name_jobs.append((code + "_name", url, None))
    gtopdb_names = providers["gtopdb"].map(name_jobs)

    output = []
    for code in codes:
        item = meta[code]
        ambiguities = []
        chembl_xref, issue = choose_chembl(item["chembl_candidates"], chembl.get(code),
                                           item["inchi_key"], item["chembl_basis"])
        if issue:
            ambiguities.append(issue)
        pubchem_xref, issue = choose_pubchem(code, item["pubchem_candidates"], pubchem.get(code),
                                             item["name"], item["inchi_key"],
                                             item["pubchem_basis"])
        if issue:
            ambiguities.append(issue)
        gtopdb_xref, issue = choose_gtopdb(gtopdb.get(code), gtopdb_names.get(code + "_name"),
                                           item["name"])
        if issue:
            ambiguities.append(issue)
        output.append({
            "ccd": code, "name": item["name"], "formula": item["formula"],
            "inchi_key": item["inchi_key"], "chembl": chembl_xref,
            "pubchem": pubchem_xref, "gtopdb": gtopdb_xref,
            "ambiguities": ambiguities, "retrieved": TODAY,
        })

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = [(row["ccd"], error.message) for row in output
              for error in validator.iter_errors(row)]
    if errors:
        raise RuntimeError(f"chemical xref schema errors: {errors[:10]}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n", encoding="utf-8")

    pilot_text = REPORT.read_text(encoding="utf-8")
    pilot_text = pilot_text.split("\nThe bulk section below", 1)[0]
    pilot_text = pilot_text.split("\n## Bulk results", 1)[0].rstrip()
    coverage = {source: sum(row[source] is not None for row in output)
                for source in ("chembl", "pubchem", "gtopdb")}
    approximate = {source: sum(bool(row[source] and row[source]["approximate"]) for row in output)
                   for source in coverage}
    missing = {source: [row["ccd"] for row in output if row[source] is None]
               for source in coverage}
    pubchem_resolved = sum(bool(row["pubchem"] and
                                row["pubchem"]["basis"] == "pubchem_unique_full_inchikey")
                           for row in output)
    pubchem_unresolved_multiple = [
        row for row in output
        if any(issue["source"] == "pubchem" and issue["reason"] in {
            "multiple_full_inchikey_candidates", "no_full_inchikey_candidate"
        } for issue in row["ambiguities"])
    ]
    report = [pilot_text, "", "## Bulk results", "",
              f"Scope: {scope['union']} CCD codes (GPCRdb {scope['gpcrdb']}, observations "
              f"{scope['observations']}, contacts {scope['contacts']}).", "",
              "| Source | Matched | Coverage | Approximate | Approximate among matches | HTTP errors | Transport errors |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for source in ("chembl", "pubchem", "gtopdb"):
        provider = providers[source]
        cov = 100.0 * coverage[source] / len(output)
        app = 100.0 * approximate[source] / coverage[source] if coverage[source] else 0.0
        report.append(f"| {source} | {coverage[source]} | {cov:.2f}% | {approximate[source]} | "
                      f"{app:.2f}% | {provider.http_errors} | {provider.transport_errors} |")
    report += ["", "RCSB ChemComp and UniChem retrieval:", "",
               f"- RCSB ChemComp cache coverage: {sum(isinstance(rcsb.get(c), dict) and bool((rcsb[c] or {}).get('chem_comp')) for c in codes)}/{len(codes)}.",
               f"- UniChem compound matches: {sum(bool((unichem.get(c) or {}).get('compounds')) for c in codes)}/{len(codes)}.",
               f"- Total network requests this run: {sum(p.network_requests for p in providers.values())}; cache hits: {sum(p.cache_hits for p in providers.values())}.", "",
               "### PubChem multiple-candidate resolution", "",
               f"- Resolved by a unique full InChIKey match: {pubchem_resolved}.",
               f"- Still null because zero or multiple candidates share the CCD full InChIKey: {len(pubchem_unresolved_multiple)}.",
               "- No name-based choice is made among multiple direct candidates.", "",
               "### Unmatched CCD codes", ""]
    for source in ("chembl", "pubchem", "gtopdb"):
        report.append(f"- **{source}** ({len(missing[source])}): " +
                      (", ".join(f"`{code}`" for code in missing[source]) if missing[source] else "none"))
    report += ["", "### Approximate mappings", ""]
    for source in ("chembl", "pubchem", "gtopdb"):
        values = [(row["ccd"], row[source]["id"], row[source]["basis"])
                  for row in output if row[source] and row[source]["approximate"]]
        report.append(f"- **{source}** ({len(values)}): " +
                      ("; ".join(f"`{ccd}` → `{xref}` ({basis})" for ccd, xref, basis in values)
                       if values else "none"))
    report += ["", "### Fetch diagnostics", ""]
    for name, provider in providers.items():
        report.append(f"- `{name}`: network={provider.network_requests}, cache_hits={provider.cache_hits}, "
                      f"http_errors={provider.http_errors}, transport_errors={provider.transport_errors}")
    report += ["", "### Persistent cache outcomes", "",
               "These counts are derived from the cached bodies and therefore remain meaningful "
               "on a zero-network rerun.", "",
               "| Source | Response bodies | API error/no-match bodies | HTTP markers | Transport markers | Parse errors |",
               "|---|---:|---:|---:|---:|---:|"]
    for name, provider in providers.items():
        outcome = cache_outcomes(provider.cache_dir)
        report.append(f"| {name} | {outcome['response_body']} | "
                      f"{outcome['api_error_or_no_match_body']} | {outcome['http_status_marker']} | "
                      f"{outcome['transport_marker']} | {outcome['parse_error']} |")
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"scope": scope, "records": len(output), "coverage": coverage,
                      "approximate": approximate, "missing": {k: len(v) for k, v in missing.items()},
                      "pubchem_multiple_resolved_by_full_inchikey": pubchem_resolved,
                      "pubchem_multiple_still_ambiguous": len(pubchem_unresolved_multiple),
                      "network_requests": sum(p.network_requests for p in providers.values()),
                      "cache_hits": sum(p.cache_hits for p in providers.values())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
