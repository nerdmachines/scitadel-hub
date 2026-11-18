# L3: query engine

DataFusion as the one query engine, and how the logical table is composed from products. Source: XADR-SCITADEL-008 §3 (query engine: DataFusion), with the newest-wins read rule of §2.

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). Every DES below is `proposed`.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-025 | Logical table, newest-wins scan and the DataFusion session | SYS-022, SYS-025, SYS-034 | DES-003, DES-004, DES-005 |

## 1. Logical table and DataFusion session (DES-025)

DataFusion is tessera's public query API, is pure Rust and embeddable, reads OpenAlex's Parquet at ingest and reaches object storage through the `object_store` crate. DuckDB would add a C++ dependency and a second engine for no capability the hub needs (XADR-SCITADEL-008 §3).

- **One session type.** `QuerySession` in `hub-compose` registers one `TableProvider` per block through `TableScan` ([DES-003](tessera-boundary.md)); nothing else in the hub constructs a `SessionContext`. Callers see Arrow streams ([DES-001](tessera-boundary.md)).
- **Newest-wins is a plan, not a copy.** The logical table of a generation is the union of the base's and the deltas' providers with an anti-join on the small delta key set and the tombstones of `DeltaStore` ([DES-005](tessera-boundary.md)): the newest row per key wins, a tombstone drops or redirects its key. Search runs on the base and delta indexes, merges the top-k and masks superseded keys ([DES-026](retrieval.md)).
- **Streaming and multi-product scans.** A scan never materialises a whole block in memory; filters push down to the provider and a scan may span several products. Until [vig-os/tessera#654](https://github.com/vig-os/tessera/issues/654) lands, the interim provider of DES-003 streams leaves and S-002 asks whether it is fast enough for `get` of 100 IDs and hybrid search.
- **Keyed `get`.** `get` is a keyed lookup through `KeyedRefs` ([DES-004](tessera-boundary.md)), at most 100 IDs per call (SYS-025). Whether a SQL statement has resource limits of its own, per tier, and which error it raises is S-009 ([#38](https://github.com/nerdmachines/scitadel-hub/issues/38)); nothing here limits one.
- **No bulk path.** No session entry point streams an unbounded table to a caller; a protocol call returns snippets and records only (SYS-034, [DES-032](protocol.md)).

## 2. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-119 | DES-025 | A fixture base with three deltas holding upserts, a merge and a deletion, queried through the session by filter, by key and across two products | newest row wins; deleted keys absent; merged keys redirect |
