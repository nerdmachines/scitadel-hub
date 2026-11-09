# L1: requirements

What the programme as a whole shall do, derived from the [L0 principles and decisions](L0-principles.md). Each requirement has at least one [user story](L1-user-stories.md) and one acceptance test stub, and is measured by [outcomes](L1-outcomes.md) where a number applies.

**Conventions.** "Shall" marks a requirement. "Phase 1" is the licence-clean build of PRIN-001. All requirements are `proposed`; they are decomposed into system requirements at L2 (the gate requires that edge once a requirement is past `proposed`, see ADR-0001). Acceptance test stubs are named `TEST` nodes with the intended method in the title; they are specifications, not executed tests.

> **Source legend.** `XADR-SCITADEL-008` is the vig-os/scitadel decision record "scitadel-hub: a lab corpus server" (ADR 008, status Proposed, [pull request 317](https://github.com/vig-os/scitadel/pull/317)). `§N` is a section of it and "decision N" one of its numbered decisions. Issue references such as `vig-os/scitadel#314` point at the issue that delivers the node. Every identifier below is a node in the [trace graph](../traceability/README.md), checked by `tools/trace-check`.

## Topic coverage

| Topic | Requirements |
|---|---|
| Corpus and freshness | REQ-001, REQ-002 |
| Retrieval | REQ-003, REQ-004 |
| Document model | REQ-005 |
| Extraction quality | REQ-006 |
| Provenance | REQ-007 |
| Licence gating | REQ-008, REQ-009 |
| Agent and MCP grounding surface | REQ-010, REQ-011 |
| Layered hubs and annotations | REQ-012 |
| Offline use and detach | REQ-013 |
| Hosted tiers (no commercial figures) | REQ-014 |
| On-prem | REQ-015 |
| Privacy and GDPR | REQ-016 |
| TDM compliance | REQ-017 |
| Operability | REQ-018, REQ-019, REQ-020 |

## REQ-001: Licence-clean corpus scope

In phase 1 the hub shall hold only items whose licence is CC0, CC-BY or public domain, determined per item, from sources whose access terms permit bulk harvest: US patent grants (pre-grant publications are an open scope question in the source record, grants only by default), the disambiguated PatentsView tables, an OpenAlex subset, and the structured full-text sources triaged in vig-os/scitadel#323 (JATS, LaTeX and XML first). Within that envelope the hub shall go for depth: full text, figures, tables, cross-links and embeddings. Pre-1976 patents (image only) are out of scope. No corpus copy is published in bulk.

- **Derives from:** PRIN-001, PRIN-002, D-003, D-005
- **Source:** XADR-SCITADEL-008 §6; §15
- **Stories:** US-023, US-030
- **Outcomes:** OUT-023
- **Acceptance stub:** TEST-001, phase-1 corpus is licence-clean per item, method: audit a random sample of 1,000 ingested items per source against upstream licence metadata, with negative fixtures (an NC item, a paywalled item) that ingest must reject
- **Delivered by:** [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314), [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315), [vig-os/scitadel#323](https://github.com/vig-os/scitadel/issues/323)

## REQ-002: Freshness and delta lifecycle

The hub shall keep the corpus current with a base-plus-delta lifecycle: a quarterly base, daily OpenAlex deltas (publication-date subscriptions plus a rolling refresh in ID batches), weekly patent-grant deltas, and a "current" pointer as the only object that moves. Reads are newest-wins, and tombstones drop or redirect merged and deleted IDs. OpenAlex sync shall stay within the free key's daily budget, log the credits used and never expose the key. The hub shall report freshness per subscription.

- **Derives from:** PRIN-007
- **Source:** XADR-SCITADEL-008 §2; §5; §6
- **Stories:** US-009, US-032
- **Outcomes:** OUT-006, OUT-007, OUT-008
- **Acceptance stub:** TEST-002, deltas keep the corpus fresh within budget, method: replay a week of daily jobs against recorded API responses, including a merged and a deleted ID, asserting visibility of new works, tombstone handling, credits within the daily allowance and a correct freshness report
- **Delivered by:** [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315), [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320), [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314)

## REQ-003: Hybrid retrieval and graph neighbours

The hub shall offer lexical (BM25), vector and hybrid (rank-fused) search with metadata filters, and citation and CPC graph neighbours over typed edge tables. Results are snippet-only (IDs, scores, snippets, provenance) and state the mode that produced each. If the rerank queue is busy, the hub shall return unreranked results flagged `reranked: false` rather than block. A search shall never return a row superseded by a delta or removed by a tombstone.

- **Derives from:** PRIN-003, PRIN-010
- **Source:** XADR-SCITADEL-008 §4; §7; §14
- **Stories:** US-001, US-005, US-030, US-031
- **Outcomes:** OUT-005, OUT-011
- **Acceptance stub:** TEST-003, retrieval is correct over base and deltas, method: golden-query suite over a fixed corpus asserting recall floors for BM25, vector and hybrid; a base-plus-three-deltas fixture asserting no superseded or tombstoned row is returned; a busy-queue simulation asserting reranked false
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316), [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314), [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320)

## REQ-004: Query-embedding contract

The hub shall advertise, per index, the embedding model id, version, output dimensions, Matryoshka truncation, BM25 analyzer configuration and available rerankers, and shall reject a client-supplied query vector whose declared model, version or dimensions do not match the target index, with an explicit protocol error. It never silently re-embeds under another model. Hub-side query embedding from text shall remain available for thin clients and for the window after a re-embedding. Which path is the default is an open owner question (see L0).

- **Derives from:** PRIN-008, PRIN-010
- **Source:** XADR-SCITADEL-008 §7; §14; [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)
- **Stories:** US-017
- **Outcomes:** OUT-011
- **Acceptance stub:** TEST-004, model mismatch is explicit, method: protocol contract tests where a vector with a wrong model id, version or dimension is rejected with the documented error, a matching vector is accepted, text input is embedded hub-side, and the capabilities response matches a recorded snapshot
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

## REQ-005: Document model

Full text shall be stored as a document model, not as documents: typed, Arrow-shaped blocks (works, elements, inline references, bibliography, table cells, figures, chunks) linked by keys and sorted by work and ordinal, with embedding and figure products beside each shard. Figures are stored lossless only. Typst, HTML and Markdown are views rendered on demand, never storage. The hub holds no per-paper product. Patents map to the same model, with the claim dependency tree as edges.

- **Derives from:** PRIN-004, D-007
- **Source:** XADR-SCITADEL-008 §9; §6
- **Stories:** US-004, US-030
- **Outcomes:** OUT-004, OUT-024
- **Acceptance stub:** TEST-005, the document model round-trips and holds no PDFs, method: snapshot tests of the model on golden-set fixtures from JATS, TEI, HTML, PDF and USPTO XML, a field-by-field round trip of a sample against the source, and a scan asserting no PDF bytes in any product
- **Delivered by:** [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319)

## REQ-006: Extraction quality

Extraction shall run as a licence-gated, tiered cascade: T0 parses structured sources, T1 runs tool extraction, T2 runs System One yes/no checks, T3 repairs with a vision-language model and T4 gives a frontier-model verdict. Each tier sees only what the cheaper tier could not settle. T4 reaches only CC-BY, CC0 and public-domain content, T3 and T4 are budget-capped, and work queues rather than being skipped. Quality shall be a growing test suite: a stratified golden set with a patent stratum, a red/green quarantine loop, random-sample QC on every batch, and upgrades diffed on the golden set before re-derivation. Users can report an extraction problem per element.

- **Derives from:** PRIN-009, PRIN-012
- **Source:** XADR-SCITADEL-008 §10; §13
- **Stories:** US-006, US-022
- **Outcomes:** OUT-009, OUT-010
- **Acceptance stub:** TEST-006, extraction faults are caught and tiers are licence-gated, method: golden-set regression run with red/green fixtures, a seeded extraction fault that must be flagged and quarantined, and a gating test proving T4 is unreachable for an item outside CC-BY, CC0 and public domain
- **Delivered by:** [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319), [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321), [vig-os/scitadel#324](https://github.com/vig-os/scitadel/issues/324)

## REQ-007: Provenance

Every derived product shall record tool, version, config, model-weights hash, input hashes, GPU job and host, and the cascade verdicts that shaped it. Each work row shall record its source, extractor and highest cascade tier reached. Raw inputs are referenced by hash and URL even when not held, and originals are never modified. Every protocol response shall name the product seal or version that produced it, every record shall report `answered_by`, and attribution shall be kept per row.

- **Derives from:** PRIN-005, PRIN-008
- **Source:** XADR-SCITADEL-008 §11; §7
- **Stories:** US-016, US-029, US-033
- **Outcomes:** OUT-001, OUT-012
- **Acceptance stub:** TEST-007, provenance is complete and visible, method: a completeness check on a sealed fixture product (every input resolvable by hash and URL) plus response contract tests asserting seal or version, attribution and answered_by on every record
- **Delivered by:** [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319), [vig-os/tessera#782](https://github.com/vig-os/tessera/issues/782)

## REQ-008: Licence classes and gating

Every row and artefact shall carry a licence class, and the protocol shall carry it. Phase 1 writes a single class (public, licence-clean), and `get` and `search` cannot return a row outside it. CC-BY-NC and CC-BY-ND content is excluded from every paid hosted tier. Entitlement classes, local display of licensed content for entitled lab users, upload-on-acquire and COUNTER 5.1 / SUSHI usage reporting are designed and wired through schema and protocol but disabled in phase 1. The hub is never a bulk proxy for paywalled content.

- **Derives from:** PRIN-012, D-005, D-006
- **Source:** XADR-SCITADEL-008 §12; §15
- **Stories:** US-011, US-012, US-014, US-033
- **Outcomes:** OUT-003
- **Acceptance stub:** TEST-008, only permitted classes are served and gated paths are off, method: negative tests where rows of a disallowed class are never returned by get or search, NC and ND fixtures are refused by the paid-tier build, and gated handlers are verified unreachable in the phase-1 configuration
- **Delivered by:** [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)

## REQ-009: Retraction flags

Every record the hub holds that matches a retraction-tracking entry (by DOI or PMID) shall be surfaced with its retraction status and date on `search` and `get`, and search result rendering shall say so. Flags are joined at index-build time and are first-class columns on the shards the hub serves.

- **Derives from:** PRIN-008
- **Source:** XADR-SCITADEL-008 §15 ("Retraction flags are a must-have")
- **Stories:** US-010, US-019
- **Outcomes:** OUT-013
- **Acceptance stub:** TEST-009, retracted works are flagged everywhere they are served, method: fixture records that match a retraction list by DOI and by PMID must show status and date on search and get, while non-matching records stay unflagged
- **Delivered by:** [vig-os/scitadel#323](https://github.com/vig-os/scitadel/issues/323), [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311)

## REQ-010: Agent and MCP grounding surface

The hub shall be reachable through a standalone MCP server so an agent can ground its answers: tools for search, get-by-ID, neighbours and coverage whose responses carry provenance, licence class, retraction status and `answered_by`. Every text field arrives as untrusted content. Citations an agent produces shall resolve to records the hub holds. Tool schemas and the field vocabulary shall be versioned and documented so that a third party can implement them.

- **Derives from:** PRIN-008, D-004
- **Source:** XADR-SCITADEL-008 Context (Positioning); §7
- **Stories:** US-015, US-016, US-019
- **Outcomes:** OUT-001, OUT-002
- **Acceptance stub:** TEST-010, an agent can ground answers and its citations resolve, method: an end-to-end MCP session against a mock hub over a seeded corpus asserting every cited ID resolves, untrusted-content wrapping and the presence of provenance, licence and answered_by, then the grounding benchmark on a pinned release
- **Delivered by:** [vig-os/scitadel#329](https://github.com/vig-os/scitadel/issues/329), [vig-os/scitadel#332](https://github.com/vig-os/scitadel/issues/332), [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

## REQ-011: Protocol and fall-through

The hub shall expose `search`, `get` (up to 100 IDs), `neighbours`, `coverage` and `capabilities` over HTTP and JSON, with types that do not assume the transport. A client shall ask the hub only for what `coverage` declares, and on a miss, an error or a bounded timeout fall through to the live source and record `answered_by`. With no hub configured, client behaviour is unchanged. The protocol types live in a permissively licensed crate, and conformance vectors and a verifier are provided.

- **Derives from:** D-001, D-004
- **Source:** XADR-SCITADEL-008 §7; §16
- **Stories:** US-003, US-005, US-018
- **Outcomes:** OUT-014
- **Acceptance stub:** TEST-011, protocol conformance and bounded fall-through, method: contract tests against recorded hub responses, fault injection (hub down, hub slow) asserting a bounded fall-through with answered_by, an unchanged client suite with no hub configured, and the conformance kit run against the reference implementation
- **Delivered by:** [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316), [vig-os/scitadel#331](https://github.com/vig-os/scitadel/issues/331)

## REQ-012: Layered hubs and annotations

Hubs shall support layered knowledge: a global hub holds the licence-clean corpus, and organisation, group and personal layers hold institutional annotations and curated sets on top of it. Clients keep identity (DOI, OpenAlex ID, content hash), annotations and reviews, while the hub keeps bytes. Every annotation shall record its layer and author, layers shall resolve in a defined order, and a lower layer shall never leak into a higher one. The layer names and resolution order are settled in the L2 and L3 design slices.

- **Derives from:** PRIN-008, D-004
- **Source:** XADR-SCITADEL-008 §12 (clients keep annotations); §17 (personal, lab and organisation spaces); the layer model itself is new at L1 and is not specified in that record
- **Stories:** US-007, US-008
- **Outcomes:** OUT-021
- **Acceptance stub:** TEST-012, layers isolate and resolve correctly, method: a permission-matrix test across personal, group, organisation and global layers covering read, write and leak-upward attempts, asserting layer and author on every annotation
- **Delivered by:** [vig-os/scitadel#325](https://github.com/vig-os/scitadel/issues/325), [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311)

## REQ-013: Offline use and detach

A client shall work offline-first on a personal machine with local storage. `detach` shall pull full copies of the user's own tracked works into local storage, checking the licence per artefact, and may emit a per-paper product whose provenance points at the hub shard's seal. A detached topic subset with its own indexes gives local search, and the client shall route a query to a covering local subset before the remote hub and report `answered_by: local-subset`. Bulk export of the processed corpus is not offered.

- **Derives from:** PRIN-002, PRIN-006, D-003
- **Source:** XADR-SCITADEL-008 §12; §14; §17
- **Stories:** US-001, US-002
- **Outcomes:** OUT-015
- **Acceptance stub:** TEST-013, offline search and detach work, method: detach a tracked-works fixture on a clean profile with the network disabled, verify the per-paper product with the sealed-product verifier, test local-subset routing, and assert no bulk-export endpoint exists
- **Delivered by:** [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318), [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)

## REQ-014: Hosted tiers

Hosted personal, lab and organisation spaces shall be per-tenant, isolated from each other and metered by usage. The free local tier is never metered. Tenant isolation and metering paths shall be exercised in development on the same packaging as production, through microVM tenant simulation. Hosted tiers rely on the commercial text-and-data-mining route and its opt-out handling. This repository specifies no commercial figures.

- **Derives from:** PRIN-006, PRIN-013
- **Source:** XADR-SCITADEL-008 §8 (stages 1 and 2); §17 (tiers)
- **Stories:** US-026
- **Outcomes:** OUT-020
- **Acceptance stub:** TEST-014, tenants are isolated and usage is metered, method: tenant simulation on microVMs with two tenants, a cross-read attempt that must fail, and a metering reconciliation against generated usage
- **Delivered by:** `nerdmachines/scitadel-cloud#1`, `nerdmachines/scitadel-hub-deploy#1`

## REQ-015: On-prem deployment

An on-prem hub shall run the same binary and the same sealed shards as the hosted stages and interoperate over the same protocol. An administrator installs it through the NixOS module, OCI image or Helm chart from the private deploy repository, under the commercial grant or a support contract. A research organisation's own mining rests on the research-organisation provisions of the TDM requirement.

- **Derives from:** D-001, D-002
- **Source:** XADR-SCITADEL-008 §1; §8 (on-prem)
- **Stories:** US-020
- **Outcomes:** OUT-019
- **Acceptance stub:** TEST-015, a clean install serves the protocol, method: install on a clean machine from the NixOS module, OCI image and Helm chart, run the protocol smoke suite, and serve one sealed shard unchanged from a hosted-stage instance and an on-prem instance
- **Delivered by:** `nerdmachines/scitadel-hub-deploy#2`

## REQ-016: Privacy and GDPR

Before the first hosted user, a reviewed data-protection impact assessment and a published Art. 14 notice shall exist. Author data (ORCID) is reused under legitimate interests (Art. 6(1)(f)). Erasure requests are honoured by soft-deleting from the index while retaining the hash for deduplication. Access logging is limited to entitlement checks with bounded retention, not reading histories. Research analytics default to aggregates, with individual views only for the researcher or with consent. Not legal advice.

- **Derives from:** PRIN-011
- **Source:** XADR-SCITADEL-008 §12 (GDPR); §18 (GDPR guardrails)
- **Stories:** US-013
- **Outcomes:** OUT-018
- **Acceptance stub:** TEST-016, privacy obligations are met before launch, method: a launch-gate checklist (assessment and notice exist and are reviewed), an erasure test asserting an erased author is absent from search while the hash is retained, and a log-retention test
- **Delivered by:** [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333)

## REQ-017: Text-and-data-mining compliance

The commercial hosted tier shall honour every machine-readable TDM opt-out (robots.txt, TDMRep, noai, ai.txt), re-checked on every re-ingest, because it relies on EU DSM Art. 4. Research-organisation use, including the on-prem hub of a research organisation, rests on Art. 3 and Swiss CopA Art. 24d for internal indexing, which does not permit commercial redistribution of mining results beyond verification. Per-publisher TDM terms are honoured in the paced fetch buckets, and every product pins the upstream snapshot date for audit. Not legal advice.

- **Derives from:** PRIN-001, D-005
- **Source:** XADR-SCITADEL-008 §12 (legal basis by tier); §15 (Crossref TDM-link harvester)
- **Stories:** US-012, US-027
- **Outcomes:** OUT-016
- **Acceptance stub:** TEST-017, opt-outs are honoured on every re-ingest, method: opt-out fixtures (robots.txt, TDMRep, a noai header, ai.txt) that a re-ingest must skip and record, plus a replay where an opt-out appears between two ingests and must take effect
- **Delivered by:** [vig-os/scitadel#330](https://github.com/vig-os/scitadel/issues/330)

## REQ-018: Operability

The hub shall be operable by one person. Infrastructure is staged (stage 0 on the local GPU host, stage 1 on a dedicated server with object storage, stage 2 hosted spaces), with the data model, protocol and licence gating unchanged across stages. Storage is tiered (hot, warm, cold) with encrypted backups and an explicit retention policy (default: keep the last two bases and their deltas), and no generation expires by ad-hoc deletion. Hub secrets live in their own store, and the OpenAlex key and other credentials never appear in logs or errors. T3 and T4 spend is capped.

- **Derives from:** PRIN-007, PRIN-011
- **Source:** XADR-SCITADEL-008 §2 (retention); §8
- **Stories:** US-021, US-025
- **Outcomes:** OUT-017
- **Acceptance stub:** TEST-018, the hub can be restored and cleaned up safely, method: a restore drill from backup into an empty host, a retention-policy test (an old base expires by policy, never by ad-hoc delete), a log scan asserting no secret appears, and a budget-cap test asserting work queues rather than skips
- **Delivered by:** `gerchowl/g-fleet#1363`, [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320)

## REQ-019: Serving performance and compute placement

Serving shall run on CPU and NVMe: no index, embedder or reranker is resident on the GPU. GPU work (extraction tiers T1 and T3, bulk embedding, figure descriptions, re-embedding) shall go through the shared queue with declared VRAM, chunked to the default runtime with checkpoints and writing outputs only to new directories. Backfills and re-embedding sweeps run on rented GPU, not on the shared one. A lab of about twenty users shall be served interactively by a CPU hub.

- **Derives from:** PRIN-010
- **Source:** XADR-SCITADEL-008 §8 (GPU policy); §14
- **Stories:** US-024, US-025
- **Outcomes:** OUT-004, OUT-005
- **Acceptance stub:** TEST-019, serving is CPU-only and GPU use obeys the queue policy, method: a lab-scale load test (twenty simulated users) on a CPU-only host recording p95 per step, plus a lint asserting every GPU submission declares VRAM, a checkpoint and a new output directory
- **Delivered by:** [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311), [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314)

## REQ-020: Licence and release hygiene

Code and documents shall be released under the licences of the owner decisions: the hub under `AGPL-3.0-only OR LicenseRef-scitadel-Commercial` with written AGPL §7 interop permissions, the protocol crate under `MIT OR Apache-2.0`, the protocol prose spec under the Community Specification License 1.0, the conformance vectors under CC0-1.0, and deploy artefacts proprietary. Every release ships a third-party NOTICE and an SBOM, dependency licences are checked against an allowlist, model weights are fetched at first run through a signed manifest and never baked into an image, and contributions follow the ICLA policy once external pull requests arrive.

- **Derives from:** D-001, D-002
- **Source:** XADR-SCITADEL-008 §16
- **Stories:** US-018, US-028
- **Outcomes:** OUT-022
- **Acceptance stub:** TEST-020, every release is licence-clean, method: release-checklist automation asserting SPDX expressions and licence files are present, NOTICE and SBOM are generated, the dependency licence check passes and no model weights sit in the image layers
- **Delivered by:** [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333)
