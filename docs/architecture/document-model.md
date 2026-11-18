# L3: document model

Full text stored as Arrow-shaped blocks, not as documents. Source: XADR-SCITADEL-008 §9 (document model). Binary figure bytes use the media-column contract of [the tessera boundary](tessera-boundary.md) ([DES-011](tessera-boundary.md)); keyed links use `KeyedRefs` ([DES-004](tessera-boundary.md)).

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). Every DES below is `proposed`. Model names are defaults of service definitions ([DES-015](tessera-boundary.md)), never named in code.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-036 | Blocks of a shard product and their keys | SYS-008, SYS-009 | DES-002, DES-004, DES-023 |
| DES-037 | Derived products, lossless figure storage and figure embeddings | SYS-008, SYS-032, SYS-065 | DES-011, DES-022, DES-036 |

## 1. Blocks (DES-036)

TEI, JATS, publisher HTML and PDF are **ingest sources** ([DES-013](tessera-boundary.md)), not storage. A shard holds these blocks, each sorted by `(work_id, ord)`:

| Block | Columns |
|---|---|
| `works` | work_id, DOI, licence class, source (`jats`, `html`, `tei`, `pdf`), extractor@version, per-work content hash, raw-input hashes and URLs, QC metrics ([DES-044](quality.md)), highest cascade tier ([DES-040](provenance.md)) |
| `elements` | work_id, ord, parent_ord, kind (heading, paragraph, equation, list, caption, …), text, page, bbox[4] |
| `inline_refs` | work_id, ord, span, target kind (citation, figure, table, formula), target id |
| `bib` | work_id, bib_id, parsed fields, DOI, `matched_work_id`, the source of citation edges |
| `table_cells` | work_id, table_id, row, col, text, `num: f64?`, unit |
| `figures` | work_id, fig_id, caption ord, bbox, blob ref |
| `chunks` | work_id, chunk_id, element span, 300 to 400 tokens (derived; the unit of the scorer's second pass) |

- **Linking.** Within a shard by key: sorting keeps one paper's rows together in every block, so `get` touches a few chunks per block. Declared keyed links (`bib.matched_work_id` → `works.work_id`) and the work_id → product index are `KeyedRefs`; across products by provenance ([DES-040](provenance.md)).
- **Compression comes from the layout:** sorted keys as runs and deltas, dictionaries for `kind` and section names, typed columns for numbers apart from text (`table_cells.num`, bbox, pages), embeddings as f16 or int8 plus scale.
- **Rendered views are not storage.** Typst, HTML and Markdown are generated on demand for readers and LLM context; storing them would make a compiler a dependency for reading our own data.
- **Size.** Per paper about 5 to 8 KB of text, a few KB of tables, 100 KB to 1 MB of lossless figures, about 10 KB of vectors *(estimates)*; figures dominate and the first measured shards replace these numbers.

## 2. Derived products, figures and embeddings (DES-037)

Next to each shard: one embeddings product per model (chunk and figure vectors, row-aligned with `chunks` and `figures`); a figure-blob product, so text scans never touch images; figure descriptions from the vision tier as a derived text column for BM25 and text embeddings, for the hot set only and generated lazily; and the work_id → shard index.

| Source image | Stored as | Why |
|---|---|---|
| Vector graphics | SVG in a string column | exact and small |
| Embedded JPEG | JPEG XL lossless transcode | smaller, and the original JPEG is reconstructed bit-exactly so its hash still verifies |
| Lossless raster (PNG, TIFF, patent drawings) | JPEG XL lossless | smaller than PNG, no generational loss |
| 16-bit or high bit depth | JPEG XL | WebP is 8-bit only |

- **Lossless only.** Nothing is re-encoded lossily for storage; WebP or AVIF thumbnails exist only as on-demand display views. JPEG XL decodes with `jxl-oxide` and encodes through `libjxl`; the figure bytes are `BinaryView` columns under the contract of [DES-011](tessera-boundary.md).
- **Figure and page-region embeddings** put text, images and page screenshots in one space so a text query finds a chart; Matryoshka truncation keeps the store small and its quality loss is checked on the golden set ([DES-043](quality.md)). Bulk embedding is a GPU job ([DES-022](adapters-and-pool.md), SYS-065).
- **Detach** hands out the structured document with figures as JPEG XL, never PDF bytes ([DES-051](client-app.md), SYS-032).

## 3. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-130 | DES-036 | A fixture JATS paper and a fixture patent through T0 into a shard, then `get` by ID, a cross-shard citation and a re-sort check | every block sorted by `(work_id, ord)`; `get` touches a few chunks per block (XADR-SCITADEL-008 §9), the count recorded; the cross-shard citation resolves through the work_id index; numbers sit in typed columns |
| TEST-131 | DES-037 | A fixture with an SVG, an embedded JPEG, a PNG, a TIFF and a 16-bit image stored and read back; an embeddings product aligned with `chunks` | each image decodes bit-exactly (the JPEG reconstructs to its original hash); no lossy encode in the write path; embedding rows align 1:1 with `chunks` and `figures` |
