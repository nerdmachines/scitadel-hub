# L3/L4: the tessera boundary

The Rust traits the hub owns at its storage, index and provenance boundary. For each one: a signature sketch, its invariants and provenance obligations, the tessera issue that will back it, the interim backend in use until then (with the evidence for whether tessera already provides it), what changes for the caller when the backend is swapped (always nothing) and its failure modes. Section 5 specifies the swap test. The adapters and the download pool are in [adapters and pool](adapters-and-pool.md); open points are in [open questions](../open-questions.md).

> **Source legend.** `XADR-SCITADEL-008` is the vig-os/scitadel decision record "scitadel-hub: a lab corpus server" (ADR 008, status Proposed, [pull request 317](https://github.com/vig-os/scitadel/pull/317)); `§N` is a section of it. `vig-os/tessera#N` issues are linked; `gerchowl/g-fleet#N` is a private repository and is written in code style. Tessera facts were read on 2026-11-18 from the `dev` branch of [vig-os/tessera](https://github.com/vig-os/tessera) (release `v0.1.0-alpha.5`); every "ships" or "does not ship" claim names its path there. Every identifier below is a node in the [trace graph](../traceability/README.md). Each design is `proposed`; signatures are sketches, not code.

**The owner's rule (2026-11-09).** Where tessera already provides a capability, the hub adopts it now and the interim backend *is* tessera. Where it does not, the hub builds the smallest correct thing behind a trait it owns and swaps to tessera the day the issue lands. Constraints on every interim: `.tsra` is the only product format; internal staging that never leaves the hub is allowed and is named as such; no graph database; no PDF bytes served (D-007); everything carries provenance (XADR-SCITADEL-008 §11).

## 1. Conventions shared by every trait (DES-001)

**Crates.** `hub-boundary` holds the traits and the shared types and depends on no backend. Backends live in `hub-backend-tessera` and `hub-backend-interim`. `hub-compose`, the composition root, is the **only** crate that names a backend type; it picks one per trait from configuration (`[backends] text_index = "tantivy-direct"`, and so on). Query service, orchestrator and adapters depend on `hub-boundary` alone. That is the mechanism behind "nothing changes for the caller": a swap is a configuration change plus a new arm in `hub-compose`, and TEST-094 fails the build if any other crate depends on a backend crate.

**Shape of a trait.**

```rust
pub trait BoundaryError: std::error::Error + Send + Sync + 'static {
    fn kind(&self) -> ErrorKind;
}
#[non_exhaustive]
pub enum ErrorKind {
    NotFound, Invalid, Unsupported,   // caller or capability problem
    Integrity,                        // hash, seal or digest mismatch: never retried
    StaleStamp,                       // an index does not cover the pinned generation
    ModelMismatch,                    // query and index come from different definitions
    Refused,                          // a policy gate: licence class, PDF bytes, opt-out
    Transient,                        // retry within the caller's budget
    Quota,                            // EDQUOT or a budget: pause, never delete
    Conflict,                         // lost a race (promotion, create-only key)
}
```

- Every trait is `Send + Sync + 'static` and declares `type Error: BoundaryError`. `hub-compose` wraps each backend in an adapter that maps its error to the hub's `HubError` by `kind()`, so callers hold `Arc<dyn Trait<Error = HubError>>` and branch on `ErrorKind` only. A backend's own error type never reaches a caller.
- Methods are `async` and return `Send` futures. The sketches show the call shape; for dynamic dispatch `hub-compose` erases associated types (a trait's `Writer` becomes a boxed `dyn ProductWriter`, by-value methods such as `finish(self)` take `Box<Self>`), and the choice of macro is an implementation detail.
- **Arrow at the boundary.** Data enters and leaves as `arrow::record_batch::RecordBatch` with an `arrow_schema::SchemaRef`, streamed as DataFusion `SendableRecordBatchStream`; tables are exposed as `Arc<dyn datafusion::catalog::TableProvider>`. No tessera type (`ColumnData`, `TableSpec`, `Reader`) appears in `hub-boundary`; the tessera backend converts at its edge.
- **Provenance is a parameter, not an afterthought.** Every write takes a `&ProvContext` (run id, step id, service-definition hash, input hashes). The type has no `Default` and no public constructor outside the run ledger (DES-014), so a write without provenance does not compile, and a backend refuses a context whose definition hash does not resolve (SYS-068).
- **Index stamps.** Every derived index carries

  ```rust
  pub struct IndexStamp {
      pub covers: Vec<Seal>,         // the base seal and every delta seal, sorted by sequence
      pub params_hash: Blake3,       // analyzer, IVF parameters or edge kinds; the embedding definition hash
      pub backend: BackendId,        // e.g. "tantivy-direct/0.1", "tessera/0.2"
      pub format_version: u32,
  }
  ```

  The query service pins one `GenerationRef` per query (DES-012) and serves an index only when `stamp.covers` equals that generation's seals; otherwise the index answers `StaleStamp` (SYS-018, SYS-021). The backend id is part of the stamp, so after a swap the new backend reports the old stamps as stale and the existing rebuild path runs: indexes are rebuildable from sealed products alone (SYS-021), which is what makes an index swap free for callers.
- **Stage portability.** No method takes a host, a bucket name or a model name. Locations are `ShardLocation`/`ObjectUrl` values built from configuration; models are named only by service definitions (SYS-039, SYS-069).

## 2. Tessera-backed traits

### 2.1 `ProductStore`: write, seal, open and verify `.tsra` products (DES-002)

```rust
pub trait ProductStore: Send + Sync + 'static {
    type Error: BoundaryError;
    type Writer: ProductWriter<Error = Self::Error>;
    async fn create(&self, spec: &ProductSpec, at: &StagingPath, prov: &ProvContext)
        -> Result<Self::Writer, Self::Error>;
    async fn open(&self, at: &ShardLocation) -> Result<ProductHandle, Self::Error>;
    async fn verify(&self, at: &ShardLocation, expect: Option<&Seal>) -> Result<VerifyReport, Self::Error>;
}
pub trait ProductWriter: Send {
    type Error: BoundaryError;
    async fn push(&mut self, block: &BlockName, batch: RecordBatch) -> Result<(), Self::Error>;
    async fn finish(self, prov: ProvBlocks) -> Result<SealedShard, Self::Error>; // path, seal, size, blake3
}
// ProductHandle: manifest(), blocks(), schema(&BlockName) -> SchemaRef
```

- **Invariants.** A sealed shard is immutable; its seal is tessera's manifest hash and its file blake3 is recorded in the ledger. `ProductSpec` declares every block's Arrow schema up front and `push` refuses a batch that differs. `finish` requires the provenance blocks of DES-009, so no product seals without them. Block names and schemas follow the document model of SYS-008; no block may hold PDF bytes (the media rule of DES-011).
- **Backs it:** [vig-os/tessera#778](https://github.com/vig-os/tessera/issues/778) (umbrella), with the encoding work of [#628](https://github.com/vig-os/tessera/issues/628).
- **Interim: tessera itself (ships).** `tessera-io/src/stream.rs` and `write.rs` (`StreamWriter`, `StreamWriter::push_table`, `open_table`, lanes sealed in order), `tessera-io/src/container.rs` (`pack_streaming_verified`, `Reader`, `verify_payloads_parallel`), `tessera-core/src/manifest.rs` (`Manifest::verify`, `seal_of`) and the schema contract check of `ProductSchema` (tessera PRs 846 and 861). The backend converts Arrow columns to tessera's `ColumnData`, which today carries integers, floats, booleans, UTF-8 and nullable wrappers; wide vectors and binary columns are refused at its edge and handled by DES-006 and DES-011 until [#768](https://github.com/vig-os/tessera/issues/768) and [#779](https://github.com/vig-os/tessera/issues/779) land. Until tessera's wave 1 the adapters stage normalised tables as Parquet in `staging/parquet/` and the product is sealed from there, as XADR-SCITADEL-008 §2 decides; that Parquet is **internal staging only**, never in a bucket and never served (DES-021, C-002).
- **On the swap:** none needed; later tessera releases are a version bump of the same backend.
- **Failure modes.** `Invalid` for a schema mismatch or an unsupported Arrow type; `Integrity` when `verify` finds a digest or seal mismatch; `Quota` on `EDQUOT` in `staging` (the run stops at its next write and resumes, SYS-061); a crash before `finish` leaves a partial file in `staging` that the next run sweeps.

### 2.2 `TableScan`: blocks as DataFusion tables (DES-003)

```rust
pub trait TableScan: Send + Sync + 'static {
    type Error: BoundaryError;
    /// One block of one sealed product, projected and pruned, streamed leaf by leaf.
    fn table(&self, product: &ProductHandle, block: &BlockName, opts: &ScanOptions)
        -> Result<Arc<dyn TableProvider>, Self::Error>;
    /// The same block across the products of a generation, without delta semantics.
    fn union(&self, g: &GenerationRef, block: &BlockName, opts: &ScanOptions)
        -> Result<Arc<dyn TableProvider>, Self::Error>;
}
// ScanOptions { verify: VerifyBlocks (default) | TrustSealed, batch_rows, max_leaves_in_flight }
```

- **Invariants.** Every scan reads only sealed bytes and verifies each block digest before use unless the handle was verified at open (`VerifyBlocks` is the default, as in tessera's decision record 0062). Memory is bounded by `max_leaves_in_flight` leaves, never the whole table. The scan exposes the provenance and licence columns of every block (SYS-028, SYS-052) so that the query service can attach them to each record; a projection that drops `prov_id` or `licence_class` is refused for any plan that returns records.
- **Backs it:** [vig-os/tessera#654](https://github.com/vig-os/tessera/issues/654) (sliced into tessera issues 666, 667 and 668: pushdown, zip, multi-product and object store).
- **Interim: hub-built (tessera does not ship it).** Tessera's `tessera sql` materialises into a DataFusion `MemTable` (`tessera-cli/src/sql.rs`), which is not bounded. The hub builds a streaming `TableProvider` over what does ship: `LogicalTableView` and `select_blocks_overlapping` (`tessera-io/src/multiblock.rs`) to choose leaves, `decode_projected` per leaf (`tessera-io/src/table.rs`, at most 2²² rows per leaf), and the int64 chunk statistics of `tessera-core/src/chunk_index.rs` for pruning; filters are reported to DataFusion as `Inexact` and re-applied above the scan. `get` reaches rows through the key index of DES-004 and decodes only the leaves that hold them; whether that meets SYS-025 and SYS-022 without pushdown is spike S-002.
- **On the swap:** nothing; `table` and `union` return a `TableProvider` either way, and the conformance suite compares results row for row.
- **Failure modes.** `Integrity` on a digest mismatch (the query fails; it never returns unverified rows); `NotFound` for an unknown block; `Transient` on an I/O error.

### 2.3 `KeyedRefs`: declared keys and references across shards (DES-004)

```rust
pub trait KeyedRefs: Send + Sync + 'static {
    type Error: BoundaryError;
    /// key -> (seal, block, row) for the pinned generation; at most 100 keys per call (SYS-025).
    async fn resolve(&self, g: &GenerationRef, block: &BlockName, keys: &ArrayRef)
        -> Result<RecordBatch, Self::Error>;
    async fn build(&self, g: &GenerationRef, prov: &ProvContext) -> Result<IndexStamp, Self::Error>;
    async fn dangling(&self, g: &GenerationRef) -> Result<DanglingReport, Self::Error>;
}
```

- **Invariants.** A key column is declared in `ProductSpec`, unique within a product and sorted; the writer checks both and refuses otherwise. References (an embedding row to its chunk, an edge endpoint to its work, a retraction flag to a DOI or PMID, SYS-010) name their target block and key. `resolve` answers only for the generation it is given, so a superseded row cannot come back (SYS-005). A sealed generation has 0 dangling references.
- **Backs it:** [vig-os/tessera#780](https://github.com/vig-os/tessera/issues/780) (`TableSpec.keys`, `references`, a key-to-product aux cache, `verify --references`).
- **Interim: hub-built (tessera does not ship it; `RowAlignment` is positional only).** The declaration is written into the product's manifest metadata under `hub.keys.v1`; the key index is a sorted key → (seal, leaf, row) file in `index/keys/<collection>/<stamp>/`, stamped like any index and rebuilt from the products.
- **On the swap:** nothing for callers. Products written before #780 carry the hub declaration; the tessera backend reads both, and the next compaction writes the native one.
- **Failure modes.** `Invalid` on a duplicate or unsorted key at write; `StaleStamp`; `Integrity` when a resolved row's key does not equal the requested key (a corrupt index; rebuilt, never served).

### 2.4 `DeltaStore`: keyed deltas, newest-wins reads and compaction (DES-005)

```rust
pub trait DeltaStore: Send + Sync + 'static {
    type Error: BoundaryError;
    /// Newest-wins over base and deltas: tombstones dropped, redirects followed.
    fn merged(&self, g: &GenerationRef, block: &BlockName, opts: &ScanOptions)
        -> Result<Arc<dyn TableProvider>, Self::Error>;
    async fn write_delta(&self, base: &Seal, seq: u64, ops: SendableRecordBatchStream, prov: &ProvContext)
        -> Result<SealedShard, Self::Error>;            // ops: key, op (upsert|delete|redirect), redirect_to, row
    async fn compact(&self, permit: BaseBuildPermit, g: &GenerationRef, prov: &ProvContext)
        -> Result<CandidateGeneration, Self::Error>;
}
```

- **Invariants.** Nothing is rewritten in place; a delta is a new sealed product naming its base and a strictly increasing sequence. A merged read returns 0 superseded or tombstoned rows (SYS-005). `compact` is deterministic (rows sorted by key, the same inputs give the same seal) and writes a **candidate**; only `GenerationCatalog::promote` makes it current (SYS-060).
- **The pin rule (SYS-073).** `compact` takes a `BaseBuildPermit`, a type with no public constructor that only `GenerationCatalog::reserve_base_slot` (DES-012) returns, and only while at most three bases would occupy the tier. A QC retry and a re-derive that produces a base need the same permit. The trait therefore cannot start a fourth base; the wait and its expected end are recorded in the run ledger.
- **Backs it:** [vig-os/tessera#781](https://github.com/vig-os/tessera/issues/781) (`Role::Delta { base, seq }`, sealed `op` column, `tessera compact`), which depends on #780; sizes improve with [#628](https://github.com/vig-os/tessera/issues/628).
- **Interim: hub-built (tessera does not ship it; no upsert, tombstone or compaction code exists).** Delta products use the column layout #781 proposes (`op` as UTF-8, `redirect_to` as the target key) with base seal and sequence in manifest metadata. `merged` is a DataFusion plan over `TableScan::union`: rank rows by key and descending sequence, keep the first, drop `delete`, resolve `redirect` chains to their final key (a cycle is `Integrity`). `compact` streams that plan into `ProductStore`.
- **On the swap:** nothing for callers; old deltas stay readable by both backends because the column layout already matches the proposal.
- **Failure modes.** `Conflict` for a duplicate sequence; `Integrity` for a redirect cycle or a delta whose base seal is not in the generation; `Quota` mid-compaction (the candidate is abandoned, `current` is untouched, SYS-005).

### 2.5 `VectorIndex`: exact and approximate nearest neighbours (DES-006)

```rust
pub trait VectorIndex: Send + Sync + 'static {
    type Error: BoundaryError;
    async fn build(&self, g: &GenerationRef, source: &EmbeddingSource, params: &AnnParams, prov: &ProvContext)
        -> Result<IndexStamp, Self::Error>;
    /// `q` can only be made by the QueryEmbedder (DES-016) and carries its definition hash.
    async fn search(&self, stamp: &IndexStamp, q: &QueryVector, k: usize, filter: Option<&RowFilter>)
        -> Result<RecordBatch, Self::Error>;             // key, score, seal, prov_id
    fn capabilities(&self, stamp: &IndexStamp) -> VectorCapabilities; // exact | ivf-flat | hnsw, model fields
}
```

- **Invariants.** The embeddings of an index generation come from exactly one embedding definition; its hash is in `params_hash`. `search` refuses a `QueryVector` whose definition does not match with `ModelMismatch` (SYS-071): no mixed-model results, no fallback model. The method chosen is reported in `capabilities` (SYS-019). Recall against exact scan is a pass criterion of the suite, not a hope.
- **Backs it:** [vig-os/tessera#769](https://github.com/vig-os/tessera/issues/769) (tier 0 exact scan through a `vec_distance` UDF, tier 1 IVF-flat as a sealed centroids product, tier 2 HNSW as an aux cache), on top of [#768](https://github.com/vig-os/tessera/issues/768) (declared `vector{dim, dtype}` columns).
- **Interim: hub-built (tessera ships neither; `tessera-ingest/src/arrow_table.rs` refuses `FixedSizeList` wider than 8 and `ColumnData` has no binary type).**
  - *Storage, inside `.tsra`:* the embeddings product holds a table block (key, chunk ordinal, definition hash, `prov_id`) and the vectors as one tessera blob block per leaf (`tessera-core/src/block/blob.rs`), row-aligned little-endian fp16, whose digest tessera verifies (a deviation from the "native fixed-size lists" of L2 infrastructure section 5 until #768, C-001). The reader exposes them as Arrow `FixedSizeListArray` through `EmbeddingSource`. Nothing leaves `.tsra`.
  - *Exact scan:* in-crate SIMD over those arrays, also the reference for recall.
  - *IVF-flat:* one sealed `.tsra` file per index generation under `index/ann/<collection>/<stamp>/`: the centroids, and per-list postings (list id as an int64 column, so that tessera's shipped int64 chunk statistics prune the lists to probe, then key, seal, leaf and row). It holds **no copy of the vectors**; a probe reads them in place from the hot embeddings products. It is Vortex-encoded as SYS-019 asks, local and never in a bucket as SYS-012 asks, rebuildable, and small (about 16 bytes per vector), so the 0.2 B index estimate of L2 infrastructure section 2.4 holds. That section's premise that the lists live in the products, which would put index bytes on S3, is C-005. The HNSW cache is not built unless S-001 shows IVF-flat cannot meet the budget.
- **On the swap:** nothing for callers. Embedding products are re-sealed with native vector columns by an ordinary run (a new generation through promotion), and the IVF file is rebuilt; old stamps report `StaleStamp` until then.
- **Failure modes.** `ModelMismatch`; `StaleStamp`; `Invalid` for a dimension mismatch; `Transient` on I/O. The query service answers a failed or late vector leg BM25-only and flags it (SYS-071).

### 2.6 `TextIndex`: BM25 (DES-007)

```rust
pub trait TextIndex: Send + Sync + 'static {
    type Error: BoundaryError;
    async fn build(&self, g: &GenerationRef, block: &BlockName, column: &str, analyzer: &AnalyzerConfig,
                   prov: &ProvContext) -> Result<IndexStamp, Self::Error>;
    async fn refresh(&self, stamp: &IndexStamp, delta: &Seal, prov: &ProvContext) -> Result<IndexStamp, Self::Error>;
    async fn search(&self, stamp: &IndexStamp, query: &str, k: usize, filter: Option<&RowFilter>)
        -> Result<RecordBatch, Self::Error>;             // key, score, seal, prov_id, snippet offsets
    /// Registers `bm25(block, column, query, k)` as a DataFusion table function.
    fn register(&self, ctx: &SessionContext, stamp: &IndexStamp) -> Result<(), Self::Error>;
}
```

- **Invariants.** The stamp's `params_hash` is the analyzer configuration hash, so a changed analyzer is a new index, never a silent mix. `refresh` makes a delta searchable within 1 h of its seal *(estimate)* (SYS-021) by adding a segment for the delta and masking superseded keys; a full rebuild is the fallback. Results compose with filters through the table function (SYS-018).
- **Backs it:** [vig-os/tessera#775](https://github.com/vig-os/tessera/issues/775) (declared `text_index{column, analyzer}`, tantivy as an aux cache stamped `built_from`, the `bm25` table function).
- **Interim: hub-built, tantivy directly (tessera does not ship text indexing).** One tantivy index per stamp under `index/bm25/<collection>/<stamp>/`, on local NVMe and never over S3 (SYS-012), stamp in the same `built_from` shape #775 proposes. Snippets are cut from the product's text column, not stored twice.
- **On the swap:** nothing for callers; the tessera backend rebuilds from the products, the old index is stale by backend id and is removed by the index sweep.
- **Failure modes.** `StaleStamp`; `Invalid` for a query the analyzer cannot parse (reported, never widened); `Integrity` when a hit's key does not resolve in the pinned generation.

### 2.7 `GraphIndex`: typed edge tables and adjacency (DES-008)

```rust
pub trait GraphIndex: Send + Sync + 'static {
    type Error: BoundaryError;
    async fn build(&self, g: &GenerationRef, kinds: &EdgeKindSet, prov: &ProvContext) -> Result<IndexStamp, Self::Error>;
    /// Depth 1 or 2 (SYS-020), by edge kind and direction.
    async fn neighbours(&self, stamp: &IndexStamp, seeds: &ArrayRef, kinds: &EdgeKindSet, depth: u8, dir: Direction)
        -> Result<SendableRecordBatchStream, Self::Error>; // seed, node, kind, depth, via, edge seal, prov_id, licence_class
}
```

- **Invariants.** Edges are product rows, not index state: tables with columns `src`, `dst`, `kind` (and an optional `weight`) in the convention #776 proposes, for work cites work, patent cites patent, patent cites paper and has-CPC (SYS-020). Endpoints are keys (DES-004). Every returned edge carries the seal, `prov_id` and licence class of its edge row, as every record does (SYS-028). The adjacency is a derived cache. **No graph database** (XADR-SCITADEL-008 §4).
- **Backs it:** [vig-os/tessera#776](https://github.com/vig-os/tessera/issues/776) (edge convention, CSR and reverse CSR as an aux cache, `neighbours` table function).
- **Interim: hub-built (tessera does not ship it).** A forward and a reverse CSR per edge kind, built from the edge tables: a node dictionary (key → ordinal) plus `UInt64` offsets and `UInt32` targets as Arrow arrays, persisted in `index/graph/<collection>/<stamp>/` as Arrow IPC files. That file format is an **internal cache that never leaves the hub**: rebuildable, never a product, never served.
- **On the swap:** nothing for callers; the edge tables already follow #776, so only the cache is rebuilt.
- **Failure modes.** `StaleStamp`; `Invalid` for a depth above 2 or an unknown kind; `Integrity` for an endpoint that does not resolve.

### 2.8 `ProvenanceSink`: product and row provenance (DES-009)

```rust
pub trait ProvenanceSink: Send + Sync + 'static {
    type Error: BoundaryError;
    fn begin(&self, ctx: &ProvContext, step: &PipelineStep) -> Result<ProvWriter, Self::Error>;
    async fn explain(&self, g: &GenerationRef, key: &ScalarKey) -> Result<ProvTrace, Self::Error>;
    /// SYS-069: every row produced by one definition, set-equal to the ledger's answer.
    async fn select_by_definition(&self, g: &GenerationRef, def: &DefinitionHash)
        -> Result<SendableRecordBatchStream, Self::Error>;
}
// ProvWriter::row(&mut self, RowProv) -> ProvId; ProvWriter::external(ExternalArtefact) -> ArtefactRef;
// ProvWriter::finish(self) -> ProvBlocks   (consumed by ProductWriter::finish)
// PipelineStep { tool, version, config_digest, model { id, revision, weights_blake3 }, definition_hash,
//                inputs: [{ role, blake3 }], compute { host, gpu_job_id }, verdicts, started, ended }
// RowProv { source, extractor, tier_reached, definition_hash, artefact: Option<ArtefactRef>, licence_class }
// ExternalArtefact { blake3, size, media_type, urls, fetched_at, holding: Held | Cold | Discarded }
```

- **Invariants.** Every product records tool, version, configuration, model weights hash, input hashes, GPU job and host and the cascade verdicts (SYS-009). Every row carries a `prov_id` whose variant names its source, extractor, highest tier, licence class and definition hash (SYS-068, SYS-052); raw inputs are referenced by blake3 and URL and are never inside the product. 100 % of served rows resolve to a seal and a raw-input hash (OUT-012). The column has no default value: a block without `prov_id` does not seal.
- **Backs it:** [vig-os/tessera#782](https://github.com/vig-os/tessera/issues/782) (typed `pipeline.steps[]`, per-row `prov_id` into a provenance-variants table, `ExternalArtefact`, `tessera provenance --row`).
- **Interim: tessera for the part that ships, the hub for the rest (partial).** Shipped (`tessera-core/src/provenance.rs`): `Source { role, reference, content_hash }` for every input, `Producer` for the tool, `Generation.config` and `verify_chain`. Not shipped: typed steps, per-row provenance and external artefacts. The hub writes the steps into `Generation.config` under the schema `hub.pipeline.v1` with the field names #782 proposes, external inputs as `Source` entries whose `reference` is the URL and whose `content_hash` is the blake3, and a `provenance` table block plus a `prov_id` column in every data block.
- **On the swap:** nothing for callers. The tessera backend reads `hub.pipeline.v1` as a legacy encoding and writes the typed slot for new products.
- **Failure modes.** `Invalid` for a row without a variant or a step without a definition hash; `NotFound` when a definition hash does not resolve (the write is refused, SYS-068); `Integrity` when an input's recorded hash differs from the ledger's.

### 2.9 `RemoteRead`: products in object storage (DES-010)

```rust
pub trait RemoteRead: Send + Sync + 'static {
    type Error: BoundaryError;
    async fn open(&self, url: &ObjectUrl) -> Result<ProductHandle, Self::Error>;
    /// SYS-059 read-back and SYS-047 restore: every digest checked against the expected seal.
    async fn verify(&self, url: &ObjectUrl, expect: &Seal) -> Result<VerifyReport, Self::Error>;
}
```

- **Invariants.** Used for the canonical copy in `scitadel-hub-keep` and later the warm tier: the read-back after a write, reconciliation at start, restore and rebuilding indexes when the hot copy is missing. **Never for serving index reads**, which are local (SYS-012). Credentials are the reading role's, from the hub's secrets file (SYS-040, SYS-041).
- **Backs it:** [vig-os/tessera#777](https://github.com/vig-os/tessera/issues/777) (remote open, verify and projection of a `.tsra` over HTTP or S3).
- **Interim: tessera itself for opening (ships), the hub for remote verify.** `tessera-io/src/cloud.rs` (`open_url`, `ObjectStoreReader`, feature `cloud`) opens a `.tsra` over S3 or HTTPS by range. What #777 adds, a ranged remote verify, is not there; until it is, `verify` streams the whole object once and checks it with `verify_payloads` and the file blake3, which is what the read-back of SYS-059 needs anyway.
- **On the swap:** nothing for callers; `verify` gets cheaper.
- **Failure modes.** `Transient` for a network error (retried within the caller's budget); `Integrity` for a mismatch (never retried; the shard is not published or not restored); `NotFound`.

### 2.10 `MediaColumns`: figures and drawings (DES-011)

```rust
pub trait MediaColumns: Send + Sync + 'static {
    type Error: BoundaryError;
    fn put(&self, w: &mut dyn ProductWriter<Error = Self::Error>, m: MediaValue) -> Result<MediaRef, Self::Error>;
    async fn get(&self, p: &ProductHandle, r: &MediaRef) -> Result<MediaBytes, Self::Error>; // bytes, media type, blake3
}
// MediaValue { media_type: Png | JpegXlLossless | Svg, width, height, bytes, source_blake3 }
```

- **Invariants.** Figures are stored lossless only and decode to the pixels (or SVG) of the source (SYS-008). The media-type set is closed: `application/pdf` and any unlisted type are `Refused`, so no product can hold PDF bytes and no call can serve them (D-007, SYS-032). Each value carries its blake3 and the licence class of its work.
- **Backs it:** [vig-os/tessera#779](https://github.com/vig-os/tessera/issues/779) (declared `media{media_type}` columns over `VarBinView`, SVG over UTF-8, per-value size cap).
- **Interim: hub-built on a shipped primitive (tessera has no binary column; `ColumnData` lacks `Binary` and ingest refuses binary Arrow types).** Each value is a tessera blob block `media/<blake3>` in the same shard, and a `figures` table block carries key, media type, width, height, blob name and blake3. SVG is stored as UTF-8 in that table, as #779 proposes.
- **On the swap:** nothing for callers; products are re-sealed with native media columns by the next compaction.
- **Failure modes.** `Refused` for a forbidden type; `Invalid` for a value above the size cap or a failed lossless round trip; `Integrity` for a blob digest mismatch.

## 3. The tessera map at a glance

| Trait | DES | Tessera issue | Interim backend | Tessera provides it today? |
|---|---|---|---|---|
| `ProductStore` | DES-002 | #778, #628 | tessera `.tsra` writer, reader, verify | **yes** |
| `TableScan` | DES-003 | #654 | hub `TableProvider` over tessera leaves | no (`MemTable` only) |
| `KeyedRefs` | DES-004 | #780 | hub declaration and key index | no |
| `DeltaStore` | DES-005 | #781 | hub delta layout and DataFusion merge | no |
| `VectorIndex` | DES-006 | #769, #768 | exact scan and IVF-flat over vectors in blob blocks | no |
| `TextIndex` | DES-007 | #775 | tantivy directly | no |
| `GraphIndex` | DES-008 | #776 | Arrow CSR cache over #776-shaped edge tables | no |
| `ProvenanceSink` | DES-009 | #782 | tessera `Source`, `Producer`, `Generation.config` plus hub row provenance | **partly** |
| `RemoteRead` | DES-010 | #777 | tessera `open_url`; hub full-read verify | **partly** |
| `MediaColumns` | DES-011 | #779 | tessera blob blocks plus a `figures` table | no (blob blocks only) |

All twelve tessera issues were open on 2026-11-18; none of [#778](https://github.com/vig-os/tessera/issues/778)'s waves has merged.

## 4. Hub-owned boundaries that tessera does not back

Same conventions as section 1, no tessera issue behind them: these are the hub's lifecycle, ledger and configuration. Each still has two backends, so the swap rule and the suite of section 5 apply.

### 4.1 `GenerationCatalog`: collections, `current` and canonical-first writes (DES-012)

```rust
pub trait GenerationCatalog: Send + Sync + 'static {
    type Error: BoundaryError;
    /// SYS-059: keep first (create-only, read back, blake3), then hot (temporary name, verify, rename).
    async fn publish_shard(&self, c: &CollectionId, g: &GenerationId, s: &SealedShard) -> Result<PublishedShard, Self::Error>;
    async fn current(&self, c: &CollectionId) -> Result<GenerationRef, Self::Error>;
    async fn generations(&self, c: &CollectionId) -> Result<Vec<GenerationInfo>, Self::Error>;
    /// SYS-060: a passing QC record; one atomic switch, keep first, hot by rename.
    async fn promote(&self, c: &CollectionId, g: &GenerationId, qc: &QcPass) -> Result<GenerationRef, Self::Error>;
    async fn rollback(&self, c: &CollectionId, to: &GenerationId, run: &RunId) -> Result<GenerationRef, Self::Error>;
    /// SYS-073: Granted(BaseBuildPermit) or Wait { until, reason }.
    async fn reserve_base_slot(&self, c: &CollectionId, run: &RunId, now: Timestamp) -> Result<SlotDecision, Self::Error>;
    async fn reconcile(&self) -> Result<ReconcileReport, Self::Error>; // keep wins
}
```

- **Invariants.** The layout `base/<release>/`, `delta/<date>.tsra`, `current` (SYS-002). `publish_shard` never moves `current`. A reader resolves `current` once per query and pins that `GenerationRef`, so it sees the old or the new generation, never a mix. `QcPass` is constructible only by the QC gate. `reserve_base_slot` counts the bases on the tier, counting a retired base as the previous one while a snapshot pins it, computes the pin's expiry from the snapshot schedule in configuration (L2 infrastructure section 2.4), and returns `Wait` while the count would exceed three; the orchestrator records the wait and its expected end in the ledger and raises an alert if the wait exceeds the longest snapshot retention. Retention deletes are **not** a method here: they belong to the retention role (SYS-017), a separate credential.
- **Backend:** S3 keys in `scitadel-hub-keep` written by the ingest role (or the newest-wins sequence of pointer objects if the gateway has no per-key rule, L2 infrastructure section 4), the hot pointer `products/<collection>/current` replaced by `rename(2)`, and collection manifests through tessera's shipped `CollectionBuilder` (`tessera-core/src/collection.rs`). **Second backend:** in memory over a temporary directory, for the suite.
- **Failure modes.** `Integrity` on a read-back mismatch (not published; the keep object stays unreferenced and is swept); `Conflict` when two promotions race (one wins, the other is refused and logged); `Wait` is a result, not an error.

### 4.2 `ArtefactStore`: the content-addressed raw and intermediate store (DES-013)

```rust
pub trait ArtefactStore: Send + Sync + 'static {
    type Error: BoundaryError;
    /// Create-only by blake3; read back and verified before Ok.
    async fn put(&self, file: &StagedFile, meta: &ArtefactMeta, ctx: &ProvContext) -> Result<ArtefactRef, Self::Error>;
    async fn put_intermediate(&self, input: &Blake3, step: &PipelineStep, file: &StagedFile, ctx: &ProvContext)
        -> Result<ArtefactRef, Self::Error>;            // keyed by input hash, tool, model, version, definition hash
    async fn get(&self, r: &ArtefactRef) -> Result<VerifiedReader, Self::Error>;
    async fn head(&self, h: &Blake3) -> Result<Option<ArtefactMeta>, Self::Error>;
    /// The only removal: a re-fetchable open-access PDF with recorded hash and URL, audited.
    async fn drop_refetchable(&self, h: &Blake3, audit: &OperatorAudit) -> Result<(), Self::Error>;
}
```

- **Invariants.** Keys `cas/<first two hex>/<blake3>` and `inter/<input blake3>/<tier>/<definition hash>/…` in `scitadel-hub-keep` (SYS-014), then on the warm tier by configuration (SYS-015). Nothing is deleted automatically; `drop_refetchable` refuses every other class (SYS-014). A re-run of a tier writes new intermediates beside the old ones (SYS-066). `get` serves the hub's own processes (cascade, renders of SYS-064); no protocol call returns raw bytes, and PDFs are never served (D-007). `put` returns `Quota` at the stage-0 raw budget, which pauses ingest (L2 infrastructure section 2.4), and the ledger's backup-age check gates raw-writing runs (SYS-072).
- **Backend:** the S3 gateway through the `object_store` crate. **Second backend:** a local directory with the same key scheme.
- **Failure modes.** `Integrity` (read-back or re-fetch mismatch); `Quota`; `Refused` for a drop outside the allowed class; `Conflict` is impossible by construction (same key, same bytes) and is treated as success after a hash compare.

### 4.3 `RunLedger`: runs, steps, queue and spend (DES-014)

```rust
pub trait RunLedger: Send + Sync + 'static {
    type Error: BoundaryError;
    async fn open_run(&self, kind: RunKind, pins: &InputPins, defs: &[DefinitionHash]) -> Result<RunId, Self::Error>;
    async fn step_started(&self, run: &RunId, step: &StepKey) -> Result<ProvContext, Self::Error>;
    async fn step_completed(&self, run: &RunId, step: &StepKey, outputs: &[OutputHash]) -> Result<(), Self::Error>;
    async fn resume_point(&self, run: &RunId) -> Result<ResumePlan, Self::Error>;
    async fn spend(&self, run: &RunId, step: &StepKey, s: &Spend) -> Result<(), Self::Error>;   // idempotent per step
    async fn enqueue(&self, item: &QueueItem) -> Result<(), Self::Error>;
    async fn record_wait(&self, run: &RunId, until: Timestamp, reason: &WaitReason) -> Result<(), Self::Error>;
    async fn gpu_submitted(&self, run: &RunId, job: &GpuJobRecord) -> Result<(), Self::Error>;
    async fn gpu_job_ended(&self, job: &GpuJobId, hashes: &[FileHash]) -> Result<(), Self::Error>; // hub-computed
}
```

- **Invariants.** A run record exists before step 1, with every input pinned by version or snapshot date and hash and every definition hash; an unpinned input refuses `open_run` (SYS-057). `step_started` is the only issuer of `ProvContext`. `resume_point` skips completed steps whose outputs still verify (SYS-061); `spend` is keyed by step, so a resume never double-counts credits or budget. Queued T3 and T4 work lives here, not in a bucket (SYS-006). The GPU acceptance order of SYS-062 reads `gpu_submitted` and `gpu_job_ended` (DES-022).
- **Backend:** SQLite with a write-ahead log on `state` (`+C`), dumped nightly to `keep`. **Second backend:** in-memory SQLite, for the suite and the crash-injection tests.
- **Failure modes.** `Invalid` for an unpinned input; `Conflict` for a step started twice concurrently; `Integrity` when a completed step's outputs no longer verify (the step is redone, SYS-061).

### 4.4 `ServiceRegistry`: versioned, content-hashed definitions (DES-015)

```rust
pub trait ServiceRegistry: Send + Sync + 'static {
    type Error: BoundaryError;
    fn validate(&self, d: &Definition) -> Result<DefinitionHash, Self::Error>;
    async fn active(&self, kind: &JobKind) -> Result<ResolvedDefinition, Self::Error>;
    async fn resolve(&self, h: &DefinitionHash) -> Result<ResolvedDefinition, Self::Error>;
    /// The query-embedding definition whose model fields equal those of an index generation (SYS-071).
    async fn query_embedder_for(&self, e: &EmbeddingSpec) -> Result<Option<ResolvedDefinition>, Self::Error>;
}
// Definition { kind, executor { gpu_submit | cpu_pool | remote_api, vram, max_runtime, priority, chunk },
//   model { id, revision, quantization, weights_blake3, dimensions, truncation }, runtime { name, version },
//   budget_cap, escalation_target, licence_classes }
```

- **Invariants.** A definition is configuration, canonicalised and hashed with blake3; a change is a new version; every version is stored by hash in `keep` and stays resolvable (SYS-067). `validate` refuses the cases of SYS-067: incomplete, a `gpu_submit` executor without VRAM or low priority, T3 or T4 without a budget cap, T4 with a class outside CC-BY, CC0 and public domain, and an escalation cycle. Moving a tier to another executor is a new definition and no code change; **no code names a host or a model** (SYS-069, TEST-089). A sage executor exists only if a definition names it (SYS-070). Weights come through the signed manifest and must equal `weights_blake3` (SYS-056).
- **Backend:** TOML files in the hub's configuration, loaded at start, mirrored by hash to `keep`. **Second backend:** an in-memory registry.
- **Failure modes.** `Invalid` with the failing rule; `NotFound` for an unknown hash (the step or row is refused, SYS-068).

### 4.5 `QueryEmbedder`: hub-side query vectors (DES-016)

```rust
pub trait QueryEmbedder: Send + Sync + 'static {
    type Error: BoundaryError;
    /// Embeds with the definition that matches `target`, or refuses. Never another model.
    async fn embed(&self, text: &str, target: &IndexStamp, deadline: Instant) -> Result<QueryVector, Self::Error>;
}
// QueryVector { values: Float32Array, definition: DefinitionHash, spec: EmbeddingSpec }  (no public constructor)
```

- **Invariants.** The query embedder is a **registry consumer** (D-009, SYS-071): it reads the embedding spec of the index generation from `target`, asks `ServiceRegistry::query_embedder_for` for the definition with equal model id, revision, quantization, weights hash, dimensions and truncation, and loads that model through the definition's runtime. No match is `ModelMismatch` and the vector leg is refused. The definition hash travels in `QueryVector` into the response's provenance and `capabilities` (SYS-027). Clients never send vectors; the protocol rejects them before this trait is reached. It runs on CPU in `vm-hub`; a GPU executor is possible only by a definition that names one outside the serving microVM, after the benchmark and with the owner's approval (SYS-024). Missing the deadline is `Transient`, and the query service answers BM25-only, flagged (SYS-071).
- **Backends:** the in-process CPU runtime the active definition names; a GPU-slot executor through the same definition mechanism; a deterministic fake for the suite. Which model is the default is decided by the benchmark of TEST-091 on anvil's RTX 5090 and the serving CPU, together with SYS-050, not here.
- **Failure modes.** `ModelMismatch`; `Transient` (timeout); `Integrity` when the loaded weights do not hash to the definition's.

## 5. The swap test (DES-017)

One crate, `hub-boundary-conformance`, holds one generic suite per trait: `pub async fn run<T: TextIndex>(make: impl Fn() -> T, fixtures: &Fixtures) -> SuiteReport`. Every backend crate calls the suite of each trait it implements from its own integration tests, and CI runs every backend on every pull request. The fixtures are the CC0 fixture corpus (a base, three deltas with an update, a merge and a delete, figures in each media type, edges of each kind, embeddings from two definitions) plus seeded corruptions.

**Pass criteria for every suite.** All named cases pass; results are compared with the reference backend (the interim one until tessera lands, then each other) **row for row** for deterministic traits and by **recall@10 ≥ 0.99 against exact scan** for approximate vector search; the error *kind* of every negative case equals the expected one.

| Suite | Named cases (each is one test function) |
|---|---|
| `ProductStore` | `seal_roundtrip_is_bit_exact`, `seal_is_deterministic`, `push_refuses_schema_drift`, `finish_refuses_missing_provenance`, `verify_detects_flipped_byte`, `partial_write_never_opens` |
| `TableScan` | `projection_and_filter_match_reference`, `pruning_skips_leaves`, `memory_bounded_by_leaves_in_flight`, `corrupt_block_fails_query`, `prov_and_licence_columns_always_present` |
| `KeyedRefs` | `resolve_hundred_keys`, `duplicate_key_refused`, `superseded_key_not_resolved`, `dangling_reference_reported` |
| `DeltaStore` | `newest_wins`, `tombstone_hides_row`, `redirect_chain_followed`, `redirect_cycle_is_integrity`, `compaction_is_deterministic`, `compact_without_permit_does_not_compile` (a trybuild case), `kill_mid_compaction_leaves_current` |
| `VectorIndex` | `exact_matches_brute_force`, `ann_recall_at_10`, `mixed_definition_refused`, `filter_respected`, `capabilities_report_method` |
| `TextIndex` | `bm25_scores_match_reference`, `analyzer_change_is_new_stamp`, `delta_refresh_masks_superseded`, `stale_stamp_refused` |
| `GraphIndex` | `depth_one_and_two_by_kind`, `reverse_direction`, `unknown_kind_invalid`, `stale_stamp_refused` |
| `ProvenanceSink` | `every_row_has_prov_id`, `explain_reaches_raw_hash_and_url`, `select_by_definition_equals_ledger`, `unresolvable_definition_refused` |
| `RemoteRead` | `open_matches_local`, `verify_detects_flipped_byte`, `transient_error_classified` |
| `MediaColumns` | `lossless_roundtrip_per_type`, `pdf_refused`, `unknown_type_refused`, `oversize_refused` |
| `GenerationCatalog` | `keep_before_hot`, `publish_never_moves_current`, `promote_needs_qc`, `no_mixed_generation_during_switch`, `fourth_base_waits`, `reconcile_keep_wins` |
| `ArtefactStore` | `create_only_by_hash`, `intermediate_beside_old`, `drop_refuses_non_refetchable`, `quota_pauses` |
| `RunLedger` | `unpinned_input_refused`, `resume_skips_verified_steps`, `spend_not_double_counted`, `queue_survives_restart` |
| `ServiceRegistry` | the nine refusal cases of SYS-067, `hash_is_canonical`, `every_version_resolvable` |
| `QueryEmbedder` | `matching_definition_used`, `mismatch_refused`, `timeout_is_transient`, `hash_in_provenance` |

**The suite is itself tested.** For each trait a set of deliberately broken backends (one per invariant: a scan that drops `prov_id`, a merge that keeps tombstones, an index that ignores the stamp) must each fail at least one named case; a mutant that passes means a missing case (TEST-110). Together with the dependency check of section 1 (TEST-094), that is the swap test: a backend that passes its suite can replace another with no caller change, and nothing outside `hub-compose` can tell the difference.

**Unit-level expectations (L4).** Beside the suites: the Arrow-to-`ColumnData` conversion table (every supported type, every refused type); the redirect resolver on chains and cycles; the stamp equality rule; the slot arithmetic of `reserve_base_slot` with an injected clock; canonical definition hashing on reordered TOML; the fp16 blob layout against a reference encoder.

## 6. Verification

Every design here is verified by one integration test; all run in CI on fixtures unless the row says otherwise.

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-094 | DES-001 | Dependency check over the workspace (`cargo metadata`): only `hub-compose` depends on a backend crate; `ErrorKind` mapping test per backend | 0 other dependents; 100 % of backend errors mapped to a kind |
| TEST-095 | DES-002 | `ProductStore` suite against the tessera backend | all cases pass; bit-exact round trip |
| TEST-096 | DES-003 | `TableScan` suite, interim backend versus a `MemTable` reference | row-for-row equal; peak memory ≤ the leaf bound |
| TEST-097 | DES-004 | `KeyedRefs` suite | all cases pass |
| TEST-098 | DES-005 | `DeltaStore` suite, including a kill at every compaction step | 0 superseded rows; `current` unchanged after every kill |
| TEST-099 | DES-006 | `VectorIndex` suite; ksb timing on the SYS-063 slice | recall@10 ≥ 0.99 on fixtures; recall ≥ 0.95 and p95 ≤ 20 ms *(estimate)* on the slice |
| TEST-100 | DES-007 | `TextIndex` suite; ksb timing on the slice | all cases pass; p95 ≤ 50 ms *(estimate)* |
| TEST-101 | DES-008 | `GraphIndex` suite; ksb timing on the slice | all cases pass; depth-2 p95 ≤ 100 ms *(estimate)* |
| TEST-102 | DES-009 | `ProvenanceSink` suite; a 1,000-row sample traced to seal, raw hash and URL | 100 % resolved; selection set-equal to the ledger |
| TEST-103 | DES-010 | `RemoteRead` suite against a local S3 gateway in CI | all cases pass |
| TEST-104 | DES-011 | `MediaColumns` suite with PNG, JPEG XL, SVG and a PDF fixture | lossless for every type; PDF refused |
| TEST-105 | DES-012 | `GenerationCatalog` suite with 100,000 reads during a switch and an injected snapshot clock | 0 mixed reads; a fourth base waits until the computed expiry |
| TEST-106 | DES-013 | `ArtefactStore` suite against the gateway and the directory backend | all cases pass; 0 deletions outside the drop rule |
| TEST-107 | DES-014 | `RunLedger` suite with a kill at every step boundary of a fixture run | identical output hashes; 0 double-counted spend |
| TEST-108 | DES-015 | `ServiceRegistry` suite including the negative cases | 0 invalid definitions accepted |
| TEST-109 | DES-016 | `QueryEmbedder` suite with the fake runtime and two definitions | 0 mixed-model vectors; timeouts flagged BM25-only |
| TEST-110 | DES-017 | Mutation run: every broken backend through its suite | 100 % of mutants fail at least one case |
