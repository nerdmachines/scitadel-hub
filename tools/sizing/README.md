# tools/sizing: the S-013 sizing harness

Measures the per-paper size factors that [L2 infrastructure §2.4](../../docs/vmodel/L2-infrastructure.md) used to model (S-013, issue #83). It is a measurement harness, not hub product code: no `hub-*` crate, no adapter, it keeps nothing and its scratch is deleted after a run.

**What it does.** Draws about 10,000 works from OpenAlex (`filter=best_oa_location.license:cc-by|cc0|public-domain`, `sample=10000&seed=83`, `per_page=100`) and records the population count and its split by type (cases: the scholarly types `type:article|review|preprint|conference-paper`, the S-014 planning case and the basis `papers` in the output; the articles alone and all types, for comparison). Per work it follows the cascade's source preference: JATS from Europe PMC where the work has a PMCID, else `best_oa_location.pdf_url`. Text is the JATS body or `pdftotext` output (the CPU proxy of T1 text). It counts chunks of 350 tokens (300 and 400 as bounds) with the Qwen3-Embedding tokenizer, builds a tantivy BM25 index (positions, whole papers) and measures its bytes per text byte, sizes the kept metadata fields as JSON and zstd Parquet, and reads the bulk-snapshot sizes from the OpenAlex manifest and the published Crossref and DataCite sizes. Nothing is embedded: vector bytes are chunks × dimensions × dtype. Each per-paper factor gets n, mean, median, p90 and a 95 % bootstrap CI of the mean; `core.extrapolate` turns them and the population count into low (CI lower bound), central (mean) and high (CI upper bound) sizes.

**Run** on ksb (CPU batch; never on vm-dev or anvil's GPU). The directory is a flake:

```sh
rsync -a tools/sizing/ ksb:<dir>/ && ssh ksb 'ksb run --name sizing --cpu 24 --mem 64Gi --time 10h <dir>#sizing -- \
  run --out /job/out --scratch /data/hdd/scratch/sizing --workers 64'
ssh ksb 'ksb wait sizing --timeout 600'    # repeat; then `ksb out sizing --path measurements.json`
python3 -m sizing.run recompute data/measurements.json   # recompute the extrapolations offline
```

`--manifest data/manifest.json` re-runs on the committed works; a run resumes from `results.jsonl` in `--out`. Only `data/manifest.json` (seed, filter, date, work IDs, per-source counts) and `data/measurements.json` (aggregates) are committed. Tests: `python3 -m unittest discover tools/tests` (stdlib only, synthetic fixtures, no network).

**Etiquette.** `User-Agent: scitadel-hub-sizing/0.1 (+https://github.com/nerdmachines/scitadel-hub)`, no email address; at most 1 request per second per PDF host and 5 per second per API; `Retry-After` and `robots.txt` honoured. `OPENALEX_API_KEY` is read if set; without a key or on an exhausted budget the run stops with `BLOCKED: needs OpenAlex API key: <error>`.

**Limits.** T1 layout/OCR and T2 to T4 outputs are modelled (GPU, #84); TEI is modelled (the OpenAlex content API is not used); patent XML and drawing bytes are not measured because the USPTO Open Data Portal refuses requests without `USPTO_ODP_API_KEY` (#85); works with only a landing page carry no text (#86). The BM25 ratio depends on the analyser (`en_stem`, nothing stored) and the chunk counts on the packing rule and the reference tokenizer.
