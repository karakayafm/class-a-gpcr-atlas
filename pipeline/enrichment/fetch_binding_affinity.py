#!/usr/bin/env python3
"""Reported binding affinity, from the one BindingDB subset whose licence permits redistribution.

BindingDB states two licences for its contents, not one:

    Data imported from ChEMBL are provided under their Creative Commons Attribution-Share Alike
    3.0 Unported License. All data curated by BindingDB staff are provided under the Creative
    Commons Attribution 3.0 License.

    -- https://www.bindingdb.org/rwd/bind/info.jsp

Only the second of those can be redistributed here. This release licenses its own derived data
CC BY-NC 4.0, and CC BY-SA material cannot be relicensed under a noncommercial term, so anything
carrying share-alike would force the licence of the whole release. The REST API returns no field
saying which measurement came from where -- its columns are affinity, affinity_type, doi, pmid,
query and smile -- so the API cannot be used for this at all.

The downloads can. BindingDB publishes its TSV split by source, and the file this script reads
is the staff-curated one; the ChEMBL-derived rows are a separate download that is never fetched.
The other subsets (PDSPKi, Patents, PubChem, CSAR, ITC) fall under neither of the two stated
categories, so their terms are not established by that sentence and they are left alone.

What is carried per ligand-receptor pair: the measurement type, how many measurements there are,
their median and range, and the PubMed identifiers they come from. Not a single headline number --
affinity is a property of a compound, a target and an assay together, and the spread across
assays is part of what the reader needs to see.

Matching is by InChIKey for the compound and by UniProt entry name for the receptor, both of
which this atlas already holds. Neither is a fuzzy match; a pair either keys exactly or is absent.

    python3 pipeline/enrichment/fetch_binding_affinity.py [--refresh]
"""
from __future__ import annotations
import argparse, collections, csv, glob, hashlib, io, json, statistics, sys, urllib.request, zipfile
from datetime import date, timezone, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/cache/bindingdb"
OUT = ROOT / "data/intermediate/enrichment"
WEB = ROOT / "site/data/web"

RELEASE = "202608"
FILENAME = f"BindingDB_BindingDB_Articles_{RELEASE}_tsv.zip"
URL = f"https://www.bindingdb.org/rwd/bind/downloads/{FILENAME}"
LICENCE_PAGE = "https://www.bindingdb.org/rwd/bind/info.jsp"
UA = {"User-Agent": "class-a-gpcr-atlas/enrichment (+https://github.com/karakayafm/class-a-gpcr-atlas)"}

# The four the atlas reports. Ki and Kd are binding constants; IC50 and EC50 are functional and
# depend on the assay's readout, which is why the type travels with every value.
MEASURES = [("Ki (nM)", "Ki"), ("Kd (nM)", "Kd"), ("IC50 (nM)", "IC50"), ("EC50 (nM)", "EC50")]
csv.field_size_limit(10 ** 9)


def fetch(refresh: bool) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / FILENAME
    if path.is_file() and not refresh:
        return path.read_bytes()
    with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=600) as response:
        blob = response.read()
    path.write_bytes(blob)
    return blob


def our_keys() -> tuple[dict[str, str], dict[str, str]]:
    """InChIKey -> component code, and UniProt entry name -> receptor entry name."""
    chemistry = json.loads((WEB / "global/ligand_chemistry.json").read_text(encoding="utf-8"))
    by_inchikey = {r["inchikey"]: r["ccd"] for r in chemistry["records"] if r.get("inchikey")}
    receptors = {}
    for path in sorted(glob.glob(str(WEB / "families/*/receptors.json"))):
        for row in json.loads(Path(path).read_text(encoding="utf-8"))["receptors"]:
            receptors[row["receptor_entry_name"].upper()] = row["receptor_entry_name"]
    return by_inchikey, receptors


def parse_value(raw: str) -> float | None:
    """BindingDB reports limits as '>1000' or '<0.5'. A limit is not a measurement and is not
       averaged into one; it is dropped, and the count reflects what remained."""
    text = (raw or "").strip()
    if not text or text[0] in "<>":
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value > 0 else None


