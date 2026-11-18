# L3: serving

Where compute runs: CPU for serving, the GPU only for ingest, and what happens when an optional step is slow. Source: XADR-SCITADEL-008 §14 (serving model) and the GPU policy of §8. Hub-side query embedding is `QueryEmbedder` ([DES-016](tessera-boundary.md)); GPU exchange is [DES-022](adapters-and-pool.md); the retrieval pipeline is [retrieval](retrieval.md).

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). **Superseded text.** §14 makes client-side query embedding the default and keeps hub-side embedding as a fallback; the owner's decision of 2026-11-18 (D-009, SYS-071) makes it hub-side only, so the client-side paragraphs and the client-vector mismatch rule of §14 are not ported (see [protocol](protocol.md)). Latencies are *(estimates)* until measured. Every DES below is `proposed`.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-045 | Serving placement and latency budget | SYS-022, SYS-024, SYS-025, SYS-048 | DES-016, DES-026 |
| DES-046 | Rerank with an unreranked fallback | SYS-023, SYS-024 | DES-015, DES-026, DES-045 |

## 1. Serving placement and latency budget (DES-045)

Ingest (GPU, queued, latency does not matter) is separated from serving (CPU, interactive). No index, embedder or reranker is resident on the shared GPU, and the serving environment is given no GPU device (SYS-024); every GPU use is a `gpu_submit` job with declared VRAM at low priority (SYS-048).

| Step | Where | Latency *(estimate)* |
|---|---|---|
| Filters and metadata (DataFusion) | hub, CPU and NVMe | ms to tens of ms |
| BM25 | hub, CPU | under 50 ms at 10⁸ documents |
| Query embedding | hub, CPU, through the registered embedder | the benchmark of TEST-091 sets it; a GPU slot is allowed only by definition and the owner's approval (SYS-024) |
| ANN search | hub, CPU, RAM or NVMe | ms |
| Fusion, filters, graph hops | hub, CPU | ms |
| Rerank of the top 50 | optional, DES-046 (section 2) | |
| System One scoring of the shortlist | client-side or hosted scorer | not hub code |

- **Budget.** The hybrid search target of SYS-022 is the sum of the hub rows; what happens when one leg is slow or fails, and whether the protocol says an answer is partial, is S-010 ([#39](https://github.com/nerdmachines/scitadel-hub/issues/39)); only the rerank fallback of DES-046 is designed.
- **Placement is configuration.** Executors and limits come from service definitions ([DES-015](tessera-boundary.md)); no code names a host.
- **Sizing** *(estimates)*: 50M chunks at 512 dimensions in fp16 are about 51 GB of vectors, resident in RAM on a sized box or served from NVMe with an on-disk index; a lab of about 20 users is trivial for a CPU hub, which is compute-bound on fusion, not I/O-bound. Stage 0 serves a far smaller slice.
- **Backfills and re-embedding sweeps** run off the shared GPU, on rented GPU by definition ([DES-022](adapters-and-pool.md), SYS-051).
- **Offline mode and local routing** are client behaviour ([DES-052](client-app.md)).

## 2. Rerank with an unreranked fallback (DES-046)

If the rerank step cannot start within **200 ms** *(estimate)* the service returns the unreranked fused list flagged `reranked: false` rather than block (SYS-023); the client may wait and re-request, or score the shortlist itself. Where the reranker runs is open: a queued `gpu_submit` job cannot serve a per-query rerank, so S-007 asks whether it is a CPU model, a resident service outside the serving environment or a batch-only step; the fallback is the same under every answer. The reranker's model and placement are a service definition ([DES-015](tessera-boundary.md)). Every fallback response is flagged, and the flag is a search-level field of the protocol ([DES-032](protocol.md)).

## 3. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-139 | DES-045 | The fixture hub in a microVM with no GPU device, 100 hybrid searches on the fixture slice | 0 GPU devices and 0 MiB VRAM in serving; the median and p95 are recorded against the SYS-022 target |
| TEST-140 | DES-046 | The same hub with a rerank stub that is busy, slow and healthy in turn | busy or slow: the response arrives within the added 200 ms with `reranked: false` on 100 % of fallbacks; healthy: `reranked: true` |
