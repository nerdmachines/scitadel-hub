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
    StaleStamp,                       // an index does not cover the pinned generation's seals
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
- **Tiers are types.** `pub trait Tier: sealed::Sealed + Send + Sync + 'static { const ID: TierId; }` has two types, `Lab` and `Paid`; the `Send + Sync + 'static` bound is what lets a `#[async_trait]` method that holds a `&Scoped<T, _>` or an `&IndexStamp<T>` across an `.await` return a `Send` future (without it, rustc reports "future cannot be sent between threads safely"), and `ID` puts the tier into values (stamps, paths) as well as types. A generation is handed to an index or a reader as `Scoped<T, GenerationRef>`, minted only by the tier views of section 1.1; the read and index traits carry `T` (`VectorIndex<T>`, `TextIndex<T>`, `GraphIndex<T>`, `KeyedRefs<T>`, `TableScan<T>`), and `hub-compose` gives the paid-tier service only `dyn …<Paid>` objects. A lab-tier generation therefore does not type-check into a paid-tier index (E0308). A `Scoped<Paid, _>` carries gate 6's predicate ([adapters and pool](adapters-and-pool.md), section 3) as an `ExclusionSet`, an allow-list, and every `<Paid>` implementation applies it. Only `PaidTier` mints and holds a paid scope, one per call (section 1.2).
- **Index stamps.** Every derived index carries

  ```rust
  pub struct IndexStamp<T: Tier> {           // every field private; read through getters
      tier: TierId,                          // T::ID as a value: hashed into the stamp id and the directory
      admitted_under: Option<ExclusionDigest>, // paid only: the ExclusionSet the build admitted under (section 1.2)
      covers: Vec<Seal>,                     // the base seal and every delta seal, sorted by sequence
      index_params: Blake3,                  // analyzer, IVF parameters or edge kinds; never an embedding definition
      embedding: Option<EmbeddingStamp>,     // vector indexes only
      backend: BackendId,                    // e.g. "tantivy-direct/0.1", "tessera/0.2"
      kind: IndexKind, collection: CollectionId, format_version: u32,
      _tier: PhantomData<T>,
  }
  /// Names an index (what the caller keeps between queries): no tier, generation, seal or digest. Public, Clone.
  pub struct IndexSpec { pub kind: IndexKind, pub collection: CollectionId, pub index_params: Blake3,
                         pub embedding: Option<EmbeddingStamp>, pub backend: BackendId }
  impl<T: Tier> Scoped<T, GenerationRef> {
      /// The only constructors. Tier, seals and admission digest come from this scope, never from another stamp;
      /// `StaleStamp` once the scope has expired (below).
      pub fn stamp(&self, spec: &IndexSpec) -> HubResult<IndexStamp<T>>;
      /// For `refresh`: this scope's seals without its newest `delta`, with the admission digest of the build it extends; `Conflict` if `delta` is not newest.
      pub fn stamp_before(&self, spec: &IndexSpec, delta: &Seal) -> HubResult<IndexStamp<T>>;
      /// Re-adopt a stamp read back from an index directory: `Refused` for another tier, `StaleStamp` for other seals; any admission digest.
      pub fn adopt(&self, spec: &IndexSpec, found: &PersistedStamp) -> HubResult<IndexStamp<T>>;
  }
  impl<T: Tier> IndexStamp<T> {
      pub fn id(&self) -> StampId;                              // blake3 of the canonical stamp, tier and digest included
      pub fn dir(&self) -> IndexDir;                            // index/<kind>/<collection>/<tier>/<stamp id>/
      pub fn persisted(&self) -> PersistedStamp;                // written into the directory with the index
  }
  pub fn check_persisted<T: Tier>(want: &IndexStamp<T>, found: &PersistedStamp) -> HubResult<()>;
  pub struct EmbeddingStamp {
      pub definition: DefinitionHash,        // the ingest definition that embedded the corpus (SYS-068); resolves in the registry
      pub space: EmbeddingSpaceId,           // blake3 of the canonical EmbeddingSpace below
  }
  pub struct EmbeddingSpace { model_id, revision, weights_blake3, dimensions, truncation, quantization }
  ```

  **Every paid read goes through the gate, and no query takes a stamp.** The query service pins one `GenerationRef` per query (DES-012). A lab query mints its scope from `TierViews::lab`; a paid query calls `PaidTier` (section 1.2), which mints a fresh paid scope for every call from the opt-out log as it stands, and no caller ever holds one. The query methods `search`, `neighbours`, `resolve`, `capabilities` and `refresh` take a `&Scoped<T, GenerationRef>` and an `IndexSpec`, never an `IndexStamp`. A build writes to `scope.stamp(spec)?.dir()`; a read lists the spec's builds over the scope's seals and adopts the newest (`adopt`). So the directory a backend opens covers the seals of this query, and anything else answers `StaleStamp` (SYS-018, SYS-021). A stamp a caller kept from an earlier build cannot be passed to a query (E0308), and there is no stamp-from-stamp conversion. A scope expires at the query deadline (`query_deadline`, configuration; 30 s *(estimate)*), after which `stamp` answers `StaleStamp`. Since only `PaidTier` holds paid scopes, that expiry bounds the gate's own calls; the opt-out window is that of section 1.2. The backend id is part of the stamp, so after a swap the new backend reports the old stamps as stale and the existing rebuild path runs: indexes are rebuildable from sealed products alone (SYS-021), which is what makes an index swap free for callers. The two hashes are separate so that the ingest definition stays recoverable from the stamp on its own, while query-time matching uses only the space (section 4.5).

  **The tier is in the stamp's value and in its path, not only in its type.** No struct literal of `IndexStamp` compiles outside `hub-boundary` (E0451), and there is no conversion between tiers, so an `IndexStamp<Lab>` cannot become an `IndexStamp<Paid>`; the only way to obtain a paid stamp is from a `Scoped<Paid, GenerationRef>`, which only `TierViews::paid` mints (section 1.1). Every index lives in `index/<kind>/<collection>/<tier>/<stamp id>/`, and the stamp id hashes the tier, so a lab build and a paid build of the same generation, analyzer and backend never share a directory and never collide. Every index directory holds its `PersistedStamp`; before serving, every backend calls `check_persisted` against the stamp its query's scope yields, and a directory that holds a lab build (copied, restored or left by an older layout) answers a paid search with `Refused`, never with rows the opt-out excluded.

  **Admission and withdrawal** follow [the paid read rule](#the-paid-read-rule) of section 1.2. A paid index records the `ExclusionDigest` of the admission its build ran under (`admitted_under`, in its id and directory). A paid index admitted under an earlier cycle is served through the rule, not refused. A source or item without a verdict is never admitted, whether no run listed it or a catalog lost its publish record ([adapters and pool](adapters-and-pool.md), section 3).
- **Stage portability.** No method takes a host, a bucket name or a model name. Locations are `ShardLocation`/`ObjectUrl` values built from configuration; models are named only by service definitions, and executors only by declared classes and capability tags (SYS-039, SYS-069, section 4.4).

### 1.1 Capabilities, the authority layer and its threat model

Some values are proofs: that a step is open in the ledger, that a base slot is free, that QC passed, that a query vector comes from the index's embedding space, that a generation passed the paid-tier gates. Each is a type in `hub-boundary` with private fields and no `Default`, `Clone`, `Deserialize` or public constructor. The code that mints them lives in `hub-boundary`'s `authority` module, as concrete types (`Steps`, `BaseSlots`, `QcGate`, `TierViews`, `QueryEmbedder`) over persistence traits that backends implement. A backend stores records; an authority writes its own records, checks the rule against them and mints.

```rust
#[cfg(feature = "composition-root")]   // the one entry point to the authorities (G2)
pub async fn compose(stores: Stores) -> HubResult<Authorities>;
// Stores { ledger, slots, catalog, registry, runtimes: Arc<dyn …> }   Authorities { steps, slots, qc, tiers, embedder }
/// Body, sequence, previous digest, and an unkeyed blake3 over the three; `from_parts` only under `backend-impl`.
pub struct Recorded<T> { body: T, seq: u64, prev: Blake3, digest: Blake3 }
```

Every authority constructor is private to `hub-boundary`; `compose` builds them all and, before it returns, replays each collection's slot log and the ledger's opt-out log against their heads recorded in the other store (below). It may run more than once in a process: besides a per-instance high-water mark of each log it has replayed, an authority keeps no state, since every mint re-reads its store and every reservation is a create-only append at its sequence number, so of two racing instances one gets `Conflict`. That is what lets each conformance case compose its own authorities under libtest (section 5). `hub-compose` calls it once, in `main`.

**Threat model.** The design stops *accidental* misuse by the hub's own crates (a write without provenance, a fourth base, a paid search of a lab index, a store wired by hand) and stops a *buggy* store from making an authority mint. A *deliberately malicious* crate inside the workspace (one that edits the workspace table or the check, or calls itself a backend) and a *malicious* store linked into the process (which can read and write the process's memory) are **out of scope**: Rust cannot stop either, and a key held in the same process would not change that, so the design holds none. What holds, and by which mechanism:

