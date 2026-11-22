# tools/sizing: the S-013 and S-015 sizing harness

Measures the per-paper size factors that [L2 infrastructure §2.4](../../docs/vmodel/L2-infrastructure.md) used to model (S-013, issue #83; the sealed products, figures and snapshot generations, S-015, issue #89). It is a measurement harness, not hub product code: no `hub-*` crate, no adapter, it keeps nothing and its scratch is deleted after a run.

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

**Limits.** (S-013 measured; S-015 below adds the sealed products.) T1 layout/OCR and T2 to T4 outputs are modelled (GPU, #84); TEI is modelled (the OpenAlex content API is not used); patent XML and drawing bytes are not measured because the USPTO Open Data Portal refuses requests without `USPTO_ODP_API_KEY` (#85); works with only a landing page carry no text (#86). The BM25 ratio depends on the analyser (`en_stem`, nothing stored) and the chunk counts on the packing rule and the reference tokenizer.

## S-015: the sealed corpus as tessera blocks

`sizing tsra` re-fetches the scholarly-type works of the manifest (JATS from Europe PMC, else the PDF, as S-013) and writes `data/tsra.json` (aggregates only). Per work it extracts the tables of [document-model.md](../../docs/architecture/document-model.md) (`works`, `elements`, `chunks`, `figures`; from JATS `table_cells`, `inline_refs`, `bib`; PDF elements come from `pdftotext -bbox-layout`, with page and box), the kept OpenAlex fields (`works`, `authorships`, `citations`) and the figures, and encodes each table as one block of the whole sample: tessera `.tsra` (`tessera-py` from the pinned vig-os/tessera commit, built by its own flake), Parquet zstd level 3 (the reference) and raw Arrow bytes. The JATS-only tables are spread over the JATS works and counted for every paper with text (PDF works need T1, #84); the range is that of ten random 80 % subsets.

*Vectors:* synthetic unit vectors (a size depends on the entropy of the values, and embeddings barely compress), fp16 and int8 plus a 4-byte scale, 512 and 1,024 dimensions, as a Vortex `fixed_size_list` (`vortex-data` 0.93.0; tessera cannot write one, vig-os/tessera#768), a tessera array block and Parquet zstd. *Figures:* PDF route `pdfimages -list` then `-all` and `cjxl` (JPEG transcoded, rasters at distance 0); JATS route the graphic files of the article in the keyless PMC open-data bucket, encoded the same way; a figure is an image, not a mask, of at least 64 px a side; the blobs go into one Vortex binary column (tessera has none, vig-os/tessera#779). *Snapshots:* only the current OpenAlex release is in the bucket, so a generation's delta is the `updated_date=` partitions on or after the previous release (`core.snapshot_generation`).

```sh
rsync -a tools/sizing/ ksb:<dir>/ && ssh ksb 'ksb run --name s015 --cpu 24 --mem 64Gi --time 10h <dir>#sizing -- \
  tsra --out /job/out --scratch /data/hdd/scratch/s015 --workers 64'   # the job deletes its scratch
ssh ksb 'ksb wait s015 --timeout 600'      # repeat; then `ksb out s015 --path tsra.json > data/tsra.json`
python3 -m sizing.run recompute data/measurements.json --tsra data/tsra.json   # folds it in, recomputes every size
```

`--stage figures` re-runs only the figure stage and the snapshot listing (`figures.json`; `recompute --figures` folds it over the figures of `tsra.json`); `--records <file>` reads the manifest's works from a saved OpenAlex page set instead of the API (the free API budget is per IP and day). Figure files are the figure and table graphics of the article's own JATS (`core.pick_graphic_files`, one rendition each; the rest of the PMC folder is supplementary material, listed by bytes only and not fetched) and, for a PDF, each image object that is a figure once (`core.figure_images`).

`nix run <dir>#py -- script.py` runs a script in the same pinned environment; `vortex-data` is installed into `$VORTEX_DIR` at the first start. `core.py` is tested by `tools/tests`; `tsra.py` and `s015.py` by the run itself.
