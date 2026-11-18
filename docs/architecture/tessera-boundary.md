# L3/L4: the tessera boundary

The Rust traits the hub owns at its storage, index and provenance boundary. For each one: a signature sketch, its invariants and provenance obligations, the tessera issue that will back it, the interim backend in use until then (with the evidence for whether tessera already provides it), what changes for the caller when the backend is swapped (always nothing) and its failure modes. Section 5 specifies the swap test. The adapters and the download pool are in [adapters and pool](adapters-and-pool.md); open points are in [open questions](../open-questions.md).

> **Source legend.** `XADR-SCITADEL-008` is the vig-os/scitadel decision record "scitadel-hub: a lab corpus server" (ADR 008, status Proposed, [pull request 317](https://github.com/vig-os/scitadel/pull/317)); `§N` is a section of it. `vig-os/tessera#N` issues are linked; `gerchowl/g-fleet#N` is a private repository and is written in code style. Tessera facts were read on 2026-11-18 from the `dev` branch of [vig-os/tessera](https://github.com/vig-os/tessera) (release `v0.1.0-alpha.5`); every "ships" or "does not ship" claim names its path there. Every identifier below is a node in the [trace graph](../traceability/README.md). Each design is `proposed`; signatures are sketches, not code.

**The owner's rule (2026-11-09).** Where tessera already provides a capability, the hub adopts it now and the interim backend *is* tessera. Where it does not, the hub builds the smallest correct thing behind a trait it owns and swaps to tessera the day the issue lands. Constraints on every interim: `.tsra` is the only product format; internal staging that never leaves the hub is allowed and is named as such; no graph database; no PDF bytes served (D-007); everything carries provenance (XADR-SCITADEL-008 §11).

## 1. Conventions shared by every trait (DES-001)

**Crates.** `hub-boundary` holds the traits, the shared types and the **authority layer** of section 1.1, and depends on no backend. Backends live in `hub-backend-tessera` and `hub-backend-interim`. `hub-compose`, the composition root, is the **only** crate that names a backend type; it picks one per trait from configuration (`[backends] text_index = "tantivy-direct"`, and so on). Query service, orchestrator and adapters depend on `hub-boundary` alone. That is the mechanism behind "nothing changes for the caller": a swap is a configuration change plus a new arm in `hub-compose`, and TEST-094 fails the build if any other crate depends on a backend crate.

**Shape of a trait.**

```rust
#[non_exhaustive]
pub enum ErrorKind {
    NotFound, Invalid, Unsupported,   // caller or capability problem
    Integrity,                        // hash, seal or digest mismatch: never retried
    StaleStamp,                       // an index does not cover the pinned generation
    ModelMismatch,                    // query vector and index come from different embedding spaces
    Refused,                          // a policy gate: licence class, tier, PDF bytes, opt-out
    Transient,                        // retry within the caller's budget
    Quota,                            // EDQUOT or a budget: pause, never delete
    Conflict,                         // lost a race (promotion, reservation, create-only key)
}
pub struct HubError { kind: ErrorKind, source: Option<Box<dyn std::error::Error + Send + Sync>> }
impl HubError { pub fn new(kind: ErrorKind, source: impl Into<BoxError>) -> Self; pub fn kind(&self) -> ErrorKind; }
pub type HubResult<T> = Result<T, HubError>;

#[async_trait::async_trait]
pub trait TextIndex<T: Tier>: Send + Sync + 'static { /* async fn …(&self, …) -> HubResult<…>; */ }
```

- **Dynamic dispatch, and how.** Callers hold `Arc<dyn Trait>` chosen at start from configuration, so every boundary trait must be dyn-compatible. Native `async fn` in a trait is not (rustc E0038; section 1.1 has the probe), so every boundary trait is annotated with **`#[async_trait]`**: each method returns a boxed `Send` future. Generic use (`QueryService<V: VectorIndex, T: TextIndex, …>`) was rejected because the backend is chosen from configuration at run time and the type parameters would spread through every caller; hand-written boxed futures are what the macro generates, with more noise. The cost is one allocation per call, against calls that each read at least one leaf or write one ledger row. The rules that keep traits dyn-compatible: no generic methods (a trait may carry a type parameter, such as the tier `T`, because `dyn VectorIndex<Paid>` is a concrete trait object); no associated types; a factory returns `Box<dyn …>` (`ProductStore::create` returns `Box<dyn ProductWriter>`); a consuming method takes `self: Box<Self>`.
- **One error type.** Every method returns `HubResult`. A backend wraps its own error as the `source` of a `HubError` and must give it a kind, so there is no associated error type to erase, callers branch on `kind()` only, and no backend type reaches them. Every trait is `Send + Sync + 'static`.
- **Arrow at the boundary.** Data enters and leaves as `arrow::record_batch::RecordBatch` with an `arrow_schema::SchemaRef`, streamed as DataFusion `SendableRecordBatchStream`; tables are exposed as `Arc<dyn datafusion::catalog::TableProvider>`. No tessera type (`ColumnData`, `TableSpec`, `Reader`) appears in `hub-boundary`; the tessera backend converts at its edge.
- **Provenance is a parameter, not an afterthought.** Every write takes a `&ProvContext` (run id, step id, service-definition hash, input hashes), a capability of section 1.1, so a write without provenance does not compile, and a backend refuses a context whose definition hash does not resolve (SYS-068).
- **Tiers are types.** `Tier` is a sealed trait with two types, `Lab` and `Paid`. A generation is handed to an index or a reader as `Scoped<T, GenerationRef>`, minted only by the tier views of section 1.1; the read and index traits carry `T` (`VectorIndex<T>`, `TextIndex<T>`, `GraphIndex<T>`, `KeyedRefs<T>`, `TableScan<T>`), and `hub-compose` gives the paid-tier service only `dyn …<Paid>` objects. A lab-tier generation therefore does not type-check into a paid-tier index (E0308). A `Scoped<Paid, _>` carries the row predicate of gate 6 ([adapters and pool](adapters-and-pool.md), section 3) and every `<Paid>` implementation applies it.
- **Index stamps.** Every derived index carries

  ```rust
  pub struct IndexStamp<T: Tier> {
      pub covers: Vec<Seal>,                 // the base seal and every delta seal, sorted by sequence
      pub index_params: Blake3,              // analyzer, IVF parameters or edge kinds; never an embedding definition
      pub embedding: Option<EmbeddingStamp>, // vector indexes only
      pub backend: BackendId,                // e.g. "tantivy-direct/0.1", "tessera/0.2"
      pub format_version: u32,
      pub tier: PhantomData<T>,
  }
  pub struct EmbeddingStamp {
      pub definition: DefinitionHash,        // the ingest definition that embedded the corpus (SYS-068); resolves in the registry
      pub space: EmbeddingSpaceId,           // blake3 of the canonical EmbeddingSpace below
  }
  pub struct EmbeddingSpace { model_id, revision, weights_blake3, dimensions, truncation, quantization }
  ```

  The query service pins one `GenerationRef` per query (DES-012) and serves an index only when `stamp.covers` equals that generation's seals; otherwise the index answers `StaleStamp` (SYS-018, SYS-021). The backend id is part of the stamp, so after a swap the new backend reports the old stamps as stale and the existing rebuild path runs: indexes are rebuildable from sealed products alone (SYS-021), which is what makes an index swap free for callers. The two hashes are separate so that the ingest definition stays recoverable from the stamp on its own, while query-time matching uses only the space (section 4.5).
- **Stage portability.** No method takes a host, a bucket name or a model name. Locations are `ShardLocation`/`ObjectUrl` values built from configuration; models are named only by service definitions, and executors only by declared classes and capability tags (SYS-039, SYS-069, section 4.4).

### 1.1 Capabilities and the authority layer

Some values are proofs: that a step is open in the ledger, that a base slot is free, that QC passed, that a query vector comes from the index's embedding space, that a generation passed the paid-tier gates. Each is a type with private fields and no `Default`, `Clone`, `Deserialize` or public constructor, so no crate outside `hub-boundary` can make one. Backends are separate crates, so **a backend cannot mint one either**: the minting code lives in `hub-boundary`'s `authority` module, as concrete types over persistence traits that backends implement. The backend persists a plain record (`StepRecord`, `SlotRecord`, a QC verdict, raw floats); the authority checks the rule and mints.

| Capability | Minted only by | Rule checked before minting | Backend record it reads | Consumed by |
|---|---|---|---|---|
| `ProvContext` | `Steps::started` | the run is open with every input pinned and every definition resolvable (SYS-057, SYS-068) | `RunLedger::record_step` (DES-014) | every write |
| `BaseBuildPermit` | `BaseSlots::reserve`, `BaseSlots::resume` | at most three bases on the tier, a pinned retired base counted (SYS-073) | `BaseSlotStore` (DES-012) | every base path of section 2.4 |
| `QcPass` | `QcGate::certify` | the ledger holds a passing QC record for that generation (SYS-060) | `RunLedger::qc_verdict` | `GenerationCatalog::promote` |
| `QueryVector` | `QueryEmbedder::embed` | the definition's embedding space equals the index's (SYS-071) | `EmbeddingRuntimes::embed` (DES-016) | `VectorIndex::search` |
| `OptOutCycle` | `Steps::opt_out_cycle` | every source of the generation has a verdict from the current ingest cycle (SYS-055, vig-os/scitadel#330) | the ledger's opt-out verdicts | `TierViews::paid` |
| `Scoped<Paid, GenerationRef>` | `TierViews::paid` | an `OptOutCycle`; carries gate 6's row predicate (SYS-054) | none | every `…<Paid>` trait |
| `Scoped<Lab, GenerationRef>` | `TierViews::lab` | none: every row of a generation has passed the licence gate at parse (SYS-001), so the lab scope is the whole generation | none | every `…<Lab>` trait, compaction |

- **Why not a sealed minting trait.** Sealing stops other crates from *implementing* a trait; it does not stop a crate that can mint from minting for anyone, and it would put the policy (slot arithmetic, space match, gate 6) into every backend. With the authority in `hub-boundary` the policy exists once, its unit tests run once, and backends stay swappable because they only persist. Backends are still trusted to check what a capability *says* (a permit's generation against the shard's, `Conflict` otherwise); the suites test that.
- **Lifetimes.** A permit is not persisted; its reservation is. A resumed run gets a permit for its own reservation from `BaseSlots::resume(run)`, which mints only for a reservation the store holds for that run (SYS-061). An abandoned candidate releases its reservation.
- **Proof.** A two-crate probe (rustc and cargo 1.99.0; a `boundary` crate, a `backend` crate, a `compose` binary and an `illegal` crate with one feature per case): the legal path (reserve, create a base shard through `&mut dyn ProductWriter`, publish, compact, certify, promote, lab and paid builds through `dyn VectorIndex<Lab>` and `dyn VectorIndex<Paid>`, a space-matched embed and a mismatch) compiles and runs, exit 0. Every illegal case fails with exit 101: a struct literal of `BaseBuildPermit`, `ProvContext`, `QueryVector`, `QcPass` or `Scoped<Paid, _>` from another crate, E0451; calling the crate-private `BaseBuildPermit::mint`, E0624; cloning a permit, E0308 (no `Clone`); `create`, `compact`, `publish_shard` or `promote` of a base without a permit, E0061 or E0063; a `Scoped<Lab, _>` into `dyn VectorIndex<Paid>`, E0308. The round-1 sketch (native `async fn`, a sync `put` over `&mut dyn ProductWriter`) fails with E0038. These are the compile-fail cases of section 5.

## 2. Tessera-backed traits

### 2.1 `ProductStore`: write, seal, open and verify `.tsra` products (DES-002)

```rust
#[async_trait]
pub trait ProductStore: Send + Sync + 'static {
    /// A base shard needs the permit of its generation (SYS-073); a delta names its base and sequence.
    async fn create(&self, spec: &ProductSpec, role: ShardRole<'_>, at: &StagingPath, prov: &ProvContext)
        -> HubResult<Box<dyn ProductWriter>>;
    async fn open(&self, at: &ShardLocation) -> HubResult<ProductHandle>;
    async fn verify(&self, at: &ShardLocation, expect: Option<&Seal>) -> HubResult<VerifyReport>;
}
#[async_trait]
pub trait ProductWriter: Send {
    async fn push(&mut self, block: &BlockName, batch: RecordBatch) -> HubResult<()>;
    async fn finish(self: Box<Self>, prov: ProvBlocks) -> HubResult<SealedShard>; // path, seal, size, blake3, role
}
pub enum ShardRole<'a> { Base(&'a BaseBuildPermit), Delta { base: Seal, seq: u64 }, Index }
// ProductHandle: seal(), manifest(), blocks(), schema(&BlockName) -> SchemaRef
```

- **Invariants.** A sealed shard is immutable; its seal is tessera's manifest hash and its file blake3 is recorded in the ledger. `ProductSpec` declares every block's Arrow schema up front and `push` refuses a batch that differs. `finish` requires the provenance blocks of DES-009, so no product seals without them. The role is written into the manifest metadata (`hub.role.v1`: the permit's generation and reservation, or base seal and sequence) and returned in `SealedShard`; an `Index` shard (the IVF file of DES-006) can never be published into a collection. Block names and schemas follow the document model of SYS-008; the `figures` block has the fixed contract of DES-011, and no block may hold PDF bytes.
- **Backs it:** [vig-os/tessera#778](https://github.com/vig-os/tessera/issues/778) (umbrella), with the encoding work of [#628](https://github.com/vig-os/tessera/issues/628).
- **Interim: tessera itself (ships).** `tessera-io/src/stream.rs` and `write.rs` (`StreamWriter`, `StreamWriter::push_table`, `open_table`, lanes sealed in order), `tessera-io/src/container.rs` (`pack_streaming_verified`, `Reader`, `verify_payloads_parallel`), `tessera-core/src/manifest.rs` (`Manifest::verify`, `seal_of`) and the schema contract check of `ProductSchema` (tessera PRs 846 and 861). The backend converts Arrow columns to tessera's `ColumnData`, which today carries integers, floats, booleans, UTF-8 and nullable wrappers; wide vectors are refused at its edge and handled by DES-006, and the `bytes` column of `figures` is encoded by DES-011, until [#768](https://github.com/vig-os/tessera/issues/768) and [#779](https://github.com/vig-os/tessera/issues/779) land. Until tessera's wave 1 the adapters stage normalised tables as Parquet in `staging/parquet/` and the product is sealed from there, as XADR-SCITADEL-008 §2 decides; that Parquet is **internal staging only**, never in a bucket and never served (DES-021, C-002).
- **On the swap:** none needed; later tessera releases are a version bump of the same backend.
- **Failure modes.** `Invalid` for a schema mismatch or an unsupported Arrow type; `Integrity` when `verify` finds a digest or seal mismatch; `Quota` on `EDQUOT` in `staging` (the run stops at its next write and resumes, SYS-061); a crash before `finish` leaves a partial file in `staging` that the next run sweeps.

### 2.2 `TableScan`: blocks as DataFusion tables (DES-003)

```rust
#[async_trait]
pub trait TableScan<T: Tier>: Send + Sync + 'static {
    /// One block of one sealed product of the scope, projected and pruned, streamed leaf by leaf.
    fn table(&self, product: &Scoped<T, ProductHandle>, block: &BlockName, opts: &ScanOptions)
        -> HubResult<Arc<dyn TableProvider>>;
    /// The same block across the products of a generation, without delta semantics.
    fn union(&self, g: &Scoped<T, GenerationRef>, block: &BlockName, opts: &ScanOptions)
        -> HubResult<Arc<dyn TableProvider>>;
    /// Newest-wins over base and deltas (the merge rule of DES-005): tombstones dropped, redirects followed.
    fn merged(&self, g: &Scoped<T, GenerationRef>, block: &BlockName, opts: &ScanOptions)
        -> HubResult<Arc<dyn TableProvider>>;
}
// ScanOptions { verify: VerifyBlocks (default) | TrustSealed, batch_rows, max_leaves_in_flight }
// Scoped<T, GenerationRef>::shard(&self, ProductHandle) -> HubResult<Scoped<T, ProductHandle>>  (Refused outside the generation)
```

- **Invariants.** Reads are tier-scoped like indexes (section 1): a `<Paid>` scan applies the scope's row predicate, so paid-tier serving cannot read a row that gate 6 excludes. Every scan reads only sealed bytes and verifies each block digest before use unless the handle was verified at open (`VerifyBlocks` is the default, as in tessera's decision record 0062). Memory is bounded by `max_leaves_in_flight` leaves, never the whole table. The scan exposes the provenance and licence columns of every block (SYS-028, SYS-052) so that the query service can attach them to each record; a projection that drops `prov_id` or `licence_class` is refused for any plan that returns records.
- **Backs it:** [vig-os/tessera#654](https://github.com/vig-os/tessera/issues/654) (sliced into tessera issues 666, 667 and 668: pushdown, zip, multi-product and object store).
- **Interim: hub-built (tessera does not ship it).** Tessera's `tessera sql` materialises into a DataFusion `MemTable` (`tessera-cli/src/sql.rs`), which is not bounded. The hub builds a streaming `TableProvider` over what does ship: `LogicalTableView` and `select_blocks_overlapping` (`tessera-io/src/multiblock.rs`) to choose leaves, `decode_projected` per leaf (`tessera-io/src/table.rs`, at most 2²² rows per leaf), and the int64 chunk statistics of `tessera-core/src/chunk_index.rs` for pruning; filters are reported to DataFusion as `Inexact` and re-applied above the scan. `get` reaches rows through the key index of DES-004 and decodes only the leaves that hold them; whether that meets SYS-025 and SYS-022 without pushdown is spike S-002.
- **On the swap:** nothing; `table`, `union` and `merged` return a `TableProvider` either way, and the conformance suite compares results row for row.
- **Failure modes.** `Integrity` on a digest mismatch (the query fails; it never returns unverified rows); `NotFound` for an unknown block; `Transient` on an I/O error.

### 2.3 `KeyedRefs`: declared keys and references across shards (DES-004)

```rust
#[async_trait]
pub trait KeyedRefs<T: Tier>: Send + Sync + 'static {
    /// key -> (seal, block, row) for the pinned generation; at most 100 keys per call (SYS-025).
    async fn resolve(&self, g: &Scoped<T, GenerationRef>, block: &BlockName, keys: &ArrayRef) -> HubResult<RecordBatch>;
    async fn build(&self, g: &Scoped<T, GenerationRef>, prov: &ProvContext) -> HubResult<IndexStamp<T>>;
    async fn dangling(&self, g: &Scoped<T, GenerationRef>) -> HubResult<DanglingReport>;
}
```

- **Invariants.** A key column is declared in `ProductSpec`, unique within a product and sorted; the writer checks both and refuses otherwise. References (an embedding row to its chunk, an edge endpoint to its work, a retraction flag to a DOI or PMID, SYS-010) name their target block and key. `resolve` answers only for the generation it is given, so a superseded row cannot come back (SYS-005). A sealed generation has 0 dangling references.
- **Backs it:** [vig-os/tessera#780](https://github.com/vig-os/tessera/issues/780) (`TableSpec.keys`, `references`, a key-to-product aux cache, `verify --references`).
- **Interim: hub-built (tessera does not ship it; `RowAlignment` is positional only).** The declaration is written into the product's manifest metadata under `hub.keys.v1`; the key index is a sorted key → (seal, leaf, row) file in `index/keys/<collection>/<stamp>/`, stamped like any index and rebuilt from the products.
- **On the swap:** nothing for callers. Products written before #780 carry the hub declaration; the tessera backend reads both, and the next compaction writes the native one.
- **Failure modes.** `Invalid` on a duplicate or unsorted key at write; `StaleStamp`; `Integrity` when a resolved row's key does not equal the requested key (a corrupt index; rebuilt, never served).

### 2.4 `DeltaStore`: keyed deltas, newest-wins reads and compaction (DES-005)

```rust
#[async_trait]
pub trait DeltaStore: Send + Sync + 'static {
    async fn write_delta(&self, base: &Seal, seq: u64, ops: SendableRecordBatchStream, prov: &ProvContext)
        -> HubResult<SealedShard>;                       // ops: key, op (upsert|delete|redirect), redirect_to, row
    async fn compact(&self, permit: &BaseBuildPermit, g: &Scoped<Lab, GenerationRef>, prov: &ProvContext)
        -> HubResult<CandidateGeneration>;
}
```

- **Invariants.** Nothing is rewritten in place; a delta is a new sealed product naming its base and a strictly increasing sequence. The merge rule, read through `TableScan::merged` (DES-003), returns 0 superseded or tombstoned rows (SYS-005); the read side lives in `TableScan` so that every read is tier-scoped. `compact` is deterministic (rows sorted by key, the same inputs give the same seal) and writes a **candidate**; only `GenerationCatalog::promote` makes it current (SYS-060).
- **The pin rule (SYS-073): every base path takes the permit.** A `BaseBuildPermit` is minted only by `BaseSlots` (section 1.1), and only while at most three bases, a pinned retired base counted, would occupy the tier. Every path that can produce, publish or promote a base requires it, so a fourth base is unrepresentable:

  | Path | Signature | Covers |
  |---|---|---|
  | write a base shard | `ProductStore::create(.., ShardRole::Base(&permit), ..)` | first ingest, a re-derive under SYS-069 that produces a base, a re-embedding sweep, a QC retry, the re-seal on tessera #768 or #779 |
  | compact | `DeltaStore::compact(&permit, ..)` | the quarterly compaction |
  | publish a base shard | `GenerationCatalog::publish_shard(.., Publish::Base { shard, permit }, ..)` | every base shard into `keep` and hot, a base restored from cold included |
  | promote a new base | `GenerationCatalog::promote(.., PromoteTarget::Base(permit), ..)`, consuming it | the switch of `current` |

  `PromoteTarget::Deltas` promotes only deltas on the base that is already current, and `rollback` only to a base still on the tier, so neither adds a base; `Publish::Delta` refuses a shard whose role is `Base`. The wait and its expected end are recorded in the run ledger.
- **Backs it:** [vig-os/tessera#781](https://github.com/vig-os/tessera/issues/781) (`Role::Delta { base, seq }`, sealed `op` column, `tessera compact`), which depends on #780; sizes improve with [#628](https://github.com/vig-os/tessera/issues/628).
- **Interim: hub-built (tessera does not ship it; no upsert, tombstone or compaction code exists).** Delta products use the column layout #781 proposes (`op` as UTF-8, `redirect_to` as the target key) with base seal and sequence in manifest metadata. The merge rule is a DataFusion plan over `TableScan::union`: rank rows by key and descending sequence, keep the first, drop `delete`, resolve `redirect` chains to their final key (a cycle is `Integrity`); `TableScan::merged` exposes it and `compact` streams it into `ProductStore::create` with the base role.
- **On the swap:** nothing for callers; old deltas stay readable by both backends because the column layout already matches the proposal.
- **Failure modes.** `Conflict` for a duplicate sequence or a permit of another generation; `Integrity` for a redirect cycle or a delta whose base seal is not in the generation; `Quota` mid-compaction (the candidate is abandoned and its reservation released, `current` is untouched, SYS-005).

### 2.5 `VectorIndex`: exact and approximate nearest neighbours (DES-006)

```rust
#[async_trait]
pub trait VectorIndex<T: Tier>: Send + Sync + 'static {
    async fn build(&self, g: &Scoped<T, GenerationRef>, source: &EmbeddingSource, params: &AnnParams,
                   prov: &ProvContext) -> HubResult<IndexStamp<T>>;
    /// `q` is minted only by the QueryEmbedder (DES-016) and carries its space and definition hash.
    async fn search(&self, stamp: &IndexStamp<T>, q: &QueryVector, k: usize, filter: Option<&RowFilter>)
        -> HubResult<RecordBatch>;                       // key, score, seal, prov_id
    fn capabilities(&self, stamp: &IndexStamp<T>) -> VectorCapabilities; // exact | ivf-flat | hnsw, embedding stamp
}
```

- **Invariants.** The embeddings of an index generation come from exactly one ingest definition; its hash and its embedding space are the stamp's `embedding`, and the IVF parameters are `index_params`. `search` refuses with `ModelMismatch` a `QueryVector` whose space differs from `stamp.embedding.space` (SYS-071, the rule of section 4.5): no mixed-model results, no fallback model. The method chosen is reported in `capabilities` (SYS-019). Recall against exact scan is a pass criterion of the suite, not a hope.
- **Backs it:** [vig-os/tessera#769](https://github.com/vig-os/tessera/issues/769) (tier 0 exact scan through a `vec_distance` UDF, tier 1 IVF-flat as a sealed centroids product, tier 2 HNSW as an aux cache), on top of [#768](https://github.com/vig-os/tessera/issues/768) (declared `vector{dim, dtype}` columns).
- **Interim: hub-built (tessera ships neither; `tessera-ingest/src/arrow_table.rs` refuses `FixedSizeList` wider than 8 and `ColumnData` has no binary type).**
  - *Storage, inside `.tsra`:* the embeddings product holds a table block (key, chunk ordinal, definition hash, `prov_id`) and the vectors as one tessera blob block per leaf (`tessera-core/src/block/blob.rs`), row-aligned little-endian fp16, whose digest tessera verifies (a deviation from the "native fixed-size lists" of L2 infrastructure section 5 until #768, C-001). The reader exposes them as Arrow `FixedSizeListArray` through `EmbeddingSource`. Nothing leaves `.tsra`.
  - *Exact scan:* in-crate SIMD over those arrays, also the reference for recall.
  - *IVF-flat:* one sealed `.tsra` file per index generation under `index/ann/<collection>/<stamp>/`: the centroids, and per-list postings (list id as an int64 column, so that tessera's shipped int64 chunk statistics prune the lists to probe, then key, seal, leaf and row). It holds **no copy of the vectors**; a probe reads them in place from the hot embeddings products. It is Vortex-encoded as SYS-019 asks, local and never in a bucket as SYS-012 asks, rebuildable, and small (about 16 bytes per vector), so the 0.2 B index estimate of L2 infrastructure section 2.4 holds. That section's premise that the lists live in the products, which would put index bytes on S3, is C-005. The HNSW cache is not built unless S-001 shows IVF-flat cannot meet the budget.
- **On the swap:** nothing for callers. Embedding products are re-sealed with native vector columns by an ordinary run under a base permit (a new generation through promotion), and the IVF file is rebuilt; old stamps report `StaleStamp` until then.
- **Failure modes.** `ModelMismatch`; `StaleStamp`; `Invalid` for a dimension mismatch; `Transient` on I/O. The query service answers a failed or late vector leg BM25-only and flags it (SYS-071).

### 2.6 `TextIndex`: BM25 (DES-007)

```rust
#[async_trait]
pub trait TextIndex<T: Tier>: Send + Sync + 'static {
    async fn build(&self, g: &Scoped<T, GenerationRef>, block: &BlockName, column: &str, analyzer: &AnalyzerConfig,
                   prov: &ProvContext) -> HubResult<IndexStamp<T>>;
    async fn refresh(&self, stamp: &IndexStamp<T>, delta: &Seal, prov: &ProvContext) -> HubResult<IndexStamp<T>>;
    async fn search(&self, stamp: &IndexStamp<T>, query: &str, k: usize, filter: Option<&RowFilter>)
        -> HubResult<RecordBatch>;                       // key, score, seal, prov_id, snippet offsets
    /// Registers `bm25(block, column, query, k)` as a DataFusion table function.
    fn register(&self, ctx: &SessionContext, stamp: &IndexStamp<T>) -> HubResult<()>;
}
```

- **Invariants.** The stamp's `index_params` is the analyzer configuration hash, so a changed analyzer is a new index, never a silent mix. `refresh` makes a delta searchable within 1 h of its seal *(estimate)* (SYS-021) by adding a segment for the delta and masking superseded keys; a full rebuild is the fallback. Results compose with filters through the table function (SYS-018).
- **Backs it:** [vig-os/tessera#775](https://github.com/vig-os/tessera/issues/775) (declared `text_index{column, analyzer}`, tantivy as an aux cache stamped `built_from`, the `bm25` table function).
- **Interim: hub-built, tantivy directly (tessera does not ship text indexing).** One tantivy index per stamp under `index/bm25/<collection>/<stamp>/`, on local NVMe and never over S3 (SYS-012), stamp in the same `built_from` shape #775 proposes. Snippets are cut from the product's text column, not stored twice.
- **On the swap:** nothing for callers; the tessera backend rebuilds from the products, the old index is stale by backend id and is removed by the index sweep.
- **Failure modes.** `StaleStamp`; `Invalid` for a query the analyzer cannot parse (reported, never widened); `Integrity` when a hit's key does not resolve in the pinned generation.

### 2.7 `GraphIndex`: typed edge tables and adjacency (DES-008)

```rust
#[async_trait]
pub trait GraphIndex<T: Tier>: Send + Sync + 'static {
    async fn build(&self, g: &Scoped<T, GenerationRef>, kinds: &EdgeKindSet, prov: &ProvContext) -> HubResult<IndexStamp<T>>;
    /// Depth 1 or 2 (SYS-020), by edge kind and direction.
    async fn neighbours(&self, stamp: &IndexStamp<T>, seeds: &ArrayRef, kinds: &EdgeKindSet, depth: u8, dir: Direction)
        -> HubResult<SendableRecordBatchStream>; // seed, node, kind, depth, via, edge seal, prov_id, licence_class
}
```

- **Invariants.** Edges are product rows, not index state: tables with columns `src`, `dst`, `kind` (and an optional `weight`) in the convention #776 proposes, for work cites work, patent cites patent, patent cites paper and has-CPC (SYS-020). Endpoints are keys (DES-004). Every returned edge carries the seal, `prov_id` and licence class of its edge row, as every record does (SYS-028). The adjacency is a derived cache. **No graph database** (XADR-SCITADEL-008 §4).
- **Backs it:** [vig-os/tessera#776](https://github.com/vig-os/tessera/issues/776) (edge convention, CSR and reverse CSR as an aux cache, `neighbours` table function).
- **Interim: hub-built (tessera does not ship it).** A forward and a reverse CSR per edge kind, built from the edge tables: a node dictionary (key → ordinal) plus `UInt64` offsets and `UInt32` targets as Arrow arrays, persisted in `index/graph/<collection>/<stamp>/` as Arrow IPC files. That file format is an **internal cache that never leaves the hub**: rebuildable, never a product, never served.
- **On the swap:** nothing for callers; the edge tables already follow #776, so only the cache is rebuilt.
- **Failure modes.** `StaleStamp`; `Invalid` for a depth above 2 or an unknown kind; `Integrity` for an endpoint that does not resolve.

### 2.8 `ProvenanceSink`: product and row provenance (DES-009)

```rust
#[async_trait]
pub trait ProvenanceSink: Send + Sync + 'static {
    fn begin(&self, ctx: &ProvContext, step: &PipelineStep) -> HubResult<ProvWriter>;
    async fn explain(&self, g: &GenerationRef, key: &ScalarKey) -> HubResult<ProvTrace>;
    /// SYS-069: every row produced by one definition, set-equal to the ledger's answer.
    async fn select_by_definition(&self, g: &GenerationRef, def: &DefinitionHash) -> HubResult<SendableRecordBatchStream>;
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
#[async_trait]
pub trait RemoteRead: Send + Sync + 'static {
    async fn open(&self, url: &ObjectUrl) -> HubResult<ProductHandle>;
    /// SYS-059 read-back and SYS-047 restore: every digest checked against the expected seal.
    async fn verify(&self, url: &ObjectUrl, expect: &Seal) -> HubResult<VerifyReport>;
}
```

- **Invariants.** Used for the canonical copy in `scitadel-hub-keep` and later the warm tier: the read-back after a write, reconciliation at start, restore and rebuilding indexes when the hot copy is missing. **Never for serving index reads**, which are local (SYS-012). Credentials are the reading role's, from the hub's secrets file (SYS-040, SYS-041).
- **Backs it:** [vig-os/tessera#777](https://github.com/vig-os/tessera/issues/777) (remote open, verify and projection of a `.tsra` over HTTP or S3).
- **Interim: tessera itself for opening (ships), the hub for remote verify.** `tessera-io/src/cloud.rs` (`open_url`, `ObjectStoreReader`, feature `cloud`) opens a `.tsra` over S3 or HTTPS by range. What #777 adds, a ranged remote verify, is not there; until it is, `verify` streams the whole object once and checks it with `verify_payloads` and the file blake3, which is what the read-back of SYS-059 needs anyway.
- **On the swap:** nothing for callers; `verify` gets cheaper.
- **Failure modes.** `Transient` for a network error (retried within the caller's budget); `Integrity` for a mismatch (never retried; the shard is not published or not restored); `NotFound`.

### 2.10 Media columns: the `figures` contract and its encoding (DES-011)

Callers see figures in exactly one shape, the one [vig-os/tessera#779](https://github.com/vig-os/tessera/issues/779) gives them natively: an ordinary `figures` block whose bytes are an Arrow `BinaryView` column. They write it with `ProductWriter::push` and read it with `TableScan`, like any block; how the bytes are stored is the backend's business and changes on the swap without a caller seeing it.

```rust
/// The contract, fixed in hub-boundary from day one (SYS-008, SYS-028, SYS-052).
pub fn figures_schema() -> SchemaRef;
//   key: Utf8 (the work)  fig_id: Utf8  media_type: Utf8 (image/png | image/jxl | image/svg+xml)
//   width: UInt32  height: UInt32  media_hash: Utf8 (blake3, hex)  licence_class: Utf8  prov_id: <DES-009>
//   bytes: BinaryView, field metadata {"media_type_column": "media_type"}

/// Caller side, in hub-boundary: validation and hashing only, no I/O, so it is a plain sync builder.
pub struct FiguresBuilder { /* rows, the step's ProvContext */ }
impl FiguresBuilder {
    pub fn new(prov: &ProvContext) -> Self;
    pub fn put(&mut self, key: &str, fig_id: &str, m: MediaValue, row: ProvId) -> HubResult<MediaRef>;
    pub fn finish(self) -> RecordBatch;          // in figures_schema(); then `writer.push(&FIGURES, batch).await`
}
pub struct MediaValue { media_type: MediaType, width: u32, height: u32, bytes: Bytes,
                        source_blake3: Blake3, licence_class: LicenceClass }   // MediaType: Png | JpegXlLossless | Svg
```

- **No separate backend trait.** The round-1 `MediaColumns::put` was a second, synchronous write path beside the async `ProductWriter::push`, over a `&mut dyn ProductWriter` that was not dyn-compatible (E0038). There is now one write path and one read path: the encoding of `bytes` is part of the `ProductStore` backend (on `push` of the `figures` block) and of the `TableScan` backend (which reads `bytes` only when it is projected), and the suite runs through those two traits. `FiguresBuilder::put` is synchronous because it does no I/O; the caller pushes its batch with the async `push` through `Box<dyn ProductWriter>`, which the probe of section 1.1 compiles.

- **Invariants.** Figures are stored lossless only and decode to the pixels (or SVG) of the source (SYS-008). The media-type set is closed: `application/pdf` and any unlisted type are `Refused` by `put`, so no product can hold PDF bytes and no call can serve them (D-007, SYS-032). A value above 16 MiB *(estimate; #779's default cap)* is `Invalid`. Every row carries its `media_hash`, the licence class of its work and a `prov_id` naming the step and the raw artefact it was extracted from (`source_blake3`); `put` refuses a value without a licence class, and a `figures` block without `prov_id` does not seal (DES-009). `TableScan` exposes exactly `figures_schema()` for every backend.
- **Backs it:** [vig-os/tessera#779](https://github.com/vig-os/tessera/issues/779) (declared `media{media_type | media_type_column}` columns over Vortex `VarBinView`, exposed by the #654 provider as Arrow `BinaryView` with the media type in field metadata, optional per-row `media_hash`, per-value cap).
- **Interim: hub-built media packs on a shipped primitive (tessera has no binary column; `ColumnData` lacks `Binary`, ingest refuses binary Arrow types, `tessera-ingest/src/arrow_table.rs`).** #779 rejects one blob block per figure, because about 10⁷ figures (and about 10⁸ at L2's scale) would mean as many blocks, manifest entries and digests. The interim therefore packs: on `push` of `figures` the `ProductStore` backend appends the values to a **media pack**, one tessera blob block (`tessera-core/src/block/blob.rs`) of concatenated values with the media type `application/vnd.scitadel-hub.media-pack.v1`, named `media-pack/<blake3 of the pack>` and closed at 256 MiB *(estimate)*, in the same shard as its `figures` rows. The stored `figures` block holds the contract columns except `bytes`, plus `pack`, `offset` and `length`; tessera verifies each pack's digest, and the `TableScan` backend rebuilds `bytes` from the slices and verifies each against `media_hash`. A shard of 10⁵ figures at about 100 KB has about 40 packs, so blocks grow with bytes, not with figures. SVG is packed like any value; #779 may store it on its text path, which is again invisible to callers.
- **On the swap:** nothing for callers: the contract schema, its column names and types, and the field metadata are those of #779's provider. The tessera backend reads both encodings (a shard says which in `hub.media.v1`) and the next compaction re-seals natively under a base permit (section 2.4).
- **Failure modes.** `Refused` for a forbidden type; `Invalid` for a value above the cap, a missing licence class or a failed lossless round trip; `Integrity` for a pack digest or `media_hash` mismatch.

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
| media columns (`figures` through `ProductStore` and `TableScan`) | DES-011 | #779 | media packs (tessera blob blocks) behind the fixed `figures` contract | no (blob blocks only) |

All twelve tessera issues were open on 2026-11-18; none of [#778](https://github.com/vig-os/tessera/issues/778)'s waves has merged.

## 4. Hub-owned boundaries that tessera does not back

Same conventions as section 1, no tessera issue behind them: these are the hub's lifecycle, ledger and configuration. Each still has two backends, so the swap rule and the suite of section 5 apply.

### 4.1 `GenerationCatalog`: collections, `current` and canonical-first writes (DES-012)

```rust
#[async_trait]
pub trait GenerationCatalog: Send + Sync + 'static {
    /// SYS-059: keep first (create-only, read back, blake3), then hot (temporary name, verify, rename).
    /// `prov` names the run and step, so every object written to `keep` links to its ledger record.
    async fn publish_shard(&self, c: &CollectionId, g: &GenerationId, p: Publish<'_>, prov: &ProvContext)
        -> HubResult<PublishedShard>;
    async fn current(&self, c: &CollectionId) -> HubResult<GenerationRef>;
    async fn generations(&self, c: &CollectionId) -> HubResult<Vec<GenerationInfo>>;
    /// SYS-060: a passing QC record; one atomic switch, keep first, hot by rename.
    async fn promote(&self, c: &CollectionId, target: PromoteTarget, qc: QcPass, prov: &ProvContext)
        -> HubResult<GenerationRef>;
    async fn rollback(&self, c: &CollectionId, to: &GenerationId, prov: &ProvContext) -> HubResult<GenerationRef>;
    async fn reconcile(&self) -> HubResult<ReconcileReport>; // keep wins
}
pub enum Publish<'a> { Base { shard: &'a SealedShard, permit: &'a BaseBuildPermit }, Delta { shard: &'a SealedShard } }
pub enum PromoteTarget { Base(BaseBuildPermit), Deltas(GenerationId) }

/// Persistence behind the BaseSlots authority (section 1.1); implemented by the catalog's backend.
#[async_trait]
pub trait BaseSlotStore: Send + Sync + 'static {
    /// Current, previous, candidates and retired-but-pinned bases, with the inventory version.
    async fn base_inventory(&self, c: &CollectionId) -> HubResult<BaseInventory>;
    /// Create-only per run; `Conflict` if the inventory changed since `seen` (optimistic, so two runs cannot both pass).
    async fn record_reservation(&self, c: &CollectionId, run: &RunId, seen: InventoryVersion) -> HubResult<SlotRecord>;
    async fn reservation_of(&self, run: &RunId) -> HubResult<Option<SlotRecord>>;
    async fn release(&self, r: &SlotRecord) -> HubResult<()>;
}
// authority: BaseSlots::reserve(c, run, now) -> SlotDecision = Granted(BaseBuildPermit) | Wait { until, reason }
//            BaseSlots::resume(run) -> Option<BaseBuildPermit>
```

- **Invariants.** The layout `base/<release>/`, `delta/<date>.tsra`, `current` (SYS-002). `publish_shard` never moves `current`. A reader resolves `current` once per query and pins that `GenerationRef`, so it sees the old or the new generation, never a mix. `promote` consumes a `QcPass` (minted only by `QcGate`) for the same generation, and for a new base the permit too; `PromoteTarget::Deltas` is refused (`Invalid`) for a generation whose base is not the current one. `rollback` is refused for a base no longer on the tier; a base restored from cold is a base build with its own permit. `BaseSlots::reserve` (in `hub-boundary`) reads the inventory, counts a retired base as the previous one while a snapshot pins it, computes the pin's expiry from the snapshot schedule in configuration (L2 infrastructure section 2.4), and returns `Wait` while the count would exceed three; the orchestrator records the wait and its expected end in the ledger and raises an alert if the wait exceeds the longest snapshot retention. Every object `publish_shard` writes to `keep` carries the run and step ids of its `ProvContext` in its metadata and is recorded against that step in the ledger. Retention deletes are **not** a method here: they belong to the retention role (SYS-017), a separate credential.
- **Backend:** S3 keys in `scitadel-hub-keep` written by the ingest role (or the newest-wins sequence of pointer objects if the gateway has no per-key rule, L2 infrastructure section 4), the hot pointer `products/<collection>/current` replaced by `rename(2)`, and collection manifests through tessera's shipped `CollectionBuilder` (`tessera-core/src/collection.rs`). **Second backend:** in memory over a temporary directory, for the suite.
- **Failure modes.** `Integrity` on a read-back mismatch (not published; the keep object stays unreferenced and is swept); `Conflict` when two promotions or two reservations race (one wins, the other is refused and logged), or for a permit of another generation; `Invalid` for `Publish::Delta` of a base shard; `Wait` is a result, not an error.

### 4.2 `ArtefactStore`: the content-addressed raw and intermediate store (DES-013)

```rust
#[async_trait]
pub trait ArtefactStore: Send + Sync + 'static {
    /// Create-only by blake3; read back and verified before Ok. Records every source digest in `meta`
    /// that the bytes verified against, in the source-digest index.
    async fn put(&self, file: &StagedFile, meta: &ArtefactMeta, prov: &ProvContext) -> HubResult<ArtefactRef>;
    async fn put_intermediate(&self, input: &Blake3, step: &PipelineStep, file: &StagedFile, prov: &ProvContext)
        -> HubResult<ArtefactRef>;                      // keyed by input hash, tool, model, version, definition hash
    async fn get(&self, r: &ArtefactRef) -> HubResult<VerifiedReader>;
    async fn head(&self, h: &Blake3) -> HubResult<Option<ArtefactMeta>>;
    /// Dedup before download: a digest a source publishes -> the kept artefact (DES-019).
    async fn by_source_digest(&self, d: &SourceDigest) -> HubResult<Option<ArtefactRef>>;
}
// SourceDigest { namespace: SourceNamespace, algorithm: Md5 | Sha1 | Sha256 | Sha512, digest: Box<[u8]>, size: u64 }

/// The operator's hand-drop (SYS-014). Not composed into any hub process: only the `hub raw drop` command holds it,
/// with its own operator credential.
#[async_trait]
pub trait RawDrop: Send + Sync + 'static {
    async fn drop_refetchable(&self, h: &Blake3, audit: &OperatorAudit) -> HubResult<()>;
}
```

- **Invariants.** Keys `cas/<first two hex>/<blake3>` and `inter/<input blake3>/<tier>/<definition hash>/…` in `scitadel-hub-keep` (SYS-014), then on the warm tier by configuration (SYS-015). The source-digest index is create-only keys `srcdigest/<algorithm>/<hex>` whose body names the blake3, the size and the namespace; a mapping is written only after the bytes verified against that digest, and a second blake3 for the same digest is `Integrity` and quarantined, never overwritten. Nothing is deleted automatically, and `ArtefactStore` has no delete at all: no hub process holds a raw-delete right. A re-run of a tier writes new intermediates beside the old ones (SYS-066). `get` serves the hub's own processes (cascade, renders of SYS-064); no protocol call returns raw bytes, and PDFs are never served (D-007). `put` returns `Quota` at the stage-0 raw budget, which pauses ingest (L2 infrastructure section 2.4), and the ledger's backup-age check gates raw-writing runs (SYS-072).
- **The hand-drop is an operator role.** SYS-014 allows exactly one removal: an operator dropping by hand a re-fetchable open-access PDF whose hash and URL are recorded. `RawDrop` refuses every other class (`Refused`), records the audit in the ledger before the delete, and is built only into the `hub raw drop` operator command (L2 infrastructure section 2.4), with an operator gateway credential whose only delete right is on `cas/` keys. The hub's serving, ingest and retention roles never hold it. L2 infrastructure section 4 lists no such role (its retention role may "never" delete raw inputs, and section 3 gives the operator read access only), which is a gap against SYS-014 recorded for the architect, not changed here.
- **Backend:** the S3 gateway through the `object_store` crate. **Second backend:** a local directory with the same key scheme.
- **Failure modes.** `Integrity` (read-back or re-fetch mismatch, or a conflicting source-digest mapping); `Quota`; `Refused` for a drop outside the allowed class; `Conflict` is impossible by construction (same key, same bytes) and is treated as success after a hash compare.

### 4.3 `RunLedger`: runs, steps, queue and spend (DES-014)

```rust
#[async_trait]
pub trait RunLedger: Send + Sync + 'static {
    async fn open_run(&self, kind: RunKind, pins: &InputPins, defs: &[DefinitionHash]) -> HubResult<RunId>;
    /// A plain record; the `Steps` authority turns it into a `ProvContext` (section 1.1).
    async fn record_step(&self, run: &RunId, step: &StepKey) -> HubResult<StepRecord>;
    async fn step_completed(&self, run: &RunId, step: &StepKey, outputs: &[OutputHash]) -> HubResult<()>;
    async fn resume_point(&self, run: &RunId) -> HubResult<ResumePlan>;
    async fn spend(&self, run: &RunId, step: &StepKey, s: &Spend) -> HubResult<()>;   // idempotent per step
    async fn enqueue(&self, item: &QueueItem) -> HubResult<()>;
    async fn record_wait(&self, run: &RunId, until: Timestamp, reason: &WaitReason) -> HubResult<()>;
    async fn qc_verdict(&self, g: &GenerationId) -> HubResult<Option<QcRecord>>;
    async fn opt_out_verdicts(&self, cycle: &CycleId) -> HubResult<Vec<OptOutVerdict>>;
    async fn gpu_submitted(&self, run: &RunId, job: &GpuJobRecord) -> HubResult<()>;
    async fn gpu_job_ended(&self, job: &GpuJobId, hashes: &[FileHash]) -> HubResult<()>; // hub-computed
}
// authority: Steps::started(run, step) -> ProvContext; Steps::opt_out_cycle(cycle, sources) -> OptOutCycle;
//            QcGate::certify(g) -> QcPass
```

- **Invariants.** A run record exists before step 1, with every input pinned by version or snapshot date and hash and every definition hash; an unpinned input refuses `open_run` (SYS-057). `Steps::started`, over `record_step`, is the only issuer of `ProvContext`; `QcGate` and `Steps::opt_out_cycle` mint from `qc_verdict` and `opt_out_verdicts` the same way. `resume_point` skips completed steps whose outputs still verify (SYS-061); `spend` is keyed by step, so a resume never double-counts credits or budget. Queued T3 and T4 work lives here, not in a bucket (SYS-006). The GPU acceptance order of SYS-062 reads `gpu_submitted` and `gpu_job_ended` (DES-022).
- **Backend:** SQLite with a write-ahead log on `state` (`+C`), dumped nightly to `keep`. **Second backend:** in-memory SQLite, for the suite and the crash-injection tests.
- **Failure modes.** `Invalid` for an unpinned input; `Conflict` for a step started twice concurrently; `Integrity` when a completed step's outputs no longer verify (the step is redone, SYS-061).

### 4.4 `ServiceRegistry`: versioned, content-hashed definitions (DES-015)

```rust
#[async_trait]
pub trait ServiceRegistry: Send + Sync + 'static {
    fn validate(&self, d: &Definition) -> HubResult<DefinitionHash>;
    async fn active(&self, kind: &JobKind) -> HubResult<ResolvedDefinition>;
    async fn resolve(&self, h: &DefinitionHash) -> HubResult<ResolvedDefinition>;
    /// The active query-embedding definition of an embedding space (SYS-071, section 4.5).
    async fn query_embedder_for(&self, space: &EmbeddingSpaceId) -> HubResult<Option<ResolvedDefinition>>;
}
// Definition { kind, executor: ExecutorRef { class: gpu_submit | cpu_pool | remote_api, tags, vram, max_runtime,
//   priority, chunk }, model: EmbeddingSpace-shaped { id, revision, quantization, weights_blake3, dimensions,
//   truncation }, runtime { name, version }, budget_cap, escalation_target, licence_classes }
// Executors are declared in configuration data, e.g. [executors.shared-gpu] class = "gpu_submit", tags = ["shared_gpu"]
```

- **Invariants.** A definition is configuration, canonicalised and hashed with blake3; a change is a new version; every version is stored by hash in `keep` and stays resolvable (SYS-067). `validate` refuses the cases of SYS-067: incomplete, a `gpu_submit` executor without VRAM or low priority, T3 or T4 without a budget cap, T4 with a class outside CC-BY, CC0 and public domain, and an escalation cycle; and, for SYS-051, a backfill or re-embedding sweep whose executor carries the tag `shared_gpu`. That rule is a property of the executor declared in the data, never a host name in code: which executor is the shared GPU is configuration. Moving a tier to another executor is a new definition and no code change; **no code names a host or a model** (SYS-069, TEST-089). A sage executor exists only if a definition names it (SYS-070). Weights come through the signed manifest and must equal `weights_blake3` (SYS-056).
- **Backend:** TOML files in the hub's configuration, loaded at start, mirrored by hash to `keep`. **Second backend:** an in-memory registry.
- **Failure modes.** `Invalid` with the failing rule; `NotFound` for an unknown hash (the step or row is refused, SYS-068).

### 4.5 `QueryEmbedder`: hub-side query vectors (DES-016)

```rust
/// Authority in hub-boundary (section 1.1): the only minter of QueryVector.
pub struct QueryEmbedder { registry: Arc<dyn ServiceRegistry>, runtimes: Arc<dyn EmbeddingRuntimes> }
impl QueryEmbedder {
    /// Embeds in the space of `target`, or refuses. Never another model.
    pub async fn embed<T: Tier>(&self, text: &str, target: &IndexStamp<T>, deadline: Instant) -> HubResult<QueryVector>;
}
/// Backend: loads the runtime a definition names and returns raw vectors.
#[async_trait]
pub trait EmbeddingRuntimes: Send + Sync + 'static {
    async fn embed(&self, def: &ResolvedDefinition, text: &str, deadline: Instant) -> HubResult<Float32Array>;
}
// QueryVector { values, space: EmbeddingSpaceId, query_definition: DefinitionHash, index_definition: DefinitionHash }
```

- **The matching rule.** A query definition matches an index generation when their **embedding spaces are equal**: model id, revision, weights hash, dimensions, truncation and quantization, the model fields of SYS-067 and exactly the list of SYS-071. The definition hashes are *not* compared: a query definition legitimately differs from the ingest one in executor, runtime and its version, batching and limits (a CPU runtime in `vm-hub` against a `gpu_submit` batch executor), and each of those changes the hash. Numerical drift between two runtimes of one space is measured by TEST-091's recall@10 on the golden queries before a definition is enabled (SYS-071).
- **Invariants.** The query embedder is a **registry consumer** (D-009, SYS-071): it reads `target.embedding.space`, asks `ServiceRegistry::query_embedder_for` for the active definition of that space, checks that the definition's own space hashes to the same id, and embeds through `EmbeddingRuntimes`. No definition, or a runtime that returns another dimension, is `ModelMismatch` and the vector leg is refused. Both definition hashes, the query's and the index's ingest definition from the stamp, travel in `QueryVector` into the response's provenance and `capabilities` (SYS-027). Because `embed` is a method of a concrete type, it may be generic over the tier. Clients never send vectors; the protocol rejects them before this trait is reached. It runs on CPU in `vm-hub`; a GPU executor is possible only by a definition that names one outside the serving microVM, after the benchmark and with the owner's approval (SYS-024). Missing the deadline is `Transient`, and the query service answers BM25-only, flagged (SYS-071).
- **Backends** (of `EmbeddingRuntimes`): the in-process CPU runtime the active definition names; a GPU-slot executor through the same definition mechanism; a deterministic fake for the suite. Which model is the default is decided by the benchmark of TEST-091 on anvil's RTX 5090 and the serving CPU, together with SYS-050, not here.
- **Failure modes.** `ModelMismatch`; `Transient` (timeout); `Integrity` when the loaded weights do not hash to the definition's.

## 5. The swap test (DES-017)

One crate, `hub-boundary-conformance`, holds one suite per trait, run against trait objects exactly as callers hold them: `pub async fn run(make: impl Fn() -> Arc<dyn TextIndex<Lab>>, fixtures: &Fixtures) -> SuiteReport` (and the `<Paid>` instance for the tier cases). Every backend crate calls the suite of each trait it implements from its own integration tests, and CI runs every backend on every pull request. The fixtures are the CC0 fixture corpus (a base, three deltas with an update, a merge and a delete, figures in each media type, edges of each kind, embeddings from two spaces and two definitions of one space, rows of every licence class with and without an opt-out record) plus seeded corruptions.

**Pass criteria for every suite.** All named cases pass; results are compared with the reference backend (the interim one until tessera lands, then each other) **row for row** for deterministic traits and by **recall@10 ≥ 0.99 against exact scan** for approximate vector search; the error *kind* of every negative case equals the expected one.

| Suite | Named cases (each is one test function) |
|---|---|
| Capabilities (compile-fail, trybuild in `hub-boundary-conformance/tests/ui`; the expected error code is pinned) | `mint_permit_literal` (E0451), `mint_permit_private_fn` (E0624), `permit_not_clone` (E0308), `mint_prov_context_literal`, `mint_query_vector_literal`, `mint_qc_pass_literal`, `mint_paid_scope_literal` (each E0451), `create_base_without_permit` (E0061), `compact_without_permit` (E0061), `publish_base_without_permit` (E0063), `promote_base_without_permit` (E0061), `lab_scope_into_paid_index` (E0308) |
| `ProductStore` | `seal_roundtrip_is_bit_exact`, `seal_is_deterministic`, `push_refuses_schema_drift`, `finish_refuses_missing_provenance`, `verify_detects_flipped_byte`, `partial_write_never_opens`, `base_create_with_other_generation_permit_conflict`, `role_recorded_in_manifest` |
| `TableScan` | `projection_and_filter_match_reference`, `pruning_skips_leaves`, `memory_bounded_by_leaves_in_flight`, `corrupt_block_fails_query`, `prov_and_licence_columns_always_present`, `paid_scope_applies_gate_six_predicate`, `shard_outside_scope_refused` |
| `KeyedRefs` | `resolve_hundred_keys`, `duplicate_key_refused`, `superseded_key_not_resolved`, `dangling_reference_reported`, `paid_resolve_skips_excluded_rows` |
| `DeltaStore` (reads through `TableScan::merged`) | `newest_wins`, `tombstone_hides_row`, `redirect_chain_followed`, `redirect_cycle_is_integrity`, `compaction_is_deterministic`, `compact_with_other_generation_permit_conflict`, `kill_mid_compaction_leaves_current_and_releases_slot` |
| `VectorIndex` | `exact_matches_brute_force`, `ann_recall_at_10`, `space_mismatch_refused`, `filter_respected`, `capabilities_report_method_and_embedding_stamp` |
| `TextIndex` | `bm25_scores_match_reference`, `analyzer_change_is_new_stamp`, `delta_refresh_masks_superseded`, `stale_stamp_refused` |
| `GraphIndex` | `depth_one_and_two_by_kind`, `reverse_direction`, `unknown_kind_invalid`, `stale_stamp_refused` |
| `ProvenanceSink` | `every_row_has_prov_id`, `explain_reaches_raw_hash_and_url`, `select_by_definition_equals_ledger`, `unresolvable_definition_refused` |
| `RemoteRead` | `open_matches_local`, `verify_detects_flipped_byte`, `transient_error_classified` |
| Media columns (`figures` through `ProductStore` and `TableScan`) | `figures_schema_identical_on_every_backend`, `lossless_roundtrip_per_type`, `pdf_refused`, `unknown_type_refused`, `oversize_refused`, `missing_licence_class_refused`, `figures_without_prov_id_do_not_seal`, `blocks_grow_with_bytes_not_figures`, `bytes_not_read_unless_projected`, `media_hash_mismatch_is_integrity` |
| `GenerationCatalog` and `BaseSlots` | `keep_before_hot`, `publish_never_moves_current`, `keep_objects_carry_run_and_step`, `promote_needs_qc_of_same_generation`, `no_mixed_generation_during_switch`, `fourth_base_waits`, `concurrent_reservations_one_wins`, `resume_reissues_own_reservation_only`, `publish_delta_of_base_shard_refused`, `deltas_promote_of_new_base_refused`, `rollback_to_absent_base_refused`, `reconcile_keep_wins` |
| `ArtefactStore` and `RawDrop` | `create_only_by_hash`, `intermediate_beside_old`, `quota_pauses`, `source_digest_hit_returns_artefact`, `conflicting_source_digest_is_integrity`, `drop_refuses_non_refetchable`, `drop_audited_before_delete` |
| `RunLedger` | `unpinned_input_refused`, `resume_skips_verified_steps`, `spend_not_double_counted`, `queue_survives_restart`, `opt_out_cycle_refused_with_unchecked_source` |
| `ServiceRegistry` | the nine refusal cases of SYS-067, `sweep_on_shared_gpu_executor_refused`, `hash_is_canonical`, `every_version_resolvable` |
| `QueryEmbedder` over `EmbeddingRuntimes` | `space_match_ignores_runtime_and_executor`, `space_mismatch_refused_per_field` (one case per field of the space), `ingest_definition_recoverable_from_stamp`, `both_definition_hashes_in_provenance`, `timeout_is_transient` |

**The suite is itself tested.** For each trait a set of deliberately broken backends (one per invariant: a scan that drops `prov_id`, a merge that keeps tombstones, an index that ignores the stamp) must each fail at least one named case; a mutant that passes means a missing case (TEST-110). Together with the dependency check of section 1 (TEST-094), that is the swap test: a backend that passes its suite can replace another with no caller change, and nothing outside `hub-compose` can tell the difference.

**Unit-level expectations (L4).** Beside the suites: the Arrow-to-`ColumnData` conversion table (every supported type, every refused type); the redirect resolver on chains and cycles; the stamp equality rule; the canonical hashing of `EmbeddingSpace`; the slot arithmetic of `BaseSlots::reserve` with an injected clock; the gate-6 row predicate; canonical definition hashing on reordered TOML; the fp16 blob layout against a reference encoder.

## 6. Verification

Every design here is verified by one integration test; all run in CI on fixtures unless the row says otherwise.

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-094 | DES-001 | Dependency check over the workspace (`cargo metadata`): only `hub-compose` depends on a backend crate; `ErrorKind` mapping test per backend; the compile-fail capability cases of section 5 | 0 other dependents; 100 % of backend errors carry a kind; every compile-fail case fails with its pinned error code |
| TEST-095 | DES-002 | `ProductStore` suite against the tessera backend | all cases pass; bit-exact round trip |
| TEST-096 | DES-003 | `TableScan` suite, interim backend versus a `MemTable` reference | row-for-row equal; peak memory ≤ the leaf bound |
| TEST-097 | DES-004 | `KeyedRefs` suite | all cases pass |
| TEST-098 | DES-005 | `DeltaStore` suite, including a kill at every compaction step | 0 superseded rows; `current` unchanged after every kill |
| TEST-099 | DES-006 | `VectorIndex` suite; ksb timing on the SYS-063 slice | recall@10 ≥ 0.99 on fixtures; recall ≥ 0.95 and p95 ≤ 20 ms *(estimate)* on the slice |
| TEST-100 | DES-007 | `TextIndex` suite; ksb timing on the slice | all cases pass; p95 ≤ 50 ms *(estimate)* |
| TEST-101 | DES-008 | `GraphIndex` suite; ksb timing on the slice | all cases pass; depth-2 p95 ≤ 100 ms *(estimate)* |
| TEST-102 | DES-009 | `ProvenanceSink` suite; a 1,000-row sample traced to seal, raw hash and URL | 100 % resolved; selection set-equal to the ledger |
| TEST-103 | DES-010 | `RemoteRead` suite against a local S3 gateway in CI | all cases pass |
| TEST-104 | DES-011 | Media-columns suite through `ProductStore` and `TableScan` with PNG, JPEG XL, SVG and a PDF fixture, and a 10⁵-figure shard | `figures` schema identical on every backend; lossless for every type; PDF refused; blob blocks per shard ≤ ⌈bytes / 256 MiB⌉ + 1 |
| TEST-105 | DES-012 | `GenerationCatalog` and `BaseSlots` suite with 100,000 reads during a switch, an injected snapshot clock and two runs reserving at once | 0 mixed reads; a fourth base waits until the computed expiry on every base path; one of two racing reservations wins |
| TEST-106 | DES-013 | `ArtefactStore` and `RawDrop` suite against the gateway and the directory backend | all cases pass; 0 deletions outside the drop rule |
| TEST-107 | DES-014 | `RunLedger` suite with a kill at every step boundary of a fixture run | identical output hashes; 0 double-counted spend |
| TEST-108 | DES-015 | `ServiceRegistry` suite including the negative cases | 0 invalid definitions accepted |
| TEST-109 | DES-016 | `QueryEmbedder` suite with the fake runtime: two spaces, and two definitions of one space differing only in runtime and executor | the two definitions of one space both accepted; every single-field change of the space refused; 0 mixed-model vectors; timeouts flagged BM25-only |
| TEST-110 | DES-017 | Mutation run: every broken backend through its suite | 100 % of mutants fail at least one case |