| | Guarantee | Mechanism | Enforced by |
|---|---|---|---|
| G1 | No crate outside `hub-boundary` builds a capability, an `IndexStamp`, a `Recorded` or an authority | private fields and constructors | **the type system**: E0451, E0624, E0599 |
| G2 | Only `hub-compose`, `hub-boundary-conformance`, and the test, example, bench and **doctest** targets of listed backends (through their dev-dependency on the conformance crate, which doctests also build with) can call `compose` | `compose` is the only way to an authority, and exists only under `hub-boundary`'s feature `composition-root` | **the type system** for a target built without the feature (E0425); **the enforced check** below for every way the feature can reach a crate or target, `cargo test --workspace` feature unification included |
| G3 | Only listed backends (any target) and `hub-compose`, which reaches the feature through them, can implement a persistence trait | each persistence trait (`RunLedger`, `BaseSlotStore`, `EmbeddingRuntimes`) has the supertrait `seal::Backend`, public only under the feature `backend-impl`, which also gates `Recorded::from_parts` | **the type system** without the feature (E0277, E0599); **the enforced check** for who reaches it |
| G4 | A buggy store cannot make an authority mint, or admit a row of a source without a recorded allow verdict or of an item without a recorded `Clear` | every record is `Recorded` and every log hash-chained; the authority checks each digest and the chain, replays the log and evaluates the rule over its own replay, and takes no count, verdict, cycle or source set from a caller, a store's summary or the catalog; a paid row is admitted only by its own source's recorded allow verdict and, for an item row, its item's recorded `Clear`, both in the one hash-chained opt-out log (section 1.2) | **the type system** (no authority method takes a count, a cycle or a source set) and the faulty-store suite of section 5: a corrupted, hidden, reordered or other-cycle record, or a log shorter than its recorded head, is `Integrity`; a missing source or item verdict excludes its rows, and a lost `Reserved` is `Integrity` |
| G5 | No paid read path returns a row that [the paid read rule](#the-paid-read-rule) does not serve. Every scan applies the set current when it starts, and every batch a set at most `exclusion_max_age` (≤ the query deadline) old; held providers, sessions and streams are included (section 1.2) | `PaidTier` is the only holder of paid scopes and returns only filtered batches and guard types, which re-derive the set per scan and per batch | **the type system** (a paid scope outside the gate, E0624; a held stamp into a query, E0308; a stamp built from another, E0451; a paid session's context, E0616); **`hub-boundary` at runtime** (the guard); the paid-gate suite of section 5 (TEST-151, TEST-152) |
| — | The hub's own crates do not forge on purpose | review; the enforced check fails CI on any new reach for a gated feature, so none lands unnoticed | **documentation only** |

An unkeyed hash detects a corrupted, truncated or mixed-up record, not one a store fabricated with a matching digest; a key would not help there, since it would sit in the same process. So the design has no MAC, key ids or key rotation.

**What the authority cannot detect: a consistent rollback of both stores.** The two authority logs live in different stores and each records its head (sequence and digest) in the other: the slot log lives with the catalog in `keep` and `BaseSlots` records its head in the run ledger (SQLite on `state`); the opt-out log lives in the ledger and every `Steps` append to it records its head in `keep` (`BaseSlotStore::put_opt_out_head`). `compose` refuses a log shorter than its recorded head (`Integrity`), and within one instance an authority refuses a log shorter than one it has already replayed. So a ledger that loses its newest record (a `CycleCompleted` or an item's `Reserved`, through a lost WAL tail or a stale read) cannot make the gate serve under the previous state. A restore that rolls **both** stores back to a consistent earlier point passes these checks: a forgotten reservation can then grant a fourth base, and a forgotten cycle can serve rows that cycle withdrew. SYS-072 does not cover this: it governs the age of the off-anvil copy, not base counts. The proposed mitigation is to count, at start and after every restore, the base objects under `keep`'s create-only `base/` prefix and grant nothing while they exceed the replayed count. For cycles, the restore runbook re-runs the gate-2 step before paid serving resumes. Recovery from a log shorter than its head (a lost WAL tail) is an operator step, not automatic: the operator re-runs the lost step (gate 2 for a cycle; for slots, a reconcile of reservations from the `keep` listing), then re-anchors the head with an audited `hub authority reanchor` command recorded in the ledger; until then `compose` refuses to start, by design. Both are open question C-007 ([#27](https://github.com/nerdmachines/scitadel-hub/issues/27)), which names the conformance cases.

**The enforced check (part of TEST-094).** It reads `cargo metadata`, `cargo tree` and the workspace's `[workspace.metadata.hub]` table (`composition_root = ["hub-compose"]`, `test_root = ["hub-boundary-conformance"]`, `backends = [...]`, the mutant backends included). Round 3's rules asked only which crate *declares* a gated feature, which misses a crate that depends on the bin-only `hub-compose`: cargo warns "ignoring invalid dependency … missing a lib target", yet still unifies `hub-compose`'s feature requests, so the crate gets both features without declaring either (probe 3). The rules therefore ask **who reaches** a feature:
- **R1, enablers.** In `cargo tree --workspace -e features -i hub-boundary --all-features --target all --no-dedupe` (every optional feature on, every target's dependencies, every path printed in full rather than elided as `(*)`, so a crate feature `admin = ["hub-boundary/composition-root"]` or a `[target.'cfg(…)'.dependencies]` entry is seen), `composition-root` is requested directly, by a package or by one of its features, only by `hub-compose` and `hub-boundary-conformance`, and `backend-impl` only by the listed backends.
- **R2, reach.** Every package below a gated feature in that inverted tree, so every crate that gets it directly or through any chain of dependencies, is in that feature's reach set: for `composition-root`, `hub-compose`, the conformance crate and the listed backends (whose test targets run its suites, R3); for `backend-impl`, the listed backends and `hub-compose`.
- **R3, manifests.** No crate declares a dependency of any kind on `hub-compose`; `hub-boundary-conformance` is declared only as a dev-dependency, and only by a listed backend.
- **R4, build alone.** Every workspace member other than `hub-compose`, the conformance crate and the listed backends, `hub-boundary` included, passes `cargo check -p <crate> --all-targets` on its own, and every listed backend passes `cargo check -p <backend> --lib --bins` (resolver 2 resolves features per selected package, so a target that leans on a feature another crate enabled fails). `--all-targets` is what catches a featureless crate whose `tests/` or `examples/` implement a persistence trait and call `compose`: under `cargo test --workspace` feature unification builds it with both features (probe 4). Every such member with a library target also passes `cargo test -p <crate> --doc` on its own. `--all-targets` does not build doctests, and cargo refuses `--doc --no-run` (probe 5). A doctest that implements a hub-owned trait and calls `compose` passes `cargo test --workspace --doc` through feature unification, and fails alone with E0425.
- **R5, paid serving.** A crate listed in `paid_serving = [...]` (the paid protocol server and the MCP handlers) depends only on `hub-boundary` without features and on the protocol crate: no `datafusion`, no backend and no gated feature, so it cannot build a `TableProvider`, `MemTable` or `SessionContext`. Its only hub input is `PaidServing` (section 1.2). `hub-boundary` itself re-exports only an allowlist of data types (`RecordBatch`, `SchemaRef`, `ArrayRef`, `SendableRecordBatchStream`). It never re-exports a crate root (`pub use datafusion`, `pub extern crate`) or `TableProvider`, `MemTable` or `SessionContext`; the check parses `hub-boundary`'s `pub use` items and fails on anything else. R5 cannot see a paid-serving crate that keeps delivered batches in its own memory across requests. That is **documentation only** (the server holds no rows beyond a request), checked by the case `paid_server_holds_no_rows_across_requests`.

Beside them runs the existing rule: no crate except `hub-compose` depends on a backend crate.

| Capability | Minted only by | Rule the authority checks itself before minting | Record (the authority writes it, a backend stores it) | Consumed by |
|---|---|---|---|---|
| `ProvContext` | `Steps::started` | the run's `RunRecord` is open, with every input pinned and every definition resolvable (SYS-057, SYS-068) | `RunRecord` and `StepRecord` through `RunLedger::put_run` and `RunLedger::put_step` (DES-014); the context is minted from the authority's own record, never from a store's answer | every write |
| `BaseBuildPermit` | `BaseSlots::reserve`, `BaseSlots::resume` | the authority's own count over the replayed slot log: at most three bases on the tier, a pinned retired base counted (SYS-073) | `SlotEvent` through `BaseSlotStore::append_slot_event` (DES-012) | every base path of section 2.4 |
| `QcPass` | `QcGate::certify` | a passing `QcRecord` for exactly that generation (SYS-060) | `QcRecord`, written by `Steps::record_qc` at the end of the QC step | `GenerationCatalog::promote` |
| `QueryVector` | `QueryEmbedder::embed` | the definition's embedding space equals the index's (SYS-071) | none; the space comes from the registry and the stamp (DES-016) | `VectorIndex::search` |
| `Scoped<Paid, GenerationRef>` | `TierViews::paid` (`pub(crate)`), called only by `PaidTier`, once per gate call | the `ExclusionView` evaluates [the paid read rule](#the-paid-read-rule) over the replayed, chain-checked opt-out log. The scope carries the resulting `ExclusionSet` (with the classes), its `ExclusionDigest` and its expiry. A generation without an admission is `Refused` (SYS-054, SYS-055, vig-os/scitadel#330) | `OptOutEvent` (`Steps::commit_paid_admission`, the paid build's last act; `Steps::record_opt_out`, gate 2; `Steps::record_item_verdict`, gate 3; `Steps::complete_opt_out_cycle`) | every `…<Paid>` trait, through `PaidTier` only; the only source of an `IndexStamp<Paid>` |
| `Scoped<Lab, GenerationRef>` | `TierViews::lab` | none: every row of a generation has passed the licence gate at parse (SYS-001), so the lab scope is the whole generation | none | every `…<Lab>` trait, compaction |

- **Why not a sealed minting trait per backend.** Sealing restricts who *implements* a trait, not who mints, and it would copy the policy (slot arithmetic, space match, gate 6) into every backend. The policy lives once, in the authorities; sealing restricts who may *store* (G3). Backends check what a capability *says* (a permit's generation against the shard's, `Conflict` otherwise), and the suites test that.
- **Lifetimes.** A permit is not persisted; its reservation event is. A resumed run gets a permit for its own reservation from `BaseSlots::resume(run)`, which mints only for a reservation the authority finds for that run in the replayed log (SYS-061). An abandoned candidate appends a release.
- **Proof (probe 3: rustc 1.99.0 b940084d7, cargo 1.99.0; six crates with no external dependencies: `boundary`, `backend`, the bin-only `compose`, `conformance`, `illegal` and the reviewer's `forge2`).**
  - **The reviewer's forge, reproduced.** `forge2`'s manifest is `boundary` and `compose` as path dependencies, with no features. Cargo prints "ignoring invalid dependency `compose` which is missing a lib target"; `cargo run -p forge2` exits 0 and prints "forged 12 BaseBuildPermits" from a store that forgets every reservation. `cargo tree -e features -i boundary` shows both features reaching `forge2` through `compose`.
  - **Round 3's check misses it; this one does not.** With `forge2` in the workspace, round 3's check (declared features plus build alone) exits 0, and the check above exits 1, naming `forge2` three times (R2 for each feature, R3 for the dependency on `compose`). Without `forge2`, both exit 0. A crate `sneaky` with a feature `admin = ["boundary/composition-root"]` and a `cfg(windows)` dependency enabling `backend-impl` is missed by the default-build tree; with `--all-features --target all` the check exits 1 with R1 and R2 for both features, where round 3's check flags only the `backend-impl` entry.
  - **Compile-fail codes, each exit 101:** `compose` without the feature, E0425; `BaseSlots::new` outside `boundary`, E0624; a struct literal of `IndexStamp<Paid>`, E0451.
  - **Tests compose.** One libtest process runs `fourth_base_waits`, `paid_index_of_previous_cycle_filters_withdrawn_rows` and `cycle_without_withdrawal_filters_nothing` (the case names since #28), each with its own `compose`: exit 0. A ledger returning another cycle's verdict made `paid` fail with `Integrity`.
  - **Probe 4 (round 5; same toolchain; a sync, dependency-free sketch of section 1 and section 2.6 with crates `boundary`, `backend`, `compose`, `conformance`, `testforge`, `illegal`).** *Held stamp:* built under cycle 1 over rows of sources A and B, then A opts out in cycle 2. Round 4's shape, `search(&held_cycle1_stamp)`, returns `Ok([A rowA, B rowB])`, exit 0. The new shape, `search(&tiers.paid(g)?, &spec)`, returns `StaleStamp`, exit 1; after the paid rebuild it returns `Ok([B rowB])`, exit 0; `refresh` after the flip is `StaleStamp`, exit 1; a cycle-1 scope held past its TTL is `StaleStamp`, exit 1 (inside the TTL it is still served, exit 0: the residual of G5). Passing the held stamp to `search` fails with E0308 and building a stamp from another with E0451, each exit 101; `held_paid_stamp_after_cycle_flip_is_stale` passes under libtest. A source C with rows but no verdict is never admitted. *Test targets:* `testforge` (no features) implements `RunLedger` in `tests/` and calls `compose`; `cargo test --workspace` runs it, exit 0. Round 4's check exits 0, the check above exits 1 (R4 names `testforge`). A backend whose library calls `compose` fails R4's `--lib --bins` build with E0425, exit 101. A crate `rider` depending on a backend reaches `composition-root` through the conformance dev-dependency; without `--no-dedupe` that path is elided as `(*)` and R2 reports only `backend-impl`, with it R2 reports both. *Superseded in part by D-010 (section 1.2):* a flip now filters through the gate instead of refusing, and no caller holds a scope, so the TTL residual is gone.
  - **Probes 1 and 2 stand** where the design did not change: capability literals E0451, private `mint` E0624, permit clone E0308, base path without permit E0061/E0063, lab scope or stamp into a paid index E0308, persistence impl outside a backend E0277, backend-gated `from_parts` E0599, the round-1 sketch E0038. All are compile-fail cases of section 5.

### 1.2 Paid reads: one gate over a recorded exclusion view (DES-057, DES-058)

**The owner's decision (D-010, 2026-11-19): filter now, purge on rebuild.** A recorded withdrawal of a source or an item applies at query time at once, on every paid read path, and is re-checked per scan and per batch, held providers and sessions included. Rows are physically purged from paid indexes at the next rebuild. A newly allowed source invalidates nothing; it appears after the next rebuild. The window is at most one in-flight query deadline, and it is disclosed. Earlier rounds closed one read path at a time and the next review found another (a held stamp, a held scope within its TTL, a `TableProvider` from `table`, `union` or `merged`, a caller-kept `SessionContext`, an unrecorded item deny-list, a catalog-derived source set, `refresh` carrying an old predicate). This section therefore puts **one mechanism** in front of every path, and the table below lists each path with its case.

#### The paid read rule

This is the **single normative definition** of what a paid read serves. It realises D-010. Every other place in the design links here and does not restate it.

The rule is evaluated per source and per item, at query time, over the replayed and chain-checked opt-out log. Two terms come first:
- A **verdict** is a source's `Allow` or `OptedOut`, or an item's `Clear` or `Reserved`. A **withdrawal** is an `OptedOut` or a `Reserved`.
- **`E(g)`** is the position in the log of `g`'s newest committed `Admission` record. A generation with no admission is not served (`Refused`), and the paid tier pins the newest generation that has one.

The rule has three parts:
1. **`admitted(g)`, fixed when `g` is admitted.** A verdict is *settled* at `E` if it was recorded in a cycle that completed before `E`. Every verdict names the cycle of the run that recorded it, and that must be the current cycle: a source verdict names the open cycle (the newest cycle the log has opened, not yet completed); an item verdict carries the cycle of its ingest run, whose gate-2 step completes before the run's first fetch (DES-020), so it names no cycle the log has not opened. A verdict naming any other cycle, such as an `Allow` for a cycle already completed, is never read as settled: every read fails with `Integrity`.
   - **Build.** For a full rebuild, x is admitted iff its newest verdict before `E(g)` is a settled `Allow` or `Clear`, and, for a source, that `Allow` belongs to the newest cycle completed before `E(g)`. The newest verdict counts whatever its cycle's state. So a withdrawal from a running or aborted cycle keeps x out, and so does an `Allow` from a cycle that has not completed.
   - **Refresh.** The refresh's `Admission` names its parent, which must be `g`'s newest admission at `E2`; any other parent, including a sequence number that is not in the log, makes every read of `g` fail with `Integrity` (it is never read as a build). The refresh's set starts from the parent's set, with three changes:
     - **Withdrawn since the parent:** every x with a withdrawal recorded between the two admissions is removed.
     - **Unchecked sources:** a source that a cycle completed between the two admissions has no `Allow` for before `E2` is removed (a SYS-055 violation; it fails closed by dropping the source, which returns only through a rebuild).
     - **First-seen items:** an item first seen in the refresh's delta is added iff three conditions hold: its source is in the resulting set and not withdrawn; its newest verdict is a settled `Clear`; and no `Reserved` has ever been recorded for it.

     A refresh never adds a source and never re-adds an item that was ever withdrawn; those return only through a full rebuild.
2. **`withdrawn(now)` holds iff x's newest recorded verdict, as of now, is a withdrawal**, whether or not its cycle or gate-2 step has completed.
3. **`withdrawn_since(g)` holds iff a withdrawal of x is recorded after `E(g)`.**

**A row of `g` is served iff, for every input x of the row (its source and item, and those of every row it derives from): x ∈ `admitted(g)` ∧ ¬`withdrawn(now)` ∧ ¬`withdrawn_since(g)`.**

Why it is consistent:
- **Admission requires a verdict that is not a withdrawal.** So for an admitted x, `withdrawn(now)` implies `withdrawn_since(g)`. The third term adds only one thing: a withdrawal stays in force for `g` even after a later re-allow.
- **The third term is needed.** Without it, x admitted, then withdrawn, then allowed again with no rebuild in between would be served again, since x ∈ `admitted(g)` and its newest verdict is an allow. A new allow would then bypass the rebuild.
- **Additions and removals take different routes.** The served set grows only through a full rebuild, plus a refresh for items never seen before and never reserved. It shrinks as soon as a withdrawal is recorded. The rule is a function of the log and `g` alone, the same on every path, and takes nothing from the catalog, a caller or a store's summary.
- **SYS-021 holds on the paid tier.** A delta's new items have settled `Clear` verdicts once their run's fetch is done, because the run's cycle completed before its first fetch. The refresh that makes the delta searchable, ≤ 1 h after its seal *(estimate)*, therefore admits them, and its rows are served on every path at that admission.

Edge cases, each with its case in the paid-gate suite:
- **A withdrawal in a running or aborted cycle, then a rebuild:** not admitted (build rule) and withdrawn (`withdrawn(now)`). Case: `optout_before_rebuild_in_incomplete_cycle_is_filtered`.
- **A re-allow in a running cycle after an `OptedOut` from an aborted cycle, then a rebuild:** not admitted, because the `Allow` is not settled. Case: `reallow_in_incomplete_cycle_after_aborted_optout_not_admitted`.
- **A withdrawal between an admission and a refresh:** subtracted by the refresh and withdrawn since the parent. Cases: `withdrawal_between_admission_and_refresh_is_filtered`, for a source and for an item.
- **A re-allow after a withdrawal:** not served after a refresh, and served only after a full rebuild whose `E(g)` follows the completion of the cycle that allows it. Case: `reallow_after_withdrawal_appears_after_rebuild_only`.
- **A withdrawal while gate 2 is still running, with no rebuild:** filtered at once. Case: `optout_recorded_while_cycle_incomplete_is_filtered`.
- **A source allowed after `E(g)`:** absent on every path until the rebuild. Cases: `newly_allowed_source_appears_after_rebuild_only`, `refresh_never_adds_source`.
- **An item first seen in a delta:**
  - With a settled `Clear` and an admitted source, it is served after the refresh. Case: `refresh_adds_first_seen_clear_item_of_admitted_source`.
  - If it was ever `Reserved`, it is served only after a rebuild. Case: `refresh_never_readds_previously_reserved_item`.
- **A completed cycle with no verdict for an admitted source:** the source is still served until the next refresh or rebuild, since nothing was recorded (D-010 governs recorded withdrawals). The next refresh drops it, and so does the next build. Case: `refresh_drops_source_missing_from_completed_cycle`.
- **A refresh whose parent is not `g`'s newest admission, or is not in the log:** `Integrity`. Cases: `refresh_from_stale_parent_is_integrity`, `refresh_from_dangling_parent_is_integrity`.
- **A verdict naming a cycle other than the current one:** `Integrity`. Case: `stray_allow_for_old_cycle_is_integrity`.
- **A late `Allow`, recorded after `E2` for a cycle that dropped the source:** it does not re-admit the source; only a rebuild does. Case: `late_allow_after_refresh_does_not_readmit_dropped_source`.
- **A first-seen item whose `Clear` is not settled, or whose source the refresh dropped:** not added. Cases: `refresh_skips_first_seen_item_with_unsettled_clear`, `refresh_never_adds_first_seen_item_of_dropped_source`.
- **A lost or reordered record, or a log shorter than its head in `keep`:** `Integrity`, and nothing is served.

**Item verdicts are recorded (DES-058).** Gate 3 records `Clear` or `Reserved` for every fetched item through `Steps::record_item_verdict`, in the same hash-chained opt-out log as the source verdicts, cycle completions and admissions. Every append also moves the log's head kept in `keep`. A missing record fails closed: an item row with no recorded `Clear` is not admitted. A store that loses a recorded `Reserved` or `OptedOut` either breaks the chain or leaves the log shorter than its head, so the next scan answers `Integrity` and every paid read refuses until the operator re-runs the step. The recovery is the one in section 1.1; a consistent rollback of both stores remains C-007.

**Derived rows inherit.** Every row derived from another carries the `source` and `item` of each row it was derived from, through `RowProv` (DES-009). This covers chunks, embeddings, figures and their descriptions, graph edges (the citing item) and region crops. A row derived from several inputs is withdrawn when any input is, so `withdrawn(now)` removes a withdrawn item's derived rows wherever they are read. The graph cache keeps each node's `prov_id` beside the node key (an endpoint always resolves to a work row, DES-027), and `neighbours` returns `node_prov` with every row. The guard checks the edge and both endpoints, so neither the vector leg (embedding rows) nor the graph leg returns the key of a withdrawn item.

```rust
pub enum OptOutEvent {
    SourceVerdict { cycle: CycleId, source: SourceId, verdict: Allow | OptedOut, evidence: Blake3 },
    ItemVerdict { cycle: CycleId, item: ItemKey, verdict: Clear | Reserved, evidence: Blake3 },   // gate 3, cycle of its run; ItemKey { source, upstream_id }
    CycleCompleted { cycle: CycleId },
    Admission { generation: GenerationId, parent: Option<u64> },                 // a paid build's last act; `parent` for a refresh
}
/// The sets of the paid read rule (below) for one generation at one epoch of the replayed log. Private fields.
pub struct ExclusionSet { admission: (u64, Blake3), admitted: AdmittedSet, withdrawn: WithdrawnSet, epoch: (u64, Blake3) }
impl ExclusionSet { pub fn digest(&self) -> ExclusionDigest; pub fn admits(&self, prov: &RowProvView) -> bool; }

/// Authority, built by `compose`; the only reader of the opt-out log for paid reads.
pub(crate) struct ExclusionView { ledger: Arc<dyn RunLedger>, slots: Arc<dyn BaseSlotStore>, max_age: Duration }
impl ExclusionView {
    /// Reads the log head; replays new records against the chain and keep's head (Integrity on any mismatch); g's admission.
    async fn for_scan(&self, g: &GenerationRef) -> HubResult<Arc<ExclusionSet>>;
    /// The newest snapshot for g while younger than `max_age` (exclusion_max_age, at most the query deadline), else `for_scan`.
    async fn for_batch(&self, g: &GenerationRef) -> HubResult<Arc<ExclusionSet>>;
}

/// The only way to a paid read (DES-057): concrete, built by `compose`, and the only holder of paid scopes.
pub struct PaidTier { view: ExclusionView, vector: Arc<dyn VectorIndex<Paid>>, text: Arc<dyn TextIndex<Paid>>,
                      graph: Arc<dyn GraphIndex<Paid>>, keys: Arc<dyn KeyedRefs<Paid>>, scan: Arc<dyn TableScan<Paid>>,
                      renders: Arc<dyn RenderService>, query_deadline: Duration }
impl PaidTier {
    pub async fn current(&self, c: &CollectionId) -> HubResult<GenerationRef>;   // newest generation with a committed admission
    pub async fn vector_search(&self, g: &GenerationRef, spec: &IndexSpec, q: &QueryVector, k: usize, f: Option<&RowFilter>) -> HubResult<RecordBatch>;
    pub async fn text_search(&self, g: &GenerationRef, spec: &IndexSpec, query: &str, k: usize, f: Option<&RowFilter>) -> HubResult<RecordBatch>;
    pub async fn resolve(&self, g: &GenerationRef, spec: &IndexSpec, block: &BlockName, keys: &ArrayRef) -> HubResult<RecordBatch>;
    pub async fn neighbours(&self, g: &GenerationRef, spec: &IndexSpec, seeds: &ArrayRef, kinds: &EdgeKindSet, depth: u8, dir: Direction) -> HubResult<GuardedStream>;
    pub fn capabilities(&self, g: &GenerationRef, spec: &IndexSpec) -> HubResult<VectorCapabilities>;   // reports `opt_out_window`
    pub async fn coverage(&self, g: &GenerationRef) -> HubResult<Coverage>;                              // sources admitted and not withdrawn
    pub async fn table(&self, g: &GenerationRef, p: &ProductHandle, b: &BlockName, o: &ScanOptions) -> HubResult<Arc<GuardedProvider>>;
    pub async fn union(&self, g: &GenerationRef, b: &BlockName, o: &ScanOptions) -> HubResult<Arc<GuardedProvider>>;
    pub async fn merged(&self, g: &GenerationRef, b: &BlockName, o: &ScanOptions) -> HubResult<Arc<GuardedProvider>>;
    pub async fn session(&self, g: &GenerationRef) -> HubResult<PaidSession>;
    /// A region crop for an extraction report (DES-039): the element is resolved through the guard first, then rendered.
    pub async fn crop(&self, g: &GenerationRef, element: &ScalarKey, region: &Region) -> HubResult<Crop>;
    pub async fn build_text(&self, g: &GenerationRef, /* as TextIndex::build */ prov: &ProvContext) -> HubResult<IndexStamp<Paid>>;
    pub async fn refresh_text(&self, g: &GenerationRef, spec: &IndexSpec, delta: &Seal, prov: &ProvContext) -> HubResult<IndexStamp<Paid>>;
    // build_vector, build_graph and build_keys likewise; the build step ends with Steps::commit_paid_admission
}
/// What the paid protocol server and MCP handlers are given: private fields, minted by `compose`.
pub struct PaidServing { paid: PaidTier, embedder: QueryEmbedder }
// GuardedProvider: impl TableProvider; statistics() is None; filters Inexact; each scan() calls for_scan and returns a GuardedExec.
// GuardedExec: a leaf ExecutionPlan that owns the backend's plan privately and executes it itself; children() is empty,
//   with_new_children accepts only none, statistics are Statistics::new_unknown, so no optimiser rule rewrites below it and
//   the aggregate-statistics rule cannot answer count(*), min or max without running it. Every batch goes through for_batch;
//   rows the set does not admit are removed (the guard projects prov_id and drops it again if the caller did not ask for it).
// GuardedStream: the same check per batch; ends with StaleStamp at the query deadline, as does GuardedExec.
// PaidSession: owns its SessionContext (private field), built with URL tables off and registering only GuardedProviders and the
//   guarded bm25 function; sql(&str) runs sql_with_options with DDL, DML and statements disabled, so CREATE EXTERNAL TABLE,
//   COPY, INSERT and SET are refused; no register, cache or access to the context.
```

**Why one mechanism covers every path.** Each guarantee names its mechanism, under the threat model of section 1.1:
- **The type system: no unguarded paid value reaches a caller.**
  - `TierViews::paid` and every constructor of `Scoped<Paid, _>` are `pub(crate)` and called only by `PaidTier`. Every `…<Paid>` trait method takes a `&Scoped<Paid, _>`, so a crate that holds an `Arc<dyn TextIndex<Paid>>` still cannot call it (E0624 for the mint; there is no other way to get a scope).
  - Every `PaidTier` method returns a batch it has already filtered or a guard type. None returns a backend's provider, stream or session.
  - A stamp kept by a caller still cannot be passed anywhere (E0308), and no caller can hold a paid scope, so round 6's TTL residual no longer exists.
- **The paid service holds nothing else (type system and the enforced check).**
  - The paid protocol server and the MCP handlers have one constructor, which takes `PaidServing`. `PaidServing` has private fields, is minted only by `compose`, and holds `PaidTier` and `QueryEmbedder`, with no `TierViews`, lab scope, `dyn …` backend or `ArtefactStore`. The server crate cannot mint any of those itself (G1, G2).
  - Rule R5 of TEST-094 (section 1.1) keeps it from building a raw table: a crate listed as `paid_serving` depends only on `hub-boundary`, without features, and the protocol crate. With no `datafusion` and no backend, it cannot construct a `TableProvider`, `MemTable` or `SessionContext` to hold or cache rows.
- **`hub-boundary` at runtime: re-checked per scan and per batch.**
  - Each `scan()` of a `GuardedProvider` re-reads the log head, so a provider held across a withdrawal, or registered in a session, excludes it on its next scan.
  - Every batch of a `GuardedExec` or `GuardedStream` is checked against a snapshot at most `max_age` old.
  - Every guard counts the rows it removes (`paid_guard_removed_rows`). The backends also apply the scope's set inside each index, so outside the window a non-zero count is a backend bug and raises an alert.
- **The guard is a leaf, above the merge.**
  - `GuardedExec` exposes no children and no statistics. DataFusion's optimiser therefore cannot move work below it or answer an aggregate from statistics.
  - It wraps the plan of the provider the backend returns, after the newest-wins rule of `merged` (DES-005). An excluded newest row therefore hides its key and never uncovers an older, superseded version (SYS-005).
- **Admission is fixed per generation, withdrawal is query-time** ([the paid read rule](#the-paid-read-rule)). `IndexStamp.admitted_under` is the `ExclusionDigest` of the admission its build ran under, in the stamp id and directory, so a rebuild never overwrites the index being served. `adopt` accepts any admitted digest, because the guard decides what is served.
  - A paid index whose generation has a newer committed admission is still served, with the newest admission and withdrawals applied, and is never refused for its cycle.
  - `refresh` admits only its delta's rows and is never refused for a withdrawal.
  - The orchestrator schedules a full paid rebuild, the purge, after every completed cycle that withdrew a source and every recorded `Reserved`, at the next rebuild of SYS-021 (≤ 24 h *(estimate)*).
  - An index is stale only when it does not cover the pinned generation's seals (SYS-021).

**The window and its disclosure.** A withdrawal is recorded when its record and head are committed. It is then excluded from every scan that starts after the commit: each scan reads the log head. It is also excluded from every batch emitted more than `exclusion_max_age` after the commit, because a batch never uses a snapshot older than that. `exclusion_max_age` is configuration of at most the query deadline (30 s *(estimate)*), and every paid stream, `GuardedExec` and session ends at that deadline. So no paid read emits a withdrawn row later than `exclusion_max_age` after its record is committed. Responses delivered before then are not recalled: search results, `get` records, a crop, a detached copy (DES-051) and a client's local subset (DES-052). `capabilities` reports the window as `opt_out_window`, and the hub's published TDM statement names it (an owner action).

**Every paid read path.** The cases are named in the paid-gate suite of section 5 and verified by TEST-151 (paths) and TEST-152 (the exclusion view).
- **The fixture** is the CC0 corpus with sources A and B; items with `Clear`, with `Reserved` and with no verdict; and a key whose newest delta row comes from an item.
- **Each row's case** obtains its value, then makes three changes: it records A `OptedOut` while gate 2 of the cycle is still running, completes a cycle without A, and records one item `Reserved`.
- **Pass criterion,** unless a row says otherwise: 0 rows of A, of the reserved item or of the item with no verdict are returned, and the row count equals the reference backend's under the new sets.
- **The edge cases of [the paid read rule](#the-paid-read-rule) run on every row with rows** (rows 1–4, 7–12, 17, 18 and 21) and are not repeated in the table: `optout_recorded_while_cycle_incomplete_is_filtered`, `optout_before_rebuild_in_incomplete_cycle_is_filtered`, `reallow_in_incomplete_cycle_after_aborted_optout_not_admitted`, `withdrawal_between_admission_and_refresh_is_filtered`, `reallow_after_withdrawal_appears_after_rebuild_only`, `newly_allowed_source_appears_after_rebuild_only`, `refresh_never_adds_source`, `refresh_adds_first_seen_clear_item_of_admitted_source`, `refresh_never_readds_previously_reserved_item` and `refresh_drops_source_missing_from_completed_cycle`.

| # | Path (caller-facing) | Before #28 | Mechanism now | Case: method and pass criterion |
|---|---|---|---|---|
| 1 | `VectorIndex::search` (protocol `search`, vector leg) | scope held for its TTL; an index of an earlier cycle refused | `PaidTier::vector_search`: fresh scope, set applied in the index, guard re-check | `withdrawn_row_not_served_via_vector_search`: search the index admitted before the withdrawal; `withdrawn_item_id_not_returned_by_vector_or_graph_leg`: 0 keys of the reserved item from embedding rows |
| 2 | `TextIndex::search` (`search`, BM25 leg) | as 1 | `PaidTier::text_search`, as 1 | `withdrawn_row_not_served_via_text_search` |
| 3 | `KeyedRefs::resolve` (protocol `get`) | as 1 | `PaidTier::resolve`, as 1 | `withdrawn_row_not_served_via_resolve`: `get` of every fixture key |
| 4 | `GraphIndex::neighbours` (protocol `neighbours`) | stream outlived the scope | `GuardedStream`, per batch; edge and both endpoints checked | `withdrawn_row_not_served_via_neighbours` (0 edges to or from the reserved item); `in_flight_stream_applies_withdrawal_within_window`: withdrawal between two batches at an injected clock; 0 withdrawn rows in batches after `max_age` |
| 5 | `VectorIndex::capabilities` (protocol `capabilities`) | no rows | no rows; reports the window | `capabilities_reports_opt_out_window`: the field equals the configured `exclusion_max_age` |
| 6 | protocol `coverage` | catalog's list | `PaidTier::coverage`: sources admitted and not withdrawn | `withdrawn_source_absent_from_coverage` |
| 7 | `TableScan::table` | predicate applied once when created; a held provider served | `GuardedProvider` restricted to `admitted(g)`: per scan and per batch | `held_paid_table_provider_after_cycle_flip_filters_row`: provider obtained before the withdrawal, scanned after |
| 8 | `TableScan::union` | as 7 | as 7 | `held_paid_union_provider_after_withdrawal_filters_row` |
| 9 | `TableScan::merged` | as 7 | as 7, guard above the merge | `held_paid_merged_provider_after_withdrawal_filters_row`; `withdrawn_newest_row_does_not_resurface_older_version`: the key is absent, not its base version |
| 10 | `TextIndex::register` into a `SessionContext` (DES-025) | registered into a caller-kept context, never re-checked | `PaidSession` owns its context; guarded providers and `bm25` only | `registered_session_after_withdrawal_filters_row`: session opened before the withdrawal, queried after; compile-fail `paid_session_context_private` (E0616) |
| 11 | SQL over a paid session (filters, joins, aggregates, DDL) | as 10 | rows removed in every `GuardedExec` leaf of the plan; no children and no statistics exposed; DDL, DML and statements refused | `aggregate_over_paid_session_excludes_withdrawn_rows`: `count(*)` per source equals the reference's; `aggregate_without_group_by_respects_withdrawal`: `count(*)`, `min(key)` and `max(key)` with no `GROUP BY` equal the reference's under the new sets; `paid_session_refuses_create_external_table`: `CREATE EXTERNAL TABLE`, `COPY` and `INSERT` are refused, and 0 tables are added |
| 12 | media columns (`figures` through `TableScan`, DES-011) | as 7 | as 7 | `withdrawn_figure_not_served_via_table`: 0 `figures` rows or bytes of A |
| 13 | `ProductStore::open`, `RemoteRead::open` (`ProductHandle`) | no rows; rows through `TableScan` | rows only through `PaidTier::table`; a paid product scope is minted only inside it | compile-fail `paid_product_scope_outside_gate` (E0624) |
| 14 | index `build` and `refresh` (admission) | `refresh` carried the old predicate forward (round 4) | a build or a refresh commits `g`'s admission under [the paid read rule](#the-paid-read-rule); a refresh adds only first-seen, never-reserved items | `refresh_after_withdrawal_admits_under_current_set`; `item_without_clear_verdict_not_admitted`; `refresh_from_stale_parent_is_integrity`; `refresh_from_dangling_parent_is_integrity` |
| 15 | a stamp a caller kept | E0308; the old index refused | E0308 still; the old index served through the guard | compile-fail `search_with_held_stamp` (E0308); `paid_index_of_previous_cycle_filters_withdrawn_rows` |
| 16 | a paid scope a caller kept | served within its TTL | no caller can mint or hold one | compile-fail `mint_paid_scope_outside_gate` (E0624) |
| 17 | protocol `detach` / `export` (DES-051) | not designed | built from `PaidTier::resolve` and `table` | `withdrawn_row_not_served_via_detach`; a copy delivered before the withdrawal is not recalled (disclosed) |
| 18 | the protocol and the MCP server end to end (DES-032, DES-034) | not designed | every handler holds `PaidServing` only | `withdrawn_row_not_served_via_protocol`: rows 1 to 6, 17 and 21 repeated over HTTP and the MCP tools |
| 19 | `ProvenanceSink::explain`, `select_by_definition` (untiered) | not designed | not a paid read: ingest and operator use only; `PaidServing` holds no `ProvenanceSink`; a response's provenance comes from the guarded row's `prov_id` | **the type system** (the constructor) and **the enforced check** R5; `paid_service_holds_only_paid_serving` |
| 20 | a lab view or a raw provider in the paid service | wiring only | not reachable: `PaidServing` holds no `TierViews` or backend, and R5 forbids `datafusion` in a paid-serving crate | **the type system** and **the enforced check** R5; the R5 cases of TEST-094 (a paid-serving crate that depends on `datafusion`, a backend or a feature of `hub-boundary` fails the check) |
| 21 | region crops shown to a reporting user (DES-039, extraction-cascade.md section 2) | gated "like any other content", mechanism not named | `PaidTier::crop`: the element is resolved through the guard, then rendered from the kept artefact; the render cache is never served without that resolve; the paid service holds no `ArtefactStore` | `withdrawn_crop_not_shown_to_reporting_user`: a crop of the reserved item's element and of A's is refused (`NotFound`), and no cached crop is returned |
| 22 | lab tier, compaction (`…<Lab>`) | — | not a paid read; not reachable from `PaidServing` (row 20) | — |

**Probe 5 (#28): [`probes/paid-read-model/`](probes/paid-read-model/README.md).** A sync, dependency-free sketch that encodes the rule and every case of the table above that it can express. `./check.sh` runs 305 checks and compares each exit code with the documented one; with rustc and cargo 1.99.0 all match (exit 0).
- **Before.** Each case runs on the shape that served it:
  - the round-6 shape, for the historical holes: held stamp, scope, providers and session, a lost item reservation, a catalog-derived source set, `refresh`, a guard below the merge, an unchecked graph endpoint, an unguarded crop, an aggregate answered from statistics, and DDL;
  - round 1's rule, for `b1`, `b2` and `reallow`;
  - round 2's rule, for `b1_rebuild`, `refresh_src` and `refresh_item`;
  - round 3's rule, for `x1`, `unchecked`, `stale_parent` and `first_seen` (round 3 never added the item, missing SYS-021).
- **After.** Every case is served before (exit 0) and filtered (3) or refused (4) after, on every path. The `*_after_rebuild` cases serve the re-admitted source or item (0) only after a rebuild, `first_seen` serves a first-seen item after its refresh (0), and a batch inside `max_age` is the disclosed window (0).
- **Compile-fail cases** exit 101: E0624, E0308, E0616.
- **R4.** `docforge`'s doctest calls `compose`. `cargo test --workspace --doc` and round 6's `cargo check --all-targets` pass (exit 0), while `cargo test -p docforge --doc` fails with E0425 (101). Cargo refuses `cargo test --doc --no-run`, so R4 runs the doctests.
- **R5.** A paid-serving crate that depends on `datafusion` is rejected, and so is a crate-root re-export in `boundary`'s source.
- **Not modelled:** DataFusion's planner beyond the effect of `children()` and `statistics()`, the transports, and blake3.

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
// ProductHandle (an opaque hub-boundary type): seal(), role(), blocks() -> the logical blocks of the contract,
//   schema(&BlockName) -> SchemaRef, the contract schema (figures_schema() for `figures`). No manifest() accessor.
```

- **Invariants.** A sealed shard is immutable; its seal is tessera's manifest hash and its file blake3 is recorded in the ledger. `ProductSpec` declares every block's Arrow schema up front and `push` refuses a batch that differs. `finish` requires the provenance blocks of DES-009, so no product seals without them. The role is written into the manifest metadata (`hub.role.v1`: the permit's generation and reservation, or base seal and sequence) and returned in `SealedShard`; an `Index` shard (the IVF file of DES-006) can never be published into a collection. Block names and schemas follow the document model of SYS-008; the `figures` block has the fixed contract of DES-011, and no block may hold PDF bytes. **The handle shows the contract, never the encoding.** `blocks()` lists the logical blocks of the `ProductSpec` and `schema()` returns their contract schemas, on every backend: the interim's `media-pack/*` blobs, the `pack`, `offset` and `length` columns of the stored `figures` block, and the `hub.*` manifest keys are visible only inside the backend and in `verify`'s `VerifyReport` for operators. Callers therefore never see what disappears on the swap. `ProductSpec` refuses a binary column (`Binary`, `LargeBinary`, `BinaryView`) in any block other than `figures.bytes`.
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

- **Invariants.** Reads are tier-scoped like indexes (section 1). A `<Paid>` scan is reached only through `PaidTier::table`, `union` and `merged`. These return a `GuardedProvider` that applies the current `ExclusionSet` on every scan and every batch, above the merge (section 1.2), so a provider held past a flip or registered in a session does not return a withdrawn row. Every scan reads only sealed bytes and verifies each block digest before use unless the handle was verified at open (`VerifyBlocks` is the default, as in tessera's decision record 0062). Memory is bounded by `max_leaves_in_flight` leaves, never the whole table. The scan exposes the provenance and licence columns of every block (SYS-028, SYS-052) so that the query service can attach them to each record; a projection that drops `prov_id` or `licence_class` is refused for any plan that returns records.
- **Backs it:** [vig-os/tessera#654](https://github.com/vig-os/tessera/issues/654) (sliced into tessera issues 666, 667 and 668: pushdown, zip, multi-product and object store).
- **Interim: hub-built (tessera does not ship it).** Tessera's `tessera sql` materialises into a DataFusion `MemTable` (`tessera-cli/src/sql.rs`), which is not bounded. The hub builds a streaming `TableProvider` over what does ship: `LogicalTableView` and `select_blocks_overlapping` (`tessera-io/src/multiblock.rs`) to choose leaves, `decode_projected` per leaf (`tessera-io/src/table.rs`, at most 2²² rows per leaf), and the int64 chunk statistics of `tessera-core/src/chunk_index.rs` for pruning; filters are reported to DataFusion as `Inexact` and re-applied above the scan. `get` reaches rows through the key index of DES-004 and decodes only the leaves that hold them; whether that meets SYS-025 and SYS-022 without pushdown is spike S-002.
- **On the swap:** nothing; `table`, `union` and `merged` return a `TableProvider` either way, and the conformance suite compares results row for row.
- **Failure modes.** `Integrity` on a digest mismatch (the query fails; it never returns unverified rows); `NotFound` for an unknown block; `Transient` on an I/O error.

### 2.3 `KeyedRefs`: declared keys and references across shards (DES-004)

```rust
#[async_trait]
pub trait KeyedRefs<T: Tier>: Send + Sync + 'static {
    /// key -> (seal, block, row) for the pinned generation; at most 100 keys per call (SYS-025).
    async fn resolve(&self, g: &Scoped<T, GenerationRef>, spec: &IndexSpec, block: &BlockName, keys: &ArrayRef)
        -> HubResult<RecordBatch>;
    async fn build(&self, g: &Scoped<T, GenerationRef>, prov: &ProvContext) -> HubResult<IndexStamp<T>>;
    async fn dangling(&self, g: &Scoped<T, GenerationRef>) -> HubResult<DanglingReport>;
}
```

- **Invariants.** A key column is declared in `ProductSpec`, unique within a product and sorted; the writer checks both and refuses otherwise. References (an embedding row to its chunk, an edge endpoint to its work, a retraction flag to a DOI or PMID, SYS-010) name their target block and key. `resolve` answers only for the generation it is given, so a superseded row cannot come back (SYS-005). A sealed generation has 0 dangling references.
- **Backs it:** [vig-os/tessera#780](https://github.com/vig-os/tessera/issues/780) (`TableSpec.keys`, `references`, a key-to-product aux cache, `verify --references`).
- **Interim: hub-built (tessera does not ship it; `RowAlignment` is positional only).** The declaration is written into the product's manifest metadata under `hub.keys.v1`; the key index is a sorted key → (seal, leaf, row) file in `index/keys/<collection>/<tier>/<stamp id>/`, stamped like any index and rebuilt from the products.
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
- **The pin rule (SYS-073): every base path takes the permit.** A `BaseBuildPermit` is minted only by `BaseSlots` (section 1.1), and only while the authority's own count over the replayed slot log shows at most three bases on the tier, a pinned retired base counted. Every path that can produce, publish or promote a base requires a permit. No caller can therefore produce a fourth base by mistake: a permit cannot be built outside `hub-boundary` (G1), the authority can be built only by `hub-compose` (G2), and a buggy store cannot raise the count (G4). What remains is a consistent rollback of both the slot log and the ledger, open question C-007 (section 1.1):

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
    async fn search(&self, g: &Scoped<T, GenerationRef>, spec: &IndexSpec, q: &QueryVector, k: usize,
                    filter: Option<&RowFilter>) -> HubResult<RecordBatch>; // key, score, seal, prov_id
    fn capabilities(&self, g: &Scoped<T, GenerationRef>, spec: &IndexSpec) -> HubResult<VectorCapabilities>; // method, embedding stamp
}
```

- **Invariants.** The embeddings of an index generation come from exactly one ingest definition; its hash and its embedding space are the stamp's `embedding`, and the IVF parameters are `index_params`. `search` opens only the directory of `g.stamp(spec)?` and checks the stamp persisted there (`check_persisted`: `Refused` for another tier, `StaleStamp` for other seals; a paid index of any admitted digest is served through the guard, section 1.2). It refuses with `ModelMismatch` a `QueryVector` whose space differs from `spec.embedding`'s (SYS-071, the rule of section 4.5): no mixed-model results, no fallback model. The method chosen is reported in `capabilities` (SYS-019). Recall against exact scan is a pass criterion of the suite, not a hope.
- **Backs it:** [vig-os/tessera#769](https://github.com/vig-os/tessera/issues/769) (tier 0 exact scan through a `vec_distance` UDF, tier 1 IVF-flat as a sealed centroids product, tier 2 HNSW as an aux cache), on top of [#768](https://github.com/vig-os/tessera/issues/768) (declared `vector{dim, dtype}` columns).
- **Interim: hub-built (tessera ships neither; `tessera-ingest/src/arrow_table.rs` refuses `FixedSizeList` wider than 8 and `ColumnData` has no binary type).**
  - *Storage, inside `.tsra`:* the embeddings product holds a table block (key, chunk ordinal, definition hash, `prov_id`) and the vectors as one tessera blob block per leaf (`tessera-core/src/block/blob.rs`), row-aligned little-endian fp16, whose digest tessera verifies (a deviation from the "native fixed-size lists" of L2 infrastructure section 5 until #768, C-001). The reader exposes them as Arrow `FixedSizeListArray` through `EmbeddingSource`. Nothing leaves `.tsra`.
  - *Exact scan:* in-crate SIMD over those arrays, also the reference for recall.
  - *IVF-flat:* one sealed `.tsra` file per index generation under `index/ann/<collection>/<tier>/<stamp id>/`: the centroids, and per-list postings (list id as an int64 column, so that tessera's shipped int64 chunk statistics prune the lists to probe, then key, seal, leaf and row). It holds **no copy of the vectors**; a probe reads them in place from the hot embeddings products. It is Vortex-encoded as SYS-019 asks, local and never in a bucket as SYS-012 asks, rebuildable, and small (about 16 bytes per vector), so the 0.2 B index estimate of L2 infrastructure section 2.4 holds. That section's premise that the lists live in the products, which would put index bytes on S3, is C-005. The HNSW cache is not built unless S-001 shows IVF-flat cannot meet the budget.
- **On the swap:** nothing for callers. Embedding products are re-sealed with native vector columns by an ordinary run under a base permit (a new generation through promotion), and the IVF file is rebuilt; old stamps report `StaleStamp` until then.
- **Failure modes.** `ModelMismatch`; `StaleStamp`; `Invalid` for a dimension mismatch; `Transient` on I/O. The query service answers a failed or late vector leg BM25-only and flags it (SYS-071).

### 2.6 `TextIndex`: BM25 (DES-007)

```rust
#[async_trait]
pub trait TextIndex<T: Tier>: Send + Sync + 'static {
    async fn build(&self, g: &Scoped<T, GenerationRef>, block: &BlockName, column: &str, analyzer: &AnalyzerConfig,
                   prov: &ProvContext) -> HubResult<IndexStamp<T>>;
    /// `g` is the scope of the generation that ends in `delta`: opens `g.stamp_before(spec, delta)`, writes `g.stamp(spec)`.
    async fn refresh(&self, g: &Scoped<T, GenerationRef>, spec: &IndexSpec, delta: &Seal, prov: &ProvContext)
        -> HubResult<IndexStamp<T>>;
    async fn search(&self, g: &Scoped<T, GenerationRef>, spec: &IndexSpec, query: &str, k: usize,
                    filter: Option<&RowFilter>) -> HubResult<RecordBatch>; // key, score, seal, prov_id, snippet offsets
    /// Registers `bm25(block, column, query, k)` as a DataFusion table function in the query's own session; paid: only `PaidSession`, guarded.
    fn register(&self, ctx: &SessionContext, g: &Scoped<T, GenerationRef>, spec: &IndexSpec) -> HubResult<()>;
}
```

- **Invariants.** The stamp's `index_params` is the analyzer configuration hash, so a changed analyzer is a new index, never a silent mix. `search` and `refresh` check the persisted stamp as `VectorIndex::search` does. A paid `refresh` commits its admission under [the paid read rule](#the-paid-read-rule) of section 1.2, which adds no source and only first-seen, never-reserved items, and indexes its delta's rows under it. Withdrawals are excluded at query time on every row (section 1.2), so no refresh carries an old predicate into what is served. Every method that returns an `IndexStamp` (`build` and `refresh` here, and `build` of `VectorIndex`, `GraphIndex` and `KeyedRefs`) takes a scope and obtains it from `stamp`. `refresh` makes a delta searchable within 1 h of its seal *(estimate)* (SYS-021) by adding a segment for the delta and masking superseded keys; a full rebuild is the fallback. Results compose with filters through the table function (SYS-018).
- **Backs it:** [vig-os/tessera#775](https://github.com/vig-os/tessera/issues/775) (declared `text_index{column, analyzer}`, tantivy as an aux cache stamped `built_from`, the `bm25` table function).
- **Interim: hub-built, tantivy directly (tessera does not ship text indexing).** One tantivy index per stamp under `index/bm25/<collection>/<tier>/<stamp id>/`, on local NVMe and never over S3 (SYS-012), stamp in the same `built_from` shape #775 proposes. Snippets are cut from the product's text column, not stored twice.
- **On the swap:** nothing for callers; the tessera backend rebuilds from the products, the old index is stale by backend id and is removed by the index sweep.
- **Failure modes.** `StaleStamp`; `Invalid` for a query the analyzer cannot parse (reported, never widened); `Integrity` when a hit's key does not resolve in the pinned generation.

### 2.7 `GraphIndex`: typed edge tables and adjacency (DES-008)

```rust
#[async_trait]
pub trait GraphIndex<T: Tier>: Send + Sync + 'static {
    async fn build(&self, g: &Scoped<T, GenerationRef>, kinds: &EdgeKindSet, prov: &ProvContext) -> HubResult<IndexStamp<T>>;
    /// Depth 1 or 2 (SYS-020), by edge kind and direction.
    async fn neighbours(&self, g: &Scoped<T, GenerationRef>, spec: &IndexSpec, seeds: &ArrayRef, kinds: &EdgeKindSet,
                        depth: u8, dir: Direction)
        -> HubResult<SendableRecordBatchStream>; // seed, node, node_prov, kind, depth, via, edge seal, prov_id, licence_class
}
```

- **Invariants.** Edges are product rows, not index state: tables with columns `src`, `dst`, `kind` (and an optional `weight`) in the convention #776 proposes, for work cites work, patent cites patent, patent cites paper and has-CPC (SYS-020). Endpoints are keys (DES-004). Every returned edge carries the seal, `prov_id` and licence class of its edge row, as every record does (SYS-028). The adjacency is a derived cache. **No graph database** (XADR-SCITADEL-008 §4).
- **Backs it:** [vig-os/tessera#776](https://github.com/vig-os/tessera/issues/776) (edge convention, CSR and reverse CSR as an aux cache, `neighbours` table function).
- **Interim: hub-built (tessera does not ship it).** A forward and a reverse CSR per edge kind, built from the edge tables: a node dictionary (key → ordinal) plus `UInt64` offsets and `UInt32` targets as Arrow arrays, persisted in `index/graph/<collection>/<tier>/<stamp id>/` as Arrow IPC files. That file format is an **internal cache that never leaves the hub**: rebuildable, never a product, never served.
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
// RowProv { source, extractor, tier_reached, definition_hash, artefact: Option<ArtefactRef>, licence_class,
//           item: Option<ItemKey> }   // set for a row from an item-level fetch (gate 3, section 1.2); required when `artefact` is;
//   a derived row (chunk, embedding, figure, edge, crop) carries the source and item of every row it derives from (section 1.2)
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
//   bytes: BinaryView, field metadata {"hub.media_type_column": "media_type"}   (a hub-owned key, below)

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

- **No separate backend trait.** One write path and one read path: the encoding of `bytes` belongs to the `ProductStore` backend (on `push` of `figures`) and the `TableScan` backend (which reads `bytes` only when projected), and the suite runs through those two. `FiguresBuilder::put` is synchronous because it does no I/O; its batch goes through the async `push` of `Box<dyn ProductWriter>`.

- **The metadata key is the hub's.** #779 decides that the media type can come from a sibling column (`media_type_column`), but it does not fix a field-metadata key name. `hub.media_type_column` is therefore a hub-owned key, in the `hub.*` namespace like `hub.role.v1`. **Migration note:** if #779 settles on a different key, the tessera backend's `TableScan` still exposes `hub.media_type_column` (and may expose tessera's key beside it), so callers keep reading the hub key and nothing changes for them. Asking #779 to fix the name is an architect follow-up; this pull request does not comment on tessera.
- **Invariants.** Figures are stored lossless only and decode to the pixels (or SVG) of the source (SYS-008). The media-type set is closed, and **the check runs where the bytes enter a product**: `ProductWriter::push` of the `figures` block, on every backend. There it refuses (`Refused`) any row whose `media_type` is `application/pdf` or unlisted, or whose bytes do not carry the signature of their declared type (PNG and JPEG XL magic numbers, an SVG root element; so a `%PDF-` value labelled `image/png` is refused), and it recomputes `media_hash`. `FiguresBuilder::put` runs the same check early, for a better error, but the guarantee rests on `push`, which a hand-built batch cannot bypass. A binary column in any other block is refused by `ProductSpec` (section 2.1). So no product holds PDF bytes in a binary value, and no call can serve them (D-007, SYS-032); the `pdf_refused` cases cover both `put` and `push`. A value above 16 MiB *(estimate; #779's default cap)* is `Invalid`. Every row carries its `media_hash`, the licence class of its work and a `prov_id` naming the step and the raw artefact it was extracted from (`source_blake3`); `put` refuses a value without a licence class, and a `figures` block without `prov_id` does not seal (DES-009). `TableScan` exposes exactly `figures_schema()` for every backend.
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
    /// Copies keep -> hot for shards `keep` already records as published; never creates, publishes or promotes a base.
    async fn reconcile(&self, prov: &ProvContext) -> HubResult<ReconcileReport>; // keep wins
}
pub enum Publish<'a> { Base { shard: &'a SealedShard, permit: &'a BaseBuildPermit }, Delta { shard: &'a SealedShard } }
pub enum PromoteTarget { Base(BaseBuildPermit), Deltas(GenerationId) }

/// Persistence behind the BaseSlots authority (section 1.1); implemented by the catalog's backend. Stores, never counts.
#[async_trait]
pub trait BaseSlotStore: seal::Backend + Send + Sync + 'static {
    /// The collection's slot log: recorded, sequence-numbered, hash-chained events
    /// (reserved, released, published, promoted, retired with its pin expiry, pin expired).
    async fn slot_log(&self, c: &CollectionId) -> HubResult<Vec<Recorded<SlotEvent>>>;
    /// Create-only at the event's sequence number: `Conflict` if taken, so of two racing runs one wins.
    async fn append_slot_event(&self, c: &CollectionId, e: &Recorded<SlotEvent>) -> HubResult<()>;
    /// The head of the ledger's opt-out log, moved on every append and kept in `keep`, so a lost tail is detected (section 1.1).
    async fn put_opt_out_head(&self, head: &Recorded<OptOutHead>) -> HubResult<()>;
    async fn opt_out_head(&self) -> HubResult<Option<Recorded<OptOutHead>>>;
}
// GenerationInfo { id, seals, publishes: Vec<PublishRecord { seal, run, step, reservation }> }
// authority (built by `compose`, section 1.1): BaseSlots::reserve(c, run, now) -> SlotDecision = Granted(BaseBuildPermit) | Wait { until, reason }
//            BaseSlots::resume(run) -> Option<BaseBuildPermit>; BaseSlots::release(permit)
```

- **Invariants.** The layout `base/<release>/`, `delta/<date>.tsra`, `current` (SYS-002). `publish_shard` never moves `current`. A reader resolves `current` once per query and pins that `GenerationRef`, so it sees the old or the new generation, never a mix. `promote` consumes a `QcPass` (minted only by `QcGate`) for the same generation, and for a new base the permit too; `PromoteTarget::Deltas` is refused (`Invalid`) for a generation whose base is not the current one. `rollback` is refused for a base no longer on the tier; a base restored from cold is a base build with its own permit. `BaseSlots::reserve` (in `hub-boundary`) replays the slot log, checking every digest and the chain, counts a retired base as the previous one while a snapshot pins it, computes the pin's expiry from the snapshot schedule in configuration (L2 infrastructure section 2.4), and returns `Wait` while the count would exceed three; the orchestrator records the wait and its expected end in the ledger and raises an alert if the wait exceeds the longest snapshot retention. Every object `publish_shard` writes to `keep` carries the run and step ids of its `ProvContext` in its metadata and is recorded against that step in the ledger. Retention deletes are **not** a method here: they belong to the retention role (SYS-017), a separate credential. **`reconcile` takes a `ProvContext` and no permit, and cannot produce or promote a base.** It runs as a ledger step (`RunKind::Reconcile`); it repairs only the hot copy, rewriting hot objects from `keep` for shards whose `keep` object carries a publish record (run, step and, for a base, the reservation of the permit it was published with), and it verifies each copy against the seal in that record. A `keep` object without a publish record is `Integrity`, and it is reported, not mirrored. `reconcile` re-points the hot `current` only to the generation that `keep`'s `current` already names, so it adds no base and does not move `keep`'s `current`. Every copy is recorded against its step in the ledger, so the repair has its own provenance.
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
pub trait RunLedger: seal::Backend + Send + Sync + 'static {
    /// Stores the run record `Steps::open_run` wrote (kind, pinned inputs and sources, cycle, definition hashes); create-only.
    async fn put_run(&self, r: &Recorded<RunRecord>) -> HubResult<()>;
    async fn run(&self, id: &RunId) -> HubResult<Option<Recorded<RunRecord>>>;
    /// Stores the record the `Steps` authority wrote; create-only per (run, step), `Conflict` otherwise.
    async fn put_step(&self, r: &Recorded<StepRecord>) -> HubResult<()>;
    async fn step_completed(&self, run: &RunId, step: &StepKey, outputs: &[OutputHash]) -> HubResult<()>;
    async fn resume_point(&self, run: &RunId) -> HubResult<ResumePlan>;
    async fn spend(&self, run: &RunId, step: &StepKey, s: &Spend) -> HubResult<()>;   // idempotent per step
    async fn enqueue(&self, item: &QueueItem) -> HubResult<()>;
    async fn record_wait(&self, run: &RunId, until: Timestamp, reason: &WaitReason) -> HubResult<()>;
    async fn put_qc(&self, r: &Recorded<QcRecord>) -> HubResult<()>;
    async fn qc_verdict(&self, g: &GenerationId) -> HubResult<Option<Recorded<QcRecord>>>;
    /// The opt-out log of section 1.2 (source verdicts, item verdicts, cycle completions): one hash chain, create-only per sequence.
    async fn put_opt_out(&self, r: &Recorded<OptOutEvent>) -> HubResult<()>;
    async fn opt_out_log(&self, after_seq: u64) -> HubResult<Vec<Recorded<OptOutEvent>>>;
    async fn put_slot_head(&self, c: &CollectionId, head: &Recorded<SlotHead>) -> HubResult<()>;
    async fn slot_head(&self, c: &CollectionId) -> HubResult<Option<Recorded<SlotHead>>>;
    async fn gpu_submitted(&self, run: &RunId, job: &GpuJobRecord) -> HubResult<()>;
    async fn gpu_job_ended(&self, job: &GpuJobId, hashes: &[FileHash]) -> HubResult<()>; // hub-computed
}
// authorities (built by `compose`, section 1.1): Steps::open_run(kind, pins, defs) -> RunId;
//   Steps::started(run, step) -> ProvContext; Steps::record_qc(&prov, g, verdict); QcGate::certify(g) -> QcPass;
//   Steps::record_opt_out(&prov, source, verdict);   // the cycle is the one the run record of `prov` names
//   Steps::record_item_verdict(&prov, item, verdict, evidence);   // gate 3: Clear or Reserved, per fetched item
//   Steps::complete_opt_out_cycle(&prov) -> CycleId; // gate 2's last act: cycle current; every append writes the head to `keep`
//   Steps::commit_paid_admission(&prov, g);        // a paid build's or refresh's last act: fixes admitted(g) (section 1.2)
// TierViews { ledger: Arc<dyn RunLedger>, slots: Arc<dyn BaseSlotStore>, query_deadline: Duration }, likewise `lab(g)`; no catalog:
//   pub(crate) async fn paid(&self, g: &GenerationRef) -> HubResult<Scoped<Paid, GenerationRef>>;  // PaidTier only; no cycle or source parameter
```

- **Invariants.** A run record exists before step 1, with every input pinned by version or snapshot date and hash and every definition hash; an unpinned input refuses `Steps::open_run` (SYS-057). `Steps::started`, which writes its own `StepRecord` and stores it through `put_step`, is the only issuer of `ProvContext`. `QcGate` and `TierViews::paid` mint only from records whose digest and chain verify: a corrupted pass, a pass of another generation, a corrupted verdict or one of another cycle is `Integrity`, and a missing one is `Refused`. **`TierViews::paid` derives its own inputs, on every call:** from the replayed, chain-checked opt-out log, no shorter than the head kept in `keep` (a lost newest record is `Integrity`), it evaluates [the paid read rule](#the-paid-read-rule) of section 1.2. It takes no source set from anyone: the catalog's `PublishRecord`s are not recorded and the catalog is not sealed, so a lost record must not widen the scope, and with an allow-list it cannot, since a row whose source has no verdict is excluded by the predicate itself. `resume_point` skips completed steps whose outputs still verify (SYS-061); `spend` is keyed by step, so a resume never double-counts credits or budget. Queued T3 and T4 work lives here, not in a bucket (SYS-006). The GPU acceptance order of SYS-062 reads `gpu_submitted` and `gpu_job_ended` (DES-022).
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
    pub(crate) fn new(registry: Arc<dyn ServiceRegistry>, runtimes: Arc<dyn EmbeddingRuntimes>) -> Self; // by `compose`
    /// Embeds in the space of `target`, or refuses. Never another model.
    pub async fn embed(&self, text: &str, target: &IndexSpec, deadline: Instant) -> HubResult<QueryVector>;
}
/// Backend: loads the runtime a definition names and returns raw vectors.
#[async_trait]
pub trait EmbeddingRuntimes: seal::Backend + Send + Sync + 'static {
    async fn embed(&self, def: &ResolvedDefinition, text: &str, deadline: Instant) -> HubResult<Float32Array>;
}
// QueryVector { values, space: EmbeddingSpaceId, query_definition: DefinitionHash, index_definition: DefinitionHash }
```

- **The matching rule.** A query definition matches an index generation when their **embedding spaces are equal**: model id, revision, weights hash, dimensions, truncation and quantization, the model fields of SYS-067 and exactly the list of SYS-071. The definition hashes are *not* compared: a query definition legitimately differs from the ingest one in executor, runtime and its version, batching and limits (a CPU runtime in `vm-hub` against a `gpu_submit` batch executor), and each of those changes the hash. Numerical drift between two runtimes of one space is measured by TEST-091's recall@10 on the golden queries before a definition is enabled (SYS-071).
- **Invariants.** The query embedder is a **registry consumer** (D-009, SYS-071): it reads `target.embedding`'s space (`Invalid` for a spec without one), asks `ServiceRegistry::query_embedder_for` for the active definition of that space, checks that the definition's own space hashes to the same id, and embeds through `EmbeddingRuntimes`. No definition, or a runtime that returns another dimension, is `ModelMismatch` and the vector leg is refused. Both definition hashes, the query's and the index's ingest definition from the spec, travel in `QueryVector` into the response's provenance and `capabilities` (SYS-027). Clients never send vectors; the protocol rejects them before this trait is reached. It runs on CPU in `vm-hub`; a GPU executor is possible only by a definition that names one outside the serving microVM, after the benchmark and with the owner's approval (SYS-024). Missing the deadline is `Transient`, and the query service answers BM25-only, flagged (SYS-071).
- **Backends** (of `EmbeddingRuntimes`): the in-process CPU runtime the active definition names; a GPU-slot executor through the same definition mechanism; a deterministic fake for the suite. Which model is the default is decided by the benchmark of TEST-091 on anvil's RTX 5090 and the serving CPU, together with SYS-050, not here.
- **Failure modes.** `ModelMismatch`; `Transient` (timeout); `Integrity` when the loaded weights do not hash to the definition's.

## 5. The swap test (DES-017)

One crate, `hub-boundary-conformance`, holds one suite per trait, run against trait objects exactly as callers hold them: `pub async fn run(make: impl Fn() -> Arc<dyn TextIndex<Lab>>, fixtures: &Fixtures) -> SuiteReport` (and the `<Paid>` instance for the tier cases). Every backend crate calls the suite of each trait it implements from its own integration tests (a dev-dependency on `hub-boundary-conformance`, the check's `test_root`), and CI runs every backend on every pull request. The authority cases call `compose` themselves, each over fresh stores, so they run side by side in one libtest process. The fixtures are the CC0 fixture corpus (a base, three deltas with an update, a merge and a delete, figures in each media type, edges of each kind, embeddings from two spaces and two definitions of one space, rows of every licence class with and without an opt-out record) plus seeded corruptions.

**Pass criteria for every suite.** All named cases pass; results are compared with the reference backend (the interim one until tessera lands, then each other) **row for row** for deterministic traits and by **recall@10 ≥ 0.99 against exact scan** for approximate vector search; the error *kind* of every negative case equals the expected one.

| Suite | Named cases (each is one test function) |
|---|---|
| Capabilities (compile-fail, trybuild in `hub-boundary-conformance/tests/ui`; the expected error code is pinned) | `mint_permit_literal` (E0451), `mint_permit_private_fn` (E0624), `permit_not_clone` (E0308), `mint_prov_context_literal`, `mint_query_vector_literal`, `mint_qc_pass_literal`, `mint_paid_scope_literal` (each E0451), `search_with_held_stamp` (E0308), `create_base_without_permit` (E0061), `compact_without_permit` (E0061), `publish_base_without_permit` (E0063), `promote_base_without_permit` (E0061), `lab_scope_into_paid_index` (E0308), `stamp_literal` (E0451), `lab_stamp_into_paid_search` (E0308), `authority_new_outside_boundary` (E0624), `mint_paid_scope_outside_gate` (E0624), `paid_product_scope_outside_gate` (E0624), `paid_session_context_private` (E0616), `compose_without_feature` (E0425), `persistence_impl_outside_backend` (E0277), `recorded_from_parts_outside_backend` (E0599) |
| Authorities over faulty stores (runtime; the mutant stores are `hub-backend-mutants`, a listed backend that, like every backend, dev-depends on `hub-boundary-conformance`; the conformance crate depends on no backend) | `compose_twice_racing_reservations_one_wins`, `corrupted_step_record_is_integrity`, `corrupted_qc_record_is_integrity`, `qc_record_of_other_generation_is_integrity`, `corrupted_opt_out_verdict_is_integrity`, `missing_opt_out_verdict_refused`, `verdict_of_other_cycle_is_integrity`, `incomplete_cycle_is_not_current`, `source_without_allow_verdict_excluded` (a catalog that drops a run's publish record included), `gate_scope_past_deadline_is_stale`, `cycle_without_withdrawal_filters_nothing`, `truncated_opt_out_log_is_integrity`, `opt_out_log_shorter_than_keep_head_is_integrity`, `hidden_slot_event_is_integrity`, `reordered_slot_event_is_integrity`, `rolled_back_slot_log_is_integrity_within_instance`, `slot_log_shorter_than_ledger_head_is_integrity` |
| Paid gate (DES-057, TEST-151): one case per path of section 1.2 | `optout_recorded_while_cycle_incomplete_is_filtered`, `optout_before_rebuild_in_incomplete_cycle_is_filtered`, `withdrawal_between_admission_and_refresh_is_filtered`, `reallow_after_withdrawal_appears_after_rebuild_only` and `newly_allowed_source_appears_after_rebuild_only` (each on every path with rows), `withdrawn_row_not_served_via_vector_search`, `withdrawn_item_id_not_returned_by_vector_or_graph_leg`, `withdrawn_row_not_served_via_text_search`, `withdrawn_row_not_served_via_resolve`, `withdrawn_row_not_served_via_neighbours`, `in_flight_stream_applies_withdrawal_within_window`, `capabilities_reports_opt_out_window`, `withdrawn_source_absent_from_coverage`, `held_paid_table_provider_after_cycle_flip_filters_row`, `held_paid_union_provider_after_withdrawal_filters_row`, `held_paid_merged_provider_after_withdrawal_filters_row`, `withdrawn_newest_row_does_not_resurface_older_version`, `registered_session_after_withdrawal_filters_row`, `aggregate_over_paid_session_excludes_withdrawn_rows`, `aggregate_without_group_by_respects_withdrawal`, `paid_session_refuses_create_external_table`, `withdrawn_figure_not_served_via_table`, `withdrawn_crop_not_shown_to_reporting_user`, `refresh_after_withdrawal_admits_under_current_set`, `refresh_never_adds_source`, `refresh_adds_first_seen_clear_item_of_admitted_source`, `refresh_never_readds_previously_reserved_item`, `refresh_drops_source_missing_from_completed_cycle`, `refresh_from_stale_parent_is_integrity`, `refresh_from_dangling_parent_is_integrity`, `late_allow_after_refresh_does_not_readmit_dropped_source`, `refresh_skips_first_seen_item_with_unsettled_clear`, `refresh_never_adds_first_seen_item_of_dropped_source`, `reallow_in_incomplete_cycle_after_aborted_optout_not_admitted`, `paid_index_of_previous_cycle_filters_withdrawn_rows`, `withdrawn_row_not_served_via_detach`, `withdrawn_row_not_served_via_protocol`, `paid_service_holds_only_paid_serving`, `paid_server_holds_no_rows_across_requests` |
| Exclusion view over faulty stores (DES-058, TEST-152) | `lost_item_reservation_is_integrity`, `item_verdict_chain_break_is_integrity`, `stray_allow_for_old_cycle_is_integrity`, `item_without_clear_verdict_not_admitted`, `opt_out_log_shorter_than_keep_head_is_integrity`, `source_without_allow_verdict_excluded`, `generation_without_admission_refused`, `scan_rereads_opt_out_head`, `batch_snapshot_bounded_by_max_age` |
| `ProductStore` | `seal_roundtrip_is_bit_exact`, `seal_is_deterministic`, `push_refuses_schema_drift`, `finish_refuses_missing_provenance`, `verify_detects_flipped_byte`, `partial_write_never_opens`, `base_create_with_other_generation_permit_conflict`, `role_recorded_in_manifest`, `binary_column_outside_figures_refused`, `handle_shows_logical_blocks_only` |
| `TableScan` | `projection_and_filter_match_reference`, `pruning_skips_leaves`, `memory_bounded_by_leaves_in_flight`, `corrupt_block_fails_query`, `prov_and_licence_columns_always_present`, `paid_scope_applies_gate_six_predicate`, `shard_outside_scope_refused` |
| `KeyedRefs` | `resolve_hundred_keys`, `duplicate_key_refused`, `superseded_key_not_resolved`, `dangling_reference_reported`, `paid_resolve_skips_excluded_rows`, `paid_resolve_cannot_open_lab_index`, `paid_index_of_previous_cycle_filters_withdrawn_rows` |
| `DeltaStore` (reads through `TableScan::merged`) | `newest_wins`, `tombstone_hides_row`, `redirect_chain_followed`, `redirect_cycle_is_integrity`, `compaction_is_deterministic`, `compact_with_other_generation_permit_conflict`, `kill_mid_compaction_leaves_current_and_releases_slot` |
| `VectorIndex` | `exact_matches_brute_force`, `ann_recall_at_10`, `space_mismatch_refused`, `filter_respected`, `capabilities_report_method_and_embedding_stamp`, `lab_and_paid_builds_never_share_a_directory`, `paid_search_cannot_open_lab_index`, `paid_index_of_previous_cycle_filters_withdrawn_rows` |
| `TextIndex` | `bm25_scores_match_reference`, `analyzer_change_is_new_stamp`, `delta_refresh_masks_superseded`, `stale_stamp_refused`, `paid_search_cannot_open_lab_index`, `paid_index_of_previous_cycle_filters_withdrawn_rows`, `refresh_after_withdrawal_admits_under_current_set` |
| `GraphIndex` | `depth_one_and_two_by_kind`, `reverse_direction`, `unknown_kind_invalid`, `stale_stamp_refused`, `paid_neighbours_cannot_open_lab_index`, `paid_index_of_previous_cycle_filters_withdrawn_rows` |
| `ProvenanceSink` | `every_row_has_prov_id`, `explain_reaches_raw_hash_and_url`, `select_by_definition_equals_ledger`, `unresolvable_definition_refused` |
| `RemoteRead` | `open_matches_local`, `verify_detects_flipped_byte`, `transient_error_classified` |
| Media columns (`figures` through `ProductStore` and `TableScan`) | `figures_schema_identical_on_every_backend`, `lossless_roundtrip_per_type`, `pdf_refused` (through `put` and through `push` of a hand-built batch), `pdf_bytes_labelled_as_image_refused`, `unknown_type_refused`, `oversize_refused`, `missing_licence_class_refused`, `figures_without_prov_id_do_not_seal`, `blocks_grow_with_bytes_not_figures`, `bytes_not_read_unless_projected`, `media_hash_mismatch_is_integrity`, `handle_blocks_and_schema_are_the_contract` (`ProductHandle::blocks()` and `schema()` show no `media-pack/*` block and no `pack`, `offset` or `length` column) |
| `GenerationCatalog` and `BaseSlots` | `keep_before_hot`, `publish_never_moves_current`, `keep_objects_carry_run_and_step`, `promote_needs_qc_of_same_generation`, `no_mixed_generation_during_switch`, `fourth_base_waits`, `concurrent_reservations_one_wins`, `resume_reissues_own_reservation_only`, `publish_delta_of_base_shard_refused`, `deltas_promote_of_new_base_refused`, `rollback_to_absent_base_refused`, `reconcile_keep_wins`, `reconcile_never_adds_a_base`, `reconcile_records_provenance`, `reconcile_refuses_keep_object_without_publish_record` |
| `ArtefactStore` and `RawDrop` | `create_only_by_hash`, `intermediate_beside_old`, `quota_pauses`, `source_digest_hit_returns_artefact`, `conflicting_source_digest_is_integrity`, `drop_refuses_non_refetchable`, `drop_audited_before_delete` |
| `RunLedger` | `unpinned_input_refused`, `resume_skips_verified_steps`, `spend_not_double_counted`, `queue_survives_restart`, `opt_out_verdict_takes_the_run_cycle` |
| `ServiceRegistry` | the nine refusal cases of SYS-067, `sweep_on_shared_gpu_executor_refused`, `hash_is_canonical`, `every_version_resolvable` |
| `QueryEmbedder` over `EmbeddingRuntimes` | `space_match_ignores_runtime_and_executor`, `space_mismatch_refused_per_field` (one case per field of the space), `ingest_definition_recoverable_from_stamp`, `both_definition_hashes_in_provenance`, `timeout_is_transient` |

**The suite is itself tested.** For each trait a set of deliberately broken backends (one per invariant: a scan that drops `prov_id`, a merge that keeps tombstones, an index that ignores the stamp) must each fail at least one named case; a mutant that passes means a missing case (TEST-110). Together with the workspace check of section 1.1 (TEST-094), that is the swap test: a backend that passes its suite can replace another with no caller change, and nothing outside `hub-compose` can tell the difference.

**Unit-level expectations (L4).** Beside the suites: the Arrow-to-`ColumnData` conversion table (every supported type, every refused type); the redirect resolver on chains and cycles; the stamp equality rule; the canonical hashing of `EmbeddingSpace`; the slot arithmetic of `BaseSlots::reserve` with an injected clock; the canonical encoding and digest of every `Recorded` record; the slot-log and cycle-log replay on gaps, reorders and a shorter log; the stamp id over every field, tier and admission digest included; the gate-6 allow-list predicate on both polarities and its digest; the opt-out log replay on gaps, reorders and a shorter log; scope expiry and the guard's snapshot age with an injected clock; canonical definition hashing on reordered TOML; the fp16 blob layout against a reference encoder.

## 6. Verification

Every design here is verified by one integration test; all run in CI on fixtures unless the row says otherwise.

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-094 | DES-001 | Workspace check (`cargo metadata`, `cargo tree -e features -i hub-boundary --all-features --target all --no-dedupe`, `cargo check -p <crate> --all-targets` per crate, `cargo test -p <crate> --doc` per library crate, the dependency set of every `paid_serving` crate): only `hub-compose` depends on a backend crate, and rules R1 to R4 of section 1.1 (who requests and who reaches `composition-root` and `backend-impl`, no dependency on `hub-compose`, the conformance crate only as a backend's dev-dependency, every other crate builds alone with all its targets, R5 for paid-serving crates); `ErrorKind` mapping test per backend; the compile-fail capability cases and the authority suite over faulty stores of section 5 | 0 violations, a crate reaching a gated feature through the bin-only `hub-compose`, an optional feature, a target-specific dependency, an elided tree path or a test, example or doctest target included; 100 % of backend errors carry a kind; every compile-fail case fails with its pinned error code; every faulty store is refused with its expected kind. |
| TEST-151 | DES-057 | The paid-gate suite: one case per path of section 1.2 against the interim and the reference backends, each protocol case repeated over HTTP and the MCP tools, and its compile-fail cases | 0 rows of a withdrawn source (recorded `OptedOut`, cycle complete or not), a reserved item or an item with no verdict on any path after the withdrawal, held providers, sessions, streams, crops and derived rows included; 0 rows of a source allowed, or allowed again, after the generation's admission until its rebuild, on every path; a withdrawal between an admission and a refresh filtered; only batches inside `exclusion_max_age` may still carry one, and they are counted; every compile-fail case fails with its pinned code |
| TEST-152 | DES-058 | The exclusion-view cases over the mutant stores of section 5: a hidden, reordered or corrupted item verdict, a log shorter than its head in `keep`, a catalog without a source's publish record, an injected clock across `max_age` | every fault is `Integrity` before any row is served; a generation without an admission is `Refused`; a missing verdict excludes its rows; a scan created after a withdrawal never serves it; no batch after `max_age` serves it |
| TEST-095 | DES-002 | `ProductStore` suite against the tessera backend | all cases pass; bit-exact round trip |
| TEST-096 | DES-003 | `TableScan` suite, interim backend versus a `MemTable` reference | row-for-row equal; peak memory ≤ the leaf bound |
| TEST-097 | DES-004 | `KeyedRefs` suite | all cases pass |
| TEST-098 | DES-005 | `DeltaStore` suite, including a kill at every compaction step | 0 superseded rows; `current` unchanged after every kill |
| TEST-099 | DES-006 | `VectorIndex` suite; ksb timing on the SYS-063 slice | recall@10 ≥ 0.99 on fixtures; recall ≥ 0.95 and p95 ≤ 20 ms *(estimate)* on the slice |
| TEST-100 | DES-007 | `TextIndex` suite; ksb timing on the slice | all cases pass; p95 ≤ 50 ms *(estimate)* |
| TEST-101 | DES-008 | `GraphIndex` suite; ksb timing on the slice | all cases pass; depth-2 p95 ≤ 100 ms *(estimate)* |
| TEST-102 | DES-009 | `ProvenanceSink` suite; a 1,000-row sample traced to seal, raw hash and URL | 100 % resolved; selection set-equal to the ledger |
| TEST-103 | DES-010 | `RemoteRead` suite against a local S3 gateway in CI | all cases pass |
| TEST-104 | DES-011 | Media-columns suite through `ProductStore` (`push`, `ProductHandle::blocks()` and `schema()`) and `TableScan`, with PNG, JPEG XL, SVG and a PDF fixture (through `put` and as a hand-built batch, also labelled as an image), and a 10⁵-figure shard | `blocks()`, `schema()` and the scanned `figures` schema identical on every backend, with no encoding block or column; lossless for every type; PDF refused on every path; blob blocks per shard ≤ ⌈bytes / 256 MiB⌉ + 1 |
| TEST-105 | DES-012 | `GenerationCatalog` and `BaseSlots` suite with 100,000 reads during a switch, an injected snapshot clock and two runs reserving at once | 0 mixed reads; a fourth base waits until the computed expiry on every base path; one of two racing reservations wins |
| TEST-106 | DES-013 | `ArtefactStore` and `RawDrop` suite against the gateway and the directory backend | all cases pass; 0 deletions outside the drop rule |
| TEST-107 | DES-014 | `RunLedger` suite with a kill at every step boundary of a fixture run | identical output hashes; 0 double-counted spend |
| TEST-108 | DES-015 | `ServiceRegistry` suite including the negative cases | 0 invalid definitions accepted |
| TEST-109 | DES-016 | `QueryEmbedder` suite with the fake runtime: two spaces, and two definitions of one space differing only in runtime and executor | the two definitions of one space both accepted; every single-field change of the space refused; 0 mixed-model vectors; timeouts flagged BM25-only |
| TEST-110 | DES-017 | Mutation run: every broken backend through its suite | 100 % of mutants fail at least one case |
