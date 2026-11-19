# L3: data model and lifecycle

How the corpus is cut into sealed shards and how a release, its deltas and the `current` pointer move. Source: XADR-SCITADEL-008 §2 (data model on tessera: layout and lifecycle). The mechanics (write, seal, keyed deltas, atomic publication) are the hub-owned traits of [the tessera boundary](tessera-boundary.md); this file adds only the layout and the lifecycle policy that use them.

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). `XADR-SCITADEL-008` is the vig-os/scitadel decision record (status Proposed, [pull request 317](https://github.com/vig-os/scitadel/pull/317)); `§N` is a section of it. Every DES below is `proposed`.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-023 | Shard and collection layout | SYS-002, SYS-008 | DES-002, DES-004, DES-036 |
| DES-024 | Base, delta and current lifecycle policy | SYS-005, SYS-017, SYS-021, SYS-060, SYS-073 | DES-005, DES-012 |

## 1. Shard and collection layout (DES-023)

A release is a collection of **shard products** of about 1 to 10 GB *(estimate)*, never one product per paper.

| Corpus | Shard key | Collection |
|---|---|---|
| OpenAlex | one of 26 fields × a publication-year bucket | one collection per field, under the release's base collection |
| Patents | grant year × CPC section (A to H, Y) | one collection per grant year |

- The blocks inside a shard are the document model of [DES-036](document-model.md); every block is sorted by `(work_id, ord)`.
- Each product records, through `ProvenanceSink` ([DES-009](tessera-boundary.md), [DES-040](provenance.md)), the upstream release or snapshot date, the filter that defined the subset and the code version that built it.
- **No per-paper `.tsra` in the hub.** The manifest, seal and footer of a product would exceed a paper's text, tiny blocks compress badly and a corpus-wide query would open millions of objects. A per-paper `.tsra` exists only as the output of a client-side `detach` ([DES-051](client-app.md)).
- `.tsra` is the only product format. Parquet staging before sealing is internal and never in a bucket ([DES-021](adapters-and-pool.md), [C-002 ruling](https://github.com/nerdmachines/scitadel-hub/issues/20#issuecomment-6995799107)).
- String-heavy shards seal about 3× larger than Parquet until [vig-os/tessera#628](https://github.com/vig-os/tessera/issues/628) lands; capacity planning uses that factor ([L2 infrastructure](../vmodel/L2-infrastructure.md)).

## 2. Base, delta and current lifecycle policy (DES-024)

```
base/<release>/     a collection per quarterly snapshot or PatentsView release: shards + derived products
delta/<date>.tsra   the same blocks: upserted rows + tombstones (id, merged → W… | deleted), with small caches of its own
current             a tiny content-addressed collection {base, deltas[]}; the only thing that moves
```

| Rule | Mechanism |
|---|---|
| Reads are newest-wins over base ⊕ deltas | `DeltaStore` ([DES-005](tessera-boundary.md)); the query side is [DES-025](query-engine.md) |
| A new release becomes the new base; deltas older than its snapshot date retire; `current` moves atomically | `GenerationCatalog` ([DES-012](tessera-boundary.md)); nothing is rewritten in place |
| Deltas may be merged monthly along the way | `LifecyclePolicy.merge_deltas = monthly`, a configuration value |
| Retention is an explicit policy: keep the last 2 bases and their deltas (the number is open question 8 of the ADR) | `LifecyclePolicy.keep_bases = 2`; expiry only by the retention role (SYS-017), never by an ad-hoc delete |
| A retired base that a reader still pins is not removed | the pin rule of SYS-073 ([DES-012](tessera-boundary.md)) |
| Derived means rebuildable | every product is rebuilt from upstream or from the artefact store ([DES-013](tessera-boundary.md)); a pre-1.0 format change costs a rebuild, not data |
| Indexes follow the generation | an index stamped with another generation is stale (SYS-021, [DES-001](tessera-boundary.md)) |

OpenAlex deltas are daily ([DES-028](sync.md)); patent deltas are the weekly grant XML ([DES-031](patents.md)). How the hot working copy and the bucket's retention meet is settled in `gerchowl/g-fleet#1363`, not here.

## 3. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-117 | DES-023 | Build one OpenAlex field and one patent year from a fixture slice; list every product and read its provenance | every product is a shard keyed as the table says; 0 per-paper products; each records release, filter and code version |
| TEST-118 | DES-024 | A fixture release with three deltas, a compaction to a new base, a pinned reader and a restart in the middle | the reader sees newest-wins before and after; `current` moves in one step; bases beyond the retention count expire only through the retention role; the pinned base stays until its pin expires |
