# L3: retrieval

How BM25, vector and graph retrieval combine into one candidate set. Source: XADR-SCITADEL-008 §4 (retrieval: BM25, vectors, graph), with the fusion step of §14. The three indexes are the hub-owned traits `TextIndex`, `VectorIndex` and `GraphIndex` of [the tessera boundary](tessera-boundary.md) ([DES-007](tessera-boundary.md), [DES-006](tessera-boundary.md), [DES-008](tessera-boundary.md)); this file adds the pipeline above them.

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). Every DES below is `proposed`. Where XADR-SCITADEL-008 §4 says "Vortex fixed-size-list columns" for embeddings, the interim differs (C-001); where it says "IVF-flat in the products", C-005 applies.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-026 | Hybrid retrieval pipeline: filters, BM25, vector, fusion and masking | SYS-018, SYS-019, SYS-021, SYS-022, SYS-010 | DES-006, DES-007, DES-016, DES-025 |
| DES-027 | Graph neighbours service and edge kinds | SYS-020, SYS-025 | DES-008, DES-025 |

## 1. Hybrid retrieval pipeline (DES-026)

`search` runs the modes `bm25`, `vector` and `hybrid` (SYS-026). One `RetrievalPlan` per query, built by the query service:

| Step | Component | Note |
|---|---|---|
| 1. Filters | DataFusion ([DES-025](query-engine.md)) | metadata and licence-tier view; the tier is a type ([DES-001](tessera-boundary.md)), so a paid query cannot reach a lab index |
| 2. BM25 | `TextIndex` ([DES-007](tessera-boundary.md)) | queried as a table function so it composes with the filters; the analyzer configuration is part of the stamp |
| 3. Vector | `VectorIndex` ([DES-006](tessera-boundary.md)) | the query vector comes from the hub's own embedder ([DES-016](tessera-boundary.md), SYS-071); never from the client; exact scan, IVF-flat, optional HNSW cache |
| 4. Fusion | reciprocal rank fusion of the two rank lists | `k` and the per-leg limits are configuration; each candidate records the mode that produced it |
| 5. Masking | newest-wins over base and delta indexes ([DES-025](query-engine.md)) | merge the top-k of each, drop superseded and redirected keys |
| 6. Retraction | retraction flag joined at index build, a column on the shard | never at query time (SYS-010, [DES-018](adapters-and-pool.md)) |
| 7. Hand-off | candidate set only | System One ranking (the scorer of vig-os/scitadel#246) happens in the client or a hosted scorer, and only the shortlist reaches an LLM; none of it is hub code |

- **Freshness.** Every index is stamped with the seal of the product it covers and fresh only when the stamp matches the pinned generation; a stale index is not served (`StaleStamp`, SYS-021).
- **Latency budget.** Set in [DES-045](serving.md); the retrieval legs run on CPU and local NVMe only.
- **Rerank.** Optional and after fusion; fallback in [DES-046](serving.md).

## 2. Graph neighbours and edge kinds (DES-027)

**No graph database** (principle PRIN-003): a citation graph is two ID columns, which fit typed tables plus an adjacency cache. Kùzu is gone and its Rust successors are young (XADR-SCITADEL-008 §4); `GraphIndex` ([DES-008](tessera-boundary.md)) keeps a later engine pluggable.

| Edge table | From → to |
|---|---|
| `cites_work` | work → work |
| `cites_patent` | patent → patent |
| `cites_paper` | patent → paper |
| `has_topic` | work or patent → CPC class or topic |
| `claim_depends_on` | claim → the claim it depends on (patents, [DES-030](patents.md)) |

- `neighbours(id, edge_kind, depth)` is a bounded breadth-first traversal over the adjacency cache; `depth` is capped by configuration and a request above it is refused. The same edge tables support recursive CTEs for analytic queries ([DES-025](query-engine.md)).
- An edge exists only if its `bib.matched_work_id` or source record resolves; unresolved references stay as `bib` rows ([DES-036](document-model.md)). How records of one work from two sources link is S-003.
- Node embeddings (node2vec, GraphSAGE) become ordinary vector columns when [vig-os/tessera#776](https://github.com/vig-os/tessera/issues/776) lands; nothing here depends on them.

## 3. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-120 | DES-026 | The golden queries of [DES-043](quality.md) over a fixture slice in each mode, with a stale index, a superseded row, a retracted record and a paid-tier query | every candidate names its mode; superseded rows masked; retraction flag present on 100 % of matches; a stale index refused; 0 lab-only rows in the paid result |
| TEST-121 | DES-027 | A fixture citation graph with a cycle, a merged work and a patent with dependent claims, traversed at depths 1 to the cap and one above it | results equal a reference traversal; the cycle terminates; the over-cap request is refused; every edge kind is reachable |
