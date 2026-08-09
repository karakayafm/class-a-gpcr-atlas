# Functional pathway evidence curation

`pathway_evidence.csv` contains source-linked tier-B functional assay evidence. Its initial 22 records are copied unchanged from the read-only aminergic GPCR reference project. They are evidence records, not structural transducer assignments.

To add a record, preserve the existing header and provide at least `receptor`, `canonical_ligand_id`, `ligand_name`, `pathway`, `result`, `evidence_tier`, `assay_or_evidence`, `source_url`, and `reference_id`. `evidence_tier` must be `B`; `source_url` must be an HTTP(S) literature link. Use `pdb_id` only when the evidence applies specifically to one deposition; leave it empty to apply the record to every atlas structure matching `receptor + canonical_ligand_id`.

Allowed source pathway names are `Gs`, `Gi`, `Gi/o`, `Gq/11`, `G12/13`, `beta_arrestin`, and `arrestin`. The loader normalizes `Gi` to `Gi/o` and `beta_arrestin` to `arrestin` without changing the curated CSV. A `negative` result remains visible evidence but never grants panel membership. Do not add inferred, approximate, or unsourced evidence to fill coverage gaps.

After editing, run `python3 pipeline/enrichment/build_pathway_evidence.py`. The command validates every CSV row, resolves its atlas matches, and rebuilds `data/intermediate/enrichment/pathway_evidence.jsonl` plus the single stage report. An unmatched record is retained in the CSV and reported; it is never silently reassigned to a different receptor or ligand.