def build(blob: bytes) -> dict:
    by_inchikey, receptors = our_keys()
    archive = zipfile.ZipFile(io.BytesIO(blob))
    member = archive.namelist()[0]
    buckets: dict[tuple[str, str, str], list[float]] = collections.defaultdict(list)
    papers: dict[tuple[str, str, str], set[str]] = collections.defaultdict(set)
    limits: dict[tuple[str, str, str], int] = collections.Counter()
    scanned = 0

    with archive.open(member) as handle:
        reader = csv.reader((line.decode("utf-8", "replace") for line in handle),
                            delimiter="\t", quoting=csv.QUOTE_NONE)
        head = next(reader)
        i_key = head.index("Ligand InChI Key")
        i_entry = head.index("UniProt (SwissProt) Entry Name of Target Chain 1")
        i_pmid = head.index("PMID")
        columns = [(head.index(column), label) for column, label in MEASURES]
        for row in reader:
            scanned += 1
            if len(row) <= i_entry:
                continue
            ccd = by_inchikey.get(row[i_key].strip())
            if not ccd:
                continue
            receptor = receptors.get(row[i_entry].strip().upper())
            if not receptor:
                continue
            for index, label in columns:
                if index >= len(row):
                    continue
                raw = row[index].strip()
                if not raw:
                    continue
                value = parse_value(raw)
                key = (ccd, receptor, label)
                if value is None:
                    limits[key] += 1
                    continue
                buckets[key].append(value)
                pmid = row[i_pmid].strip() if i_pmid < len(row) else ""
                if pmid.isdigit():
                    papers[key].add(pmid)

    records: dict[str, list[dict]] = collections.defaultdict(list)
    for (ccd, receptor, label), values in sorted(buckets.items()):
        values.sort()
        records[ccd].append({
            "receptor": receptor,
            "type": label,
            "n": len(values),
            "median_nm": round(statistics.median(values), 4),
            "min_nm": round(values[0], 4),
            "max_nm": round(values[-1], 4),
            "limits_excluded": limits.get((ccd, receptor, label), 0),
            "pmids": sorted(papers[(ccd, receptor, label)])[:12],
        })
    for rows in records.values():
        rows.sort(key=lambda r: (r["receptor"], r["type"]))

    pairs = {(ccd, row["receptor"]) for ccd, rows in records.items() for row in rows}
    digest = hashlib.sha256(blob).hexdigest()
    return {
        "schema": "binding_affinity",
        "schema_version": "1.0.0",
        "source": {
            "name": "BindingDB",
            "subset": "BindingDB-curated articles",
            "url": URL,
            "release": RELEASE,
            "sha256": digest,
            "retrieved": date.today().isoformat(),
            "licence": "CC BY 3.0",
            "licence_statement_url": LICENCE_PAGE,
            "licence_basis": (
                "BindingDB states two licences for its contents: data imported from ChEMBL under "
                "CC BY-SA 3.0, and data curated by BindingDB staff under CC BY 3.0. Only the "
                "staff-curated subset is fetched. The ChEMBL-derived subset is a separate "
                "download and is never retrieved."),
            "attribution": "Data from BindingDB (https://www.bindingdb.org), CC BY 3.0.",
        },
        "coverage": {
            "rows_scanned": scanned,
            "components_with_values": len(records),
            "components_total": len(by_inchikey),
            "receptors_with_values": len({r for _, r in pairs}),
            "pairs": len(pairs),
        },
        "records": dict(sorted(records.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-download instead of using the cache")
    args = parser.parse_args()

    payload = build(fetch(args.refresh))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "binding_affinity.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    coverage = payload["coverage"]
    print(f"scanned {coverage['rows_scanned']} rows")
    print(f"matched {coverage['pairs']} ligand-receptor pairs")
    print(f"        {coverage['components_with_values']} of {coverage['components_total']} components")
    print(f"        {coverage['receptors_with_values']} receptors")
    print(f"source sha256 {payload['source']['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
