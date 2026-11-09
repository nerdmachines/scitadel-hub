# L0: principles and owner decisions

The top of the V ([ADR-0001](../decisions/0001-v-model-and-traceability.md)): what the programme holds to, and what the owner has decided. Nothing here is a requirement on the system by itself; [L1](L1-requirements.md) turns it into requirements.

> **Source legend.** `XADR-SCITADEL-008` is the vig-os/scitadel decision record "scitadel-hub: a lab corpus server" (ADR 008, status Proposed, [pull request 317](https://github.com/vig-os/scitadel/pull/317)). `§N` is a section of it and "decision N" one of its numbered decisions. Issue references such as `vig-os/scitadel#314` point at the issue that delivers the node. Every identifier below is a node in the [trace graph](../traceability/README.md), checked by `tools/trace-check`.

## Principles

A principle is a rule the design must respect. Each one cites where it comes from.

### PRIN-001: Licence-clean first

Phase 1 ingests only items that are CC0, CC-BY or public domain per item, from sources whose access terms allow bulk harvest. No scraping, no grey-area sources and no paywalled caches in phase 1; within that envelope the build goes for maximum depth.

*Source:* XADR-SCITADEL-008 §15; decisions 15 and 16

### PRIN-002: Walled corpus, published tools

The processed corpus is served by the running hub and is not released as a dataset. What is published is the toolchain: the client, the protocol, the conformance kit and, if the owner confirms it, a tiny CC0 fixtures slice. Bulk copies would only dilute the running service.

*Source:* XADR-SCITADEL-008 §15 (opening); §17 (detach versus bulk export); decision 19

### PRIN-003: Rust-native, tessera storage, no graph database

Storage is sealed, content-addressed tessera products queried through DataFusion. BM25, vector search and the citation and CPC graph are rebuildable derived caches over typed edge tables. No graph database is the source of truth; graph access goes through a trait so an engine can plug in later.

*Source:* XADR-SCITADEL-008 §3; §4; decisions 3 to 5

### PRIN-004: Originals stay out of the corpus database

PDFs and raw JATS, TEI or HTML live in a content-addressed artefact store under a raw-retention policy. The corpus holds a typed, queryable document model, and rendered views are generated on demand. Neither PDFs nor per-paper products live in the hub corpus.

*Source:* XADR-SCITADEL-008 §9; §12; decisions 9 and 12

### PRIN-005: Full provenance

Every derived product and every served row says what produced it: tool, version, config, model-weights hash, input hashes, job and cascade verdicts. Raw inputs are referenced by hash and URL even when the bytes are not held. Originals are never modified; re-extraction writes new products.

*Source:* XADR-SCITADEL-008 §11; decision 11

### PRIN-006: Offline-first client

A personal machine works without a hub and without an account. A user can take full copies of their own tracked works with them; the processed corpus itself stays behind the wall. Hosted spaces are an addition, not a requirement.

*Source:* XADR-SCITADEL-008 §14 (offline mode); §17; decisions 20 and 21

### PRIN-007: Reproducible and rebuildable

Storage is add-only: a release writes new products and "current" is a pointer. Every derived product can be rebuilt from upstream or from the artefact store, so a format change costs a rebuild and never data. Builds run from pinned inputs with one command.

*Source:* XADR-SCITADEL-008 §2 ("Derived means rebuildable"); decision 3; [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314)

### PRIN-008: Grounding first

The hub is a stepping stone to an MCP that grounds agents against hallucination. Every answer carries per-row provenance and a licence class, every text field arrives as untrusted content, and retraction status is surfaced. Institutional knowledge lives in the database and graph and is exposed through a wire protocol a third party can implement.

*Source:* XADR-SCITADEL-008 Context (Positioning); §7; §15 (retraction flags)

### PRIN-009: Quality is a growing test suite

A stratified golden set, a red/green quarantine loop and random-sample QC on every batch. An extractor, model or threshold change runs on the golden set and produces a diff report before the corpus is re-derived.

*Source:* XADR-SCITADEL-008 §13; decision 13

### PRIN-010: Serve on CPU, ingest on GPU

Filters, BM25, ANN search, graph hops and fusion serve from CPU and NVMe. The GPU is for batch ingest through the shared queue and nothing stays resident, so a search never depends on the GPU for its tail latency.

*Source:* XADR-SCITADEL-008 §14; §8 (GPU policy); decision 14

### PRIN-011: Privacy by design

Access logging records entitlement checks, not reading histories, with bounded retention. Analytics default to aggregates. Erasure requests are honoured. A data-protection impact assessment and an Art. 14 notice come before the first hosted user.

*Source:* XADR-SCITADEL-008 §12 (guardrails, GDPR); §18 (GDPR guardrails)

### PRIN-012: Licence gating is data, not convention

The licence class is a per-row column enforced in code and covered by tests. Features that read, cache or serve any other class are designed and wired through the schema and the protocol, but no code path serves them in phase 1.

*Source:* XADR-SCITADEL-008 §12; §15 (gated features designed but disabled); Consequences

### PRIN-013: Commercial detail stays out of this repository

This repository carries no commercial figures (amounts, tier ranges), competitor analysis or business strategy, and its requirements name no competitor as a target. That material belongs in the private repositories. A grep over `docs/` for currency and cost terms is part of the review.

*Source:* XADR-SCITADEL-008 §1 (repo split); §17 (no tier figures recorded)

## Owner decisions

These are decisions the owner has taken, with the date. A decision is changed by a new decision, not by editing this file in place.

### D-001: Dual licence: AGPL-3.0-only OR commercial (2026-11-08)

The hub is dual-licensed `AGPL-3.0-only OR LicenseRef-scitadel-Commercial`, with written AGPL §7 additional permissions for client and cloud interop. The scitadel client stays `MIT OR Apache-2.0`; the protocol crate stays in the client repository under `MIT OR Apache-2.0`. Not legal advice; to be verified with counsel before the first external hosted user.

*Source:* XADR-SCITADEL-008 §16; decision 18

### D-002: Deploy repository is private (2026-11-08)

`nerdmachines/scitadel-hub-deploy` (NixOS module, OCI image build, Helm chart) is private, so on-prem comes through the commercial grant or a support contract. The AGPL hub source stays public. The owner overrode the product-angle and licence reviewers, who recommended a public deploy repository.

*Source:* XADR-SCITADEL-008 §1 ("On-prem comes via the commercial grant"); decision 1

### D-003: Walled corpus, published tools, no dataset release (2026-11-08)

The processed corpus and the GPU hours behind it are not given away. There is no Hugging Face dataset and no bulk export of the processed corpus. Publishing `.tsra` on Hugging Face is reframed from the main path to optional and selective.

*Source:* XADR-SCITADEL-008 §15; §17; decision 19

### D-004: Positioning: an MCP that grounds agents against hallucination (2026-11-08)

The hub is a stepping stone toward a scitadel MCP that grounds AI agents against hallucination, with per-row provenance and licence class in every protocol response. Institutional knowledge lives in the database and graph and is exposed through a wire protocol a third party can implement.

*Source:* XADR-SCITADEL-008 Context (Positioning)

### D-005: Licence-clean phase 1; licence-gated features designed but disabled (2026-11-08)

Build first on a strictly licence-clean corpus and approach the library with a running hub. The entitlement classes, local display of licensed content and usage reporting are designed and wired through schema and protocol, but no code path that reads, caches or serves non-CC0, non-CC-BY content is enabled in phase 1.

*Source:* XADR-SCITADEL-008 §15; decisions 15 to 17

### D-006: CC-BY-NC and CC-BY-ND are excluded from paid tiers (2026-11-08)

Content under CC-BY-NC or CC-BY-ND is excluded from every paid hosted tier. A 2048-d embedding is treated as adapted material to be safe, and the per-row licence column is the enforcement surface.

*Source:* XADR-SCITADEL-008 §12 (licence classes); Consequences

### D-007: No PDFs served (2026-11-08)

The hub never serves PDF bytes to clients. PDFs are ingest inputs only and are never served to clients (as the acceptance of the source issue states); clients get structured records and views rendered from the document model.

*Source:* [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)

### D-008: Repository home is the nerdmachines organisation (2026-11-09)

The hub, deploy and cloud repositories live under the owner's `nerdmachines` organisation, separate from `vig-os`, for a clean ownership line under the dual licence.

*Source:* XADR-SCITADEL-008 §1 (repository table and creation note)

## Open owner question (not a decision)

**Where is the query embedded by default?** The source decision record says client-side, with hub-side embedding as the fallback. A product review recommends the inverse: the hub embeds by default, client-supplied vectors become an explicit option, and offline and detached-subset use stays client-side. The reasons are that thin web and mobile clients and MCP agents have no local embedder, and that a hub model upgrade should not force coordinated client releases; the cost is query-time embedding compute on the hub, against the CPU-serving model of PRIN-010. Both paths and the explicit mismatch rejection are requirements either way (REQ-004); only the default is open. It is tracked in [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316) and is deliberately not recorded as a `D` node until the owner rules.

## What this level does not contain

- Commercial figures, competitor analysis and strategy (PRIN-013).
- System, infrastructure and design decisions: those are L2 and L3 and arrive in later slices.
