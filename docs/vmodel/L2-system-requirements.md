# L2: system requirements

What the system and its infrastructure shall do to meet each [L1 requirement](L1-requirements.md), grouped by subsystem and quantified where a number can be given. Where a requirement of L1 is decomposed here, the decomposition is the `decomposes_into` edge of the [trace graph](../traceability/README.md). How each one is verified is in the [verification plan](L2-verification-plan.md); where each one runs is in [L2 infrastructure](L2-infrastructure.md).

**Conventions.** "Shall" marks a requirement. A quantity marked *(estimate)* is a first value taken from back-of-envelope figures in the source or from the shape of the work, calibrated by the first measurement and then confirmed or changed by the owner; a quantity without the mark is fixed by an invariant, a statistic, a legal deadline or a policy value set by this document (backup lag, alert thresholds, guard sizes). Every node is `proposed`: the downward edge to a design (`realised_by`) arrives with L3 and L4 in [#5](https://github.com/nerdmachines/scitadel-hub/issues/5), as the decomposition ruling on [#3](https://github.com/nerdmachines/scitadel-hub/issues/3) allows. Each system requirement is verified by exactly one system `TEST`. This document specifies no commercial figures.

> **Source legend.** `XADR-SCITADEL-008` is the vig-os/scitadel decision record "scitadel-hub: a lab corpus server" (ADR 008, status Proposed, [pull request 317](https://github.com/vig-os/scitadel/pull/317)). `§N` is a section of it. `gerchowl/g-fleet#N` and `nerdmachines/...#N` are issues of private repositories and are written in code style because they cannot be linked from this public repository. Every identifier below is a node in the trace graph, checked by `tools/trace-check`.

## Subsystem coverage

| Subsystem | System requirements |
|---|---|
| Ingest and corpus lifecycle | SYS-001, SYS-002, SYS-003, SYS-004, SYS-005, SYS-006, SYS-007, SYS-008, SYS-009, SYS-010 |
| Storage tiers | SYS-011, SYS-012, SYS-013, SYS-014, SYS-015, SYS-016, SYS-017 |
| Indexes | SYS-018, SYS-019, SYS-020, SYS-021 |
| Query service | SYS-022, SYS-023, SYS-024, SYS-025 |
| Protocol and MCP | SYS-026, SYS-027, SYS-028, SYS-029, SYS-030 |
| Client app | SYS-031, SYS-032, SYS-033, SYS-034 |
| Tenancy and deployment | SYS-035, SYS-036, SYS-037, SYS-038, SYS-039 |
| Security, secrets and privacy | SYS-040, SYS-041, SYS-042 |
| Observability | SYS-043, SYS-044 |
| Backup and restore | SYS-045, SYS-046, SYS-047 |
| GPU job usage | SYS-048, SYS-049, SYS-050, SYS-051 |
| Licence and TDM gating | SYS-052, SYS-053, SYS-054, SYS-055, SYS-056 |

## Decomposition of the L1 requirements

Every requirement decomposes into at least one system requirement.

| Requirement | Decomposes into |
|---|---|
| REQ-001 | SYS-001, SYS-002, SYS-034 |
| REQ-002 | SYS-002, SYS-003, SYS-004, SYS-005, SYS-017, SYS-021, SYS-040, SYS-043 |
| REQ-003 | SYS-005, SYS-012, SYS-018, SYS-019, SYS-020, SYS-021, SYS-022, SYS-023, SYS-025 |
| REQ-004 | SYS-019, SYS-027 |
| REQ-005 | SYS-002, SYS-008, SYS-014, SYS-032 |
| REQ-006 | SYS-006, SYS-007 |
| REQ-007 | SYS-009, SYS-014, SYS-028, SYS-049 |
| REQ-008 | SYS-001, SYS-014, SYS-028, SYS-032, SYS-034, SYS-052, SYS-053, SYS-054 |
| REQ-009 | SYS-010, SYS-021, SYS-028 |
| REQ-010 | SYS-028, SYS-029 |
| REQ-011 | SYS-025, SYS-026, SYS-027, SYS-030, SYS-031 |
| REQ-012 | SYS-037 |
| REQ-013 | SYS-032, SYS-033, SYS-034 |
| REQ-014 | SYS-035, SYS-036, SYS-039, SYS-041, SYS-054 |
| REQ-015 | SYS-038, SYS-039 |
| REQ-016 | SYS-041, SYS-042 |
| REQ-017 | SYS-055 |
| REQ-018 | SYS-003, SYS-006, SYS-011, SYS-013, SYS-015, SYS-016, SYS-017, SYS-039, SYS-040, SYS-041, SYS-043, SYS-044, SYS-045, SYS-046, SYS-047 |
| REQ-019 | SYS-011, SYS-012, SYS-013, SYS-022, SYS-024, SYS-044, SYS-048, SYS-049, SYS-050, SYS-051 |
| REQ-020 | SYS-026, SYS-030, SYS-056 |

## Ingest and corpus lifecycle

### SYS-001: Licence determination at ingest

Ingest shall determine the licence class of every item from upstream metadata before anything is written to a product, and shall reject and log every item outside CC0, CC-BY and public domain.

- **Quantified:** 100 % of items carry a class; 0 out-of-envelope items written; audit sample of 1,000 items per source.
- **Derives from:** REQ-001, REQ-008
- **Source:** XADR-SCITADEL-008 §6; §12; §15
- **Verified by:** TEST-021
- **Delivered by:** [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314), [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318), [vig-os/scitadel#323](https://github.com/vig-os/scitadel/issues/323)

### SYS-002: Sealed shard builds and collection layout

Ingest shall build the phase-1 sources (US patent grants from 1976, the disambiguated PatentsView tables, an OpenAlex subset, structured full-text sources) into sealed shard products grouped as `base/<release>`, `delta/<date>` and `current`, each product recording its upstream release and snapshot date.

- **Quantified:** Shards of 1 to 10 GB *(estimate)*; at least 8,000,000 patents and 5,000,000 works *(estimate)* (OUT-023); sealed size about 3× Parquet until tessera#628 *(estimate)*.
- **Derives from:** REQ-001, REQ-002, REQ-005
- **Source:** XADR-SCITADEL-008 §2; §6
- **Verified by:** TEST-022
- **Delivered by:** [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314), [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315), [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319), [vig-os/tessera#778](https://github.com/vig-os/tessera/issues/778)

### SYS-003: OpenAlex delta sync within the free-key budget

The hub shall run daily OpenAlex subscription jobs (publication-date lookback, `per_page=200`, cursor paging) and a rolling refresh in batches of 100 IDs, shall log the credits used per response, and shall stop before the daily allowance is exhausted.

- **Quantified:** Credits used ≤ 100 % of the free key's daily allowance (10,000 list calls) on each of 7 consecutive days; works searchable ≤ 24 h after publication for subscribed topics *(estimate)*.
- **Derives from:** REQ-002, REQ-018
- **Source:** XADR-SCITADEL-008 §5
- **Verified by:** TEST-023
- **Delivered by:** [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315), [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320)

### SYS-004: Weekly patent-grant delta

The hub shall ingest each weekly USPTO grant release as a delta product, mapping claims, citations and CPC to the same model and edges as the base.

- **Quantified:** Grants searchable ≤ 7 days after the weekly release *(estimate)* (OUT-007).
- **Derives from:** REQ-002
- **Source:** XADR-SCITADEL-008 §6
- **Verified by:** TEST-024
- **Delivered by:** [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314)

### SYS-005: Base, delta and current-pointer lifecycle

Reads shall be newest-wins over base and deltas; tombstones shall drop or redirect merged and deleted IDs; compaction shall write a new base and move `current` atomically, and nothing shall be rewritten in place.

- **Quantified:** 0 superseded or tombstoned rows returned; `current` switch is a single atomic pointer write; 0 in-place rewrites of sealed products.
- **Derives from:** REQ-002, REQ-003
- **Source:** XADR-SCITADEL-008 §2
- **Verified by:** TEST-025
- **Delivered by:** [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320), [vig-os/tessera#781](https://github.com/vig-os/tessera/issues/781)

### SYS-006: Licence-gated extraction cascade

Extraction shall run as the T0 to T4 cascade in which each tier sees only what the cheaper tier could not settle; T4 shall be reachable only for CC-BY, CC0 and public-domain content; T3 and T4 shall be budget-capped and over-budget work shall queue.

- **Quantified:** 0 T4 calls for items outside CC-BY, CC0 and public domain; 0 items skipped for budget; T3 and T4 spend ≤ the configured cap in 100 % of days.
- **Derives from:** REQ-006, REQ-018
- **Source:** XADR-SCITADEL-008 §10; §12; §13
- **Verified by:** TEST-026
- **Delivered by:** [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319), [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321), [vig-os/scitadel#324](https://github.com/vig-os/scitadel/issues/324)

### SYS-007: Extraction quality control and golden loop

Every work shall carry QC columns, every batch shall be sampled at random through T3 and T4 where the licence allows, confirmed errors shall be quarantined and become red fixtures, and extractor, model and threshold upgrades shall be diffed on the golden set before re-derivation.

- **Quantified:** Golden set of 500 to 2,000 items; 300 random samples per batch; QC pass rate ≥ 95 % *(estimate)*; silent-error bound ≤ ~1 % at 95 % confidence when 300 samples show no error.
- **Derives from:** REQ-006
- **Source:** XADR-SCITADEL-008 §13
- **Verified by:** TEST-027
- **Delivered by:** [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321), [vig-os/scitadel#324](https://github.com/vig-os/scitadel/issues/324)

### SYS-008: Document-model storage

Full text shall be stored as the block set (works, elements, inline references, bibliography, table cells, figures, chunks) sorted by work and ordinal, with embeddings and figure products beside each shard, figures stored lossless only, and no PDF bytes in any product.

- **Quantified:** 0 PDF bytes in any product; 100 % of stored figures decode to pixels (or SVG) equal to the source; field-by-field round trip on 100 % of the sampled works.
- **Derives from:** REQ-005
- **Source:** XADR-SCITADEL-008 §9; §6
- **Verified by:** TEST-028
- **Delivered by:** [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319)

### SYS-009: Provenance recording

Every derived product shall record tool, version, config, model-weights hash, input hashes, GPU job and host, and the cascade verdicts that shaped it, and every work row shall record its source, extractor and highest tier reached; raw inputs are referenced by hash and URL.

- **Quantified:** 100 % of served rows resolve to a product seal and to their raw-input hash and URL (OUT-012).
- **Derives from:** REQ-007
- **Source:** XADR-SCITADEL-008 §11
- **Verified by:** TEST-029
- **Delivered by:** [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319), [vig-os/tessera#782](https://github.com/vig-os/tessera/issues/782)

### SYS-010: Retraction flags joined at index build

Every record that matches a retraction-tracking entry by DOI or PMID shall carry its retraction status and date as first-class columns on the shards the hub serves, joined at index-build time.

- **Quantified:** 100 % of matching records flagged (OUT-013); flag lag ≤ 1 index build.
- **Derives from:** REQ-009
- **Source:** XADR-SCITADEL-008 §15
- **Verified by:** TEST-030
- **Delivered by:** [vig-os/scitadel#323](https://github.com/vig-os/scitadel/issues/323), [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311)

## Storage tiers

### SYS-011: Hot tier layout on the KC3000

The hub's hot data shall live on named btrfs subvolumes of the KC3000 pool, each with a hard quota, the properties set out in [L2 infrastructure](L2-infrastructure.md), and a defined owner.

- **Quantified:** Combined hub quota ≤ 1.5 TiB, about 55 % of the roughly 2.7 TiB free on 2026-11-09 *(estimate)*; alert at 80 % of each quota; pool free space ≥ 500 GiB.
- **Derives from:** REQ-018, REQ-019
- **Source:** XADR-SCITADEL-008 §8; `gerchowl/g-fleet#1474`
- **Verified by:** TEST-031
- **Delivered by:** `gerchowl/g-fleet#1474`

### SYS-012: Local NVMe random access for indexes

The BM25 and ANN indexes shall sit on an uncompressed copy-on-write subvolume of the KC3000 that the hub reads directly, never over ranged S3 reads.

- **Quantified:** Random 4 KiB read p95 ≤ 1 ms *(estimate)* on the hub's real access path; 0 index bytes on S3 or on the root disk.
- **Derives from:** REQ-019, REQ-003
- **Source:** XADR-SCITADEL-008 §8; §14; `gerchowl/g-fleet#1474`
- **Verified by:** TEST-032
- **Delivered by:** `gerchowl/g-fleet#1474`

### SYS-013: Object tiers per project

The hub shall use the buckets `scitadel-hub-scratch` (48 h), `scitadel-hub-runs` (28 d), `scitadel-hub-keep` (no expiry) and `scitadel-hub-research` (versioned, write-once when finished), each with its own roles, and no role shall overwrite a finished `research` object.

- **Quantified:** Expiry 48 h and 28 d with a ≥ 72 h warning for `runs`; 0 successful overwrites of finished `research` objects; 0 cross-project reads.
- **Derives from:** REQ-018, REQ-019
- **Source:** XADR-SCITADEL-008 §8; `gerchowl/g-fleet#1449`
- **Verified by:** TEST-033
- **Delivered by:** `gerchowl/g-fleet#1449`

### SYS-014: Content-addressed artefact store

Raw originals shall live in a content-addressed store keyed by blake3 hash in `scitadel-hub-keep`, referenced from `works` rows by hash and URL; open-access PDFs shall be deleted after ingest, raw XML shall never enter a product, and a re-fetch shall be verified against the hash.

- **Quantified:** 0 PDF bytes served (D-007); kept TEI about 8 to 10 GB zstd per 2,000,000 papers *(estimate)*; 100 % of re-fetches verified.
- **Derives from:** REQ-005, REQ-007, REQ-008
- **Source:** XADR-SCITADEL-008 §12
- **Verified by:** TEST-034
- **Delivered by:** [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)

### SYS-015: Warm tier on the storage host

Once the storage host exists, the canonical sealed products, retained raw XML and base generations shall be held on it, served by an S3 gateway, with scheduled scrubs and snapshots; until then the `keep` bucket on the KC3000 stands in.

- **Quantified:** Capacity 4 to 8 TB *(estimate, from g-fleet#1363)*; 0 checksum mismatches after migration from the KC3000 buckets; scrub on schedule.
- **Derives from:** REQ-018
- **Source:** XADR-SCITADEL-008 §8; §2; `gerchowl/g-fleet#1363`
- **Verified by:** TEST-035
- **Delivered by:** `gerchowl/g-fleet#1363`

### SYS-016: Cold tier on the Storage Box

Backups and derived products that fall out of the warm working set shall be pushed client-side encrypted with restic to a Hetzner Storage Box, with keys only in this fleet's sops, and the repository shall pass an integrity check.

- **Quantified:** Backup lag ≤ 24 h; `restic check` pass monthly; 0 plaintext objects on the box.
- **Derives from:** REQ-018
- **Source:** XADR-SCITADEL-008 §8; `gerchowl/g-fleet#1363`; `gerchowl/g-fleet#1438`
- **Verified by:** TEST-036
- **Delivered by:** `gerchowl/g-fleet#1363`, `gerchowl/g-fleet#1438`

### SYS-017: Retention policy

Generations shall expire only by an explicit retention policy executed by one dedicated role, never by ad-hoc deletion; the default shall keep the last 2 bases and their deltas, and stage 0 shall run with 1 base until the warm tier exists.

- **Quantified:** Default 2 bases plus deltas; stage-0 override 1 base, recorded as policy; 0 deletions outside the retention role (audit).
- **Derives from:** REQ-018, REQ-002
- **Source:** XADR-SCITADEL-008 §2; `gerchowl/g-fleet#1363`
- **Verified by:** TEST-037
- **Delivered by:** [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320), `gerchowl/g-fleet#1363`

## Indexes

### SYS-018: BM25 index

The hub shall serve lexical search from a tantivy index over a declared text column, stamped with the seal of the product it indexes and its analyzer configuration, queried as a table function that composes with filters.

- **Quantified:** Single-query p95 ≤ 50 ms at 10⁸ documents *(estimate)*; 0 queries served from an index whose stamp does not match its product.
- **Derives from:** REQ-003
- **Source:** XADR-SCITADEL-008 §4; §14
- **Verified by:** TEST-038
- **Delivered by:** [vig-os/tessera#775](https://github.com/vig-os/tessera/issues/775), [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

### SYS-019: Vector index

The hub shall serve vector search by exact scan, IVF-flat stored in Vortex or an optional HNSW cache, with the choice recorded in `capabilities`.

- **Quantified:** ANN recall against exact search ≥ 0.95 *(estimate)* (OUT-011); ANN step p95 ≤ 20 ms *(estimate)*; 50,000,000 chunks at 512 dimensions in fp16 is about 51 GB *(estimate)*.
- **Derives from:** REQ-003, REQ-004
- **Source:** XADR-SCITADEL-008 §4; §14
- **Verified by:** TEST-039
- **Delivered by:** [vig-os/tessera#769](https://github.com/vig-os/tessera/issues/769), [vig-os/tessera#768](https://github.com/vig-os/tessera/issues/768), [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

### SYS-020: Graph neighbours

The hub shall store citation and CPC edges as typed edge tables with an adjacency cache and answer `neighbours` by edge kind and depth.

- **Quantified:** Depth-1 and depth-2 neighbour queries p95 ≤ 100 ms *(estimate)*; edge tables for work cites work, patent cites patent, patent cites paper and work or patent has CPC.
- **Derives from:** REQ-003
- **Source:** XADR-SCITADEL-008 §4
- **Verified by:** TEST-040
- **Delivered by:** [vig-os/tessera#776](https://github.com/vig-os/tessera/issues/776), [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

### SYS-021: Index freshness and rebuild

Indexes shall be rebuildable from sealed products alone, shall carry the stamp of the seal they cover, and shall be refreshed after each delta so that stale indexes are never presented as fresh.

- **Quantified:** Delta rows searchable ≤ 1 h after the delta is sealed *(estimate)*; full rebuild of the stage-0 indexes ≤ 24 h *(estimate)*; 0 stale-stamp indexes served as fresh.
- **Derives from:** REQ-002, REQ-003, REQ-009
- **Source:** XADR-SCITADEL-008 §2; §4
- **Verified by:** TEST-041
- **Delivered by:** [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320), [vig-os/tessera#781](https://github.com/vig-os/tessera/issues/781)

## Query service

### SYS-022: Hybrid search latency at lab scale

The query service shall answer hybrid (rank-fused) search with metadata filters for about 20 concurrent users on a CPU-only host.

- **Quantified:** p95 ≤ 250 ms *(estimate)* (OUT-005) for hybrid search without rerank at 20 concurrent users; ≥ 20 queries per second sustained *(estimate)*; 0 errors.
- **Derives from:** REQ-003, REQ-019
- **Source:** XADR-SCITADEL-008 §14
- **Verified by:** TEST-042
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316), [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311)

### SYS-023: Rerank fallback

If the rerank queue is busy the service shall return the unreranked result flagged `reranked: false` rather than block.

- **Quantified:** Added wait ≤ 200 ms *(estimate)* before falling back; 100 % of fallback responses flagged.
- **Derives from:** REQ-003
- **Source:** XADR-SCITADEL-008 §14
- **Verified by:** TEST-043
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

### SYS-024: CPU-only serving

No index, embedder or reranker shall be resident on the GPU, and the serving environment shall not be given a GPU device.

- **Quantified:** 0 MiB of VRAM held by serving processes; 0 GPU devices in the serving microVM.
- **Derives from:** REQ-019
- **Source:** XADR-SCITADEL-008 §8; §14
- **Verified by:** TEST-044
- **Delivered by:** [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311)

### SYS-025: Get, neighbours and snippet responses

`get` shall return up to 100 records per call, `neighbours` shall answer by ID, edge kind and depth, and `search` shall return only IDs, scores, snippets and provenance, never documents.

- **Quantified:** `get` of 100 IDs p95 ≤ 150 ms *(estimate)*; a 20-hit search page ≤ 50 KiB *(estimate)*; 0 superseded rows returned.
- **Derives from:** REQ-003, REQ-011
- **Source:** XADR-SCITADEL-008 §7; §14
- **Verified by:** TEST-045
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

## Protocol and MCP

### SYS-026: Protocol surface

The hub shall expose `search`, `get`, `neighbours`, `coverage` and `capabilities` over HTTP and JSON with transport-independent types in a `MIT OR Apache-2.0` protocol crate, and every response shall carry the protocol version.

- **Quantified:** 5 calls; 100 % of responses carry the protocol version; crate licence `MIT OR Apache-2.0`.
- **Derives from:** REQ-011, REQ-020
- **Source:** XADR-SCITADEL-008 §7; §16
- **Verified by:** TEST-046
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316), [vig-os/scitadel#340](https://github.com/vig-os/scitadel/issues/340)

### SYS-027: Capabilities, coverage and the embedding contract

`capabilities` shall advertise per index the embedding model id, version, dimensions, Matryoshka truncation, analyzer configuration and rerankers, `coverage` shall list sources, subsets and product versions, and a client query vector whose declared model, version or dimensions mismatch the index shall be rejected with an explicit protocol error.

- **Quantified:** 100 % of mismatching vectors rejected; 0 silent re-embeddings; `coverage` updated on every delta or release.
- **Derives from:** REQ-004, REQ-011
- **Source:** XADR-SCITADEL-008 §7; §14
- **Verified by:** TEST-047
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

### SYS-028: Response metadata and untrusted text

Every record in every response shall carry the product seal or version that produced it, its licence class, its retraction status, per-row attribution and `answered_by`, and every text field shall arrive as untrusted content.

- **Quantified:** 100 % of records carry the five fields; 100 % of text fields wrapped as untrusted.
- **Derives from:** REQ-007, REQ-008, REQ-009, REQ-010
- **Source:** XADR-SCITADEL-008 §7; §11; §12
- **Verified by:** TEST-048
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316), [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319)

### SYS-029: Standalone MCP server

The hub shall be reachable through a standalone MCP server with tools for search, get-by-ID, neighbours and coverage, with versioned and documented tool schemas.

- **Quantified:** Citation-existence rate ≥ 99 % *(estimate)* (OUT-001); 100 % of tool schemas versioned.
- **Derives from:** REQ-010
- **Source:** XADR-SCITADEL-008 §7
- **Verified by:** TEST-049
- **Delivered by:** [vig-os/scitadel#329](https://github.com/vig-os/scitadel/issues/329), [vig-os/scitadel#332](https://github.com/vig-os/scitadel/issues/332)

### SYS-030: Conformance kit

The project shall publish CC0 conformance vectors and a verifier, and the reference implementation shall pass them.

- **Quantified:** 100 % of vectors pass on the reference implementation; vectors licensed CC0-1.0.
- **Derives from:** REQ-011, REQ-020
- **Source:** XADR-SCITADEL-008 §16
- **Verified by:** TEST-050
- **Delivered by:** [vig-os/scitadel#331](https://github.com/vig-os/scitadel/issues/331)

## Client app

### SYS-031: Fall-through and unchanged client

The hub source adapter shall ask the hub only what `coverage` declares and shall fall through to the live source on a miss, an error or a bounded timeout, recording `answered_by`; with no hub configured, client behaviour shall be unchanged.

- **Quantified:** Added latency on hub failure ≤ 3 s p95 *(estimate)* (OUT-014); 0 differences in the client suite with no hub.
- **Derives from:** REQ-011
- **Source:** XADR-SCITADEL-008 §7
- **Verified by:** TEST-051
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

### SYS-032: Detach hands back structured documents, never PDF bytes

`detach` shall pull the user's own tracked works as structured documents (elements, tables, figures as JPEG XL, references, provenance) and `.tsra` subsets, check the licence per artefact, and may emit a per-paper product whose provenance points at the hub shard's seal; the hub shall never serve PDF bytes on `detach`, `open` or any other call.

- **Quantified:** 0 PDF bytes returned by any call; licence checked for 100 % of artefacts written; per-paper product verifies against the shard seal.
- **Derives from:** REQ-013, REQ-005, REQ-008
- **Source:** XADR-SCITADEL-008 §12; vig-os/scitadel#317 clarification of §12
- **Verified by:** TEST-052
- **Delivered by:** [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)

### SYS-033: Local-subset routing

A detached topic subset with its own indexes shall answer local queries, the client shall route a query to a covering local subset before the remote hub, and the answer shall report `answered_by: local-subset:<id>`.

- **Quantified:** A 50,000-paper subset with indexes ≤ 3 GB and local query p95 ≤ 100 ms on a laptop *(estimate)* (OUT-015).
- **Derives from:** REQ-013
- **Source:** XADR-SCITADEL-008 §14
- **Verified by:** TEST-053
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316), [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)

### SYS-034: No bulk export

The hub shall offer no endpoint that returns the processed corpus in bulk: reads are `get` of at most 100 IDs and `detach` of the caller's own tracked works.

- **Quantified:** 0 bulk-export endpoints; `get` ≤ 100 IDs; `detach` limited to the caller's tracked works.
- **Derives from:** REQ-013, REQ-001, REQ-008
- **Source:** XADR-SCITADEL-008 §12
- **Verified by:** TEST-054
- **Delivered by:** [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318), [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314)

## Tenancy and deployment

### SYS-035: Tenant isolation

Each tenant shall run in its own hub instance on its own microVM with no shared writable mount and no shared credentials, and the same packaging shall be used in development and production.

- **Quantified:** 0 cross-tenant reads in the isolation tests (OUT-020); 0 shared writable mounts.
- **Derives from:** REQ-014
- **Source:** XADR-SCITADEL-008 §8
- **Verified by:** TEST-055
- **Delivered by:** `nerdmachines/scitadel-hub-deploy#1`, [vig-os/scitadel#327](https://github.com/vig-os/scitadel/issues/327)

### SYS-036: Usage metering

The hub shall count usage per tenant for the hosted tiers and shall never meter the free local tier.

- **Quantified:** Metering reconciliation error ≤ 1 % *(estimate)* (OUT-020); 0 meter events from the local tier.
- **Derives from:** REQ-014
- **Source:** XADR-SCITADEL-008 §8; §17
- **Verified by:** TEST-056
- **Delivered by:** `nerdmachines/scitadel-cloud#1`, `nerdmachines/scitadel-hub-deploy#1`

### SYS-037: Annotation layers

Annotations shall live in four layers, personal, group, organisation and global, each annotation recording its layer and author; reads shall resolve most specific first, a write shall go only to the layer the caller names, and a lower layer shall never appear in a higher one except through an explicit publish that creates a new row in the higher layer. The layer names and the resolution order proposed here are confirmed in the L3 design.

- **Quantified:** 4 layers; 0 leaks across the full permission matrix (OUT-021); layer and author present on 100 % of annotations.
- **Derives from:** REQ-012
- **Source:** XADR-SCITADEL-008 §12; §17
- **Verified by:** TEST-057
- **Delivered by:** [vig-os/scitadel#325](https://github.com/vig-os/scitadel/issues/325), [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311)

### SYS-038: On-prem parity

An on-prem hub shall run the same binary and the same sealed shards as the hosted stages, install from the NixOS module, OCI image or Helm chart, and interoperate over the same protocol.

- **Quantified:** Time from a clean machine to a passing protocol smoke test ≤ 8 h *(estimate)* (OUT-019); 0 differing bytes for the same shard served from hosted and on-prem.
- **Derives from:** REQ-015
- **Source:** XADR-SCITADEL-008 §8; §1
- **Verified by:** TEST-058
- **Delivered by:** `nerdmachines/scitadel-hub-deploy#2`, [vig-os/scitadel#328](https://github.com/vig-os/scitadel/issues/328)

### SYS-039: Stage portability

The data model, protocol and licence gating shall be identical across stages 0, 1 and 2 and on-prem; only host mix and storage endpoints differ, and they differ by configuration.

- **Quantified:** Conformance kit 100 % on every stage; 0 code paths conditional on the stage.
- **Derives from:** REQ-018, REQ-014, REQ-015
- **Source:** XADR-SCITADEL-008 §8
- **Verified by:** TEST-059
- **Delivered by:** `nerdmachines/scitadel-hub-deploy#1`, `nerdmachines/scitadel-hub-deploy#2`

## Security, secrets and privacy

### SYS-040: Secrets handling

Hub secrets shall live in their own encrypted secrets file, and no credential, including the OpenAlex key, shall appear in logs, errors or responses.

- **Quantified:** 0 secret strings found in logs, errors and responses; 1 dedicated secrets file for the hub.
- **Derives from:** REQ-018, REQ-002
- **Source:** XADR-SCITADEL-008 §1; §5; `gerchowl/g-fleet#1474`
- **Verified by:** TEST-060
- **Delivered by:** [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315), `gerchowl/g-fleet#1474`

### SYS-041: Encryption and access control

Data shall be encrypted at rest (the KC3000 pool is LUKS) and in transit (TLS 1.2 or newer on every hub endpoint), S3 access shall use per-workload credentials, and no endpoint shall serve data anonymously.

- **Quantified:** 0 plaintext endpoints; 0 anonymous reads; per-workload credentials for 100 % of S3 clients.
- **Derives from:** REQ-014, REQ-016, REQ-018
- **Source:** XADR-SCITADEL-008 §8; §12; `gerchowl/g-fleet#1449`
- **Verified by:** TEST-061
- **Delivered by:** `gerchowl/g-fleet#1449`, `nerdmachines/scitadel-hub-deploy#1`

### SYS-042: Privacy controls

Erasure requests shall be honoured by soft-deleting from the index while retaining the hash for deduplication, access logging shall be limited to entitlement checks with bounded retention, and no reading history shall be stored.

- **Quantified:** Erasure ≤ 30 days (OUT-018); log retention ≤ 30 days *(estimate)*; 0 per-user reading-history records.
- **Derives from:** REQ-016
- **Source:** XADR-SCITADEL-008 §12; §18
- **Verified by:** TEST-062
- **Delivered by:** [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333)

## Observability

### SYS-043: Freshness, spend and budget telemetry

The hub shall export freshness per subscription, OpenAlex credits used, T3 and T4 spend, queue depth and GPU job records through the fleet's observability seam, and alert at 80 % of any cap.

- **Quantified:** Freshness reported for 100 % of subscriptions; alert raised at 80 % of every cap; metric scrape success ≥ 99 % *(estimate)*.
- **Derives from:** REQ-002, REQ-018
- **Source:** XADR-SCITADEL-008 §5; §10; `gerchowl/g-fleet#1474`
- **Verified by:** TEST-063
- **Delivered by:** [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315), `gerchowl/g-fleet#1474`

### SYS-044: Service health and quota watch

The hub shall expose per-step latency histograms and a health endpoint, and the host shall watch each subvolume's quota use and the pool's free space.

- **Quantified:** Alerts at 80 % and 90 % of any subvolume quota and below 500 GiB pool free; p95 per step recorded for 100 % of calls.
- **Derives from:** REQ-019, REQ-018
- **Source:** XADR-SCITADEL-008 §14; `gerchowl/g-fleet#1474`
- **Verified by:** TEST-064
- **Delivered by:** [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311), `gerchowl/g-fleet#1474`

## Backup and restore

### SYS-045: Snapshot schedule

The hub's btrfs subvolumes shall be snapshotted read-only by policy: `state` hourly, the `keep` and `research` buckets daily, derived subvolumes minimally, so that accidental deletion or overwrite is recoverable.

- **Quantified:** RPO ≤ 1 h for `state` and ≤ 24 h for `keep` and `research` *(estimate)*; retention per [L2 infrastructure](L2-infrastructure.md).
- **Derives from:** REQ-018
- **Source:** XADR-SCITADEL-008 §8; `gerchowl/g-fleet#1438`
- **Verified by:** TEST-065
- **Delivered by:** `gerchowl/g-fleet#1438`

### SYS-046: Off-box encrypted backup

The non-rebuildable data (`keep`, `research`, `state` dumps) shall be backed up off the KC3000 and off anvil, client-side encrypted, and research data shall additionally go to the separate fleet's target.

- **Quantified:** Backup lag ≤ 24 h; `restic check` monthly pass; keys only in sops; 100 % of non-rebuildable data covered by the backup set.
- **Derives from:** REQ-018
- **Source:** XADR-SCITADEL-008 §8; `gerchowl/g-fleet#1438`; `gerchowl/g-fleet#1263`
- **Verified by:** TEST-066
- **Delivered by:** `gerchowl/g-fleet#1438`, `gerchowl/g-fleet#1263`

### SYS-047: Restore from empty host

An empty host shall be restorable to a serving hub from backup, rebuilding the derived indexes from sealed products.

- **Quantified:** Empty host to a serving hub ≤ 8 h *(estimate)* (OUT-017); 0 sealed products missing against the ledger.
- **Derives from:** REQ-018
- **Source:** XADR-SCITADEL-008 §8; `gerchowl/g-fleet#1263`; `gerchowl/g-fleet#1363`
- **Verified by:** TEST-067
- **Delivered by:** `gerchowl/g-fleet#1263`, `gerchowl/g-fleet#1363`

## GPU job usage

### SYS-048: GPU submission policy

Every hub GPU job shall go through `gpu_submit` with a declared VRAM, low priority, a runtime chunked to the default limit and a checkpoint, and shall write only to new directories.

- **Quantified:** 100 % of submissions declare VRAM and `priority=low`; chunk ≤ 1,800 s (the default runtime); checkpoint at least every 600 s *(estimate)*; 0 writes outside a new output directory.
- **Derives from:** REQ-019
- **Source:** XADR-SCITADEL-008 §8; §14; `gerchowl/g-fleet` docs/gpu-jobs.md
- **Verified by:** TEST-068
- **Delivered by:** [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311), [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314)

### SYS-049: GPU job data access

GPU jobs shall read their inputs from the hub's `gpu-io` subvolume as exposed under the project path and write only to a new `out/<run-id>/` directory; the hub shall validate outputs against a hash ledger before promoting them into products.

- **Quantified:** 0 unvalidated outputs promoted; 0 writes by jobs outside `out/<run-id>/`; 100 % of promoted outputs match the ledger hash.
- **Derives from:** REQ-019, REQ-007
- **Source:** XADR-SCITADEL-008 §8; `gerchowl/g-fleet#654`; g-fleet docs/gpu-jobs.md
- **Verified by:** TEST-069
- **Delivered by:** `gerchowl/g-fleet#654`

### SYS-050: Embedding throughput

Bulk embedding on the local GPU shall meet the phase-1 budget so that the corpus embeds in one to two GPU-days.

- **Quantified:** ≥ 5,000,000 chunks per GPU-hour *(estimate)* (OUT-004).
- **Derives from:** REQ-019
- **Source:** XADR-SCITADEL-008 §15
- **Verified by:** TEST-070
- **Delivered by:** [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311), [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314)

### SYS-051: Backfills off the shared GPU

Backfills and re-embedding sweeps shall run on rented GPU, not on anvil, so that the shared GPU is never monopolised by a one-off sweep.

- **Quantified:** 0 re-embedding or backfill sweeps submitted to anvil; initial ingest chunks ≤ 1,800 s each.
- **Derives from:** REQ-019
- **Source:** XADR-SCITADEL-008 §8
- **Verified by:** TEST-071
- **Delivered by:** [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311)

## Licence and TDM gating

### SYS-052: Licence class on every row and artefact

Every row and artefact shall carry a licence class that the protocol carries, phase 1 shall write a single class, and `get` and `search` shall be unable to return a row outside it.

- **Quantified:** 0 rows served outside the permitted class (OUT-003) over a fuzz run of 100,000 queries *(estimate)*.
- **Derives from:** REQ-008
- **Source:** XADR-SCITADEL-008 §12
- **Verified by:** TEST-072
- **Delivered by:** [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)

### SYS-053: Gated features off in phase 1

Entitlement classes, local display of licensed content, upload-on-acquire and COUNTER 5.1 / SUSHI usage reporting shall be present in schema and protocol but unreachable in the phase-1 configuration. Upload-on-acquire comes from §12 and is an inference from §12 and §15, not a named item of §15.

- **Quantified:** 0 registered routes or handlers for the 4 gated features in the phase-1 build; schema fields present.
- **Derives from:** REQ-008
- **Source:** XADR-SCITADEL-008 §12; §15
- **Verified by:** TEST-073
- **Delivered by:** [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)

### SYS-054: Paid-tier exclusion of NC and ND content

CC-BY-NC and CC-BY-ND content shall be excluded from every build and index of a paid hosted tier.

- **Quantified:** 0 NC or ND rows in paid-tier indexes.
- **Derives from:** REQ-008, REQ-014
- **Source:** XADR-SCITADEL-008 §12
- **Verified by:** TEST-074
- **Delivered by:** [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)

### SYS-055: TDM opt-out honoured on every re-ingest

Every re-ingest of the commercial tier shall re-check robots.txt, TDMRep, `noai` and ai.txt, skip and record opted-out sources, honour per-publisher terms in the paced fetch buckets, and pin the upstream snapshot date.

- **Quantified:** 100 % of re-ingested sources re-checked in the same cycle (OUT-016); 0 fetches of opted-out sources.
- **Derives from:** REQ-017
- **Source:** XADR-SCITADEL-008 §12; §15
- **Verified by:** TEST-075
- **Delivered by:** [vig-os/scitadel#330](https://github.com/vig-os/scitadel/issues/330)

### SYS-056: Release hygiene

Every release shall carry SPDX expressions and licence files, a third-party NOTICE and an SBOM, pass a dependency-licence allowlist, fetch model weights at first run through a signed manifest, and contain no model weights in any image layer.

- **Quantified:** 100 % of releases with NOTICE and SBOM; 0 allowlist violations; 0 weight files in image layers.
- **Derives from:** REQ-020
- **Source:** XADR-SCITADEL-008 §16
- **Verified by:** TEST-076
- **Delivered by:** [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333)
