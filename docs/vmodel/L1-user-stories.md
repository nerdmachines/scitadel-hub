# L1: user stories

Each story has the form "As a *persona*, I want *goal*, so that *outcome*" and acceptance bullets that a test or a review can decide. A story is the `story_of` one or more [requirements](L1-requirements.md).

## Personas

| Persona | Who they are and what they need | Stories |
|---|---|---|
| Individual researcher (offline) | Works on a personal machine, often without a network or an account. Needs a fast local search over the topics they follow, full copies of the works they track, and no dependency on a service staying up. | US-001, US-002, US-003, US-004 |
| Lab member | Searches and reads for a group, shares annotations with colleagues and repeats the same topic queries as them. Needs shared results, visible sources and a way to report a bad extraction. | US-005, US-006, US-007 |
| Lab PI | Responsible for what the group reads, cites and keeps. Needs current literature on the lab's topics, group-level curation, and confidence that the corpus is clean enough to rely on. | US-008, US-009, US-010 |
| Librarian or research office | Answers for licence compliance, data protection and usage reporting. Needs auditable licence classes, a lawful basis for mining, minimal logging and data-sovereignty guarantees. | US-011, US-012, US-013, US-014 |
| Agent builder (MCP) | Builds research agents that must cite science they can defend. Needs an MCP surface whose answers carry provenance, licence class and retraction status, with a documented, versioned vocabulary. | US-015, US-016, US-017, US-018, US-019 |
| On-prem admin | Installs and runs the hub on institutional hardware. Needs a packaged install, backups, retention and a safe upgrade path, with no hidden outbound dependency. | US-020, US-021, US-022 |
| Owner as operator | Runs the hub and its infrastructure alone. Needs reproducible builds, bounded cost, a clear compute policy, compliance gates that cannot be skipped and licence hygiene on every release. | US-023, US-024, US-025, US-026, US-027, US-028, US-029 |
| Patent prior-art searcher | Searches US patents and the papers they cite. Needs full text with claims, citation links between patents and papers, weekly freshness and a clear source for every passage. | US-030, US-031, US-032, US-033 |

## Individual researcher (offline)

### US-001: Search my topics offline

As an individual researcher (offline), I want to search a detached subset of my topics on my own laptop with no network, so that I can find papers anywhere without a service.

*Story of:* REQ-013, REQ-003. *Delivered by:* [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318), [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316).

Acceptance:

- A detached subset with its own indexes answers BM25, vector and hybrid queries with the network disabled.
- The result reports `answered_by: local-subset:<id>`, which names the subset.
- A query outside the subset is routed to the hub when one is reachable, and is reported as not covered when not.

### US-002: Take my tracked works with me

As an individual researcher (offline), I want to detach full copies of the works I track, so that my library survives without the hub and I can cite from it.

*Story of:* REQ-013. *Delivered by:* [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318).

Acceptance:

- `detach` writes full local copies and checks the licence of each artefact before writing it.
- A per-paper product can be emitted, and its provenance points at the hub shard's seal.
- No command exports the processed corpus in bulk.

### US-003: Keep working when the hub is down

As an individual researcher (offline), I want to have my searches fall through to the live sources when the hub misses or does not answer, so that a hub outage never blocks my work.

*Story of:* REQ-011. *Delivered by:* [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316).

Acceptance:

- A hub that is down or slower than the bounded timeout produces a notice and a live-source answer, not an error.
- Every result reports `answered_by`, naming the hub or the live source.
- With no hub configured the client behaves exactly as before.

### US-004: Read a work without a PDF

As an individual researcher (offline), I want to open a held work as a structured document rendered from the hub, so that I read headings, tables, equations and figures without ever downloading a PDF.

*Story of:* REQ-005. *Delivered by:* [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318), [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319).

Acceptance:

- Opening a work renders Markdown, HTML or Typst from the document model.
- No PDF bytes are served to the client.
- Figures arrive as lossless images or vector graphics, with captions linked.

## Lab member

### US-005: Share the lab's search work

As a lab member, I want to search a lab hub that has already answered my colleagues' topics, so that we stop repeating the same queries against rate-limited APIs.

*Story of:* REQ-011, REQ-003. *Delivered by:* [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316), [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311).

Acceptance:

- A query inside the hub's declared coverage is answered by the hub with BM25, vector or hybrid mode as requested.
- Results are snippet-only (IDs, scores, snippets, provenance), and bytes flow only on open or detach.
- An unreranked answer is flagged `reranked: false` when the rerank queue is busy.

### US-006: Report a bad extraction

As a lab member, I want to flag a wrong table, equation or reading order on the element itself, so that the extraction improves and the same fault does not return.

*Story of:* REQ-006. *Delivered by:* [vig-os/scitadel#324](https://github.com/vig-os/scitadel/issues/324), [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321).

Acceptance:

- A report is attached to one element and carries the work, the element and the extractor version.
- A report on an element is shown against its source region (a licence-gated crop rendered from the kept original) and the element can be re-extracted from that region.
- A confirmed report becomes a red fixture in the golden set and the fixed case stays in it.
- Reports on licensed content go to the private tracker, public ones to the public tracker.

### US-007: Annotate and share with my group

As a lab member, I want to annotate papers and share the annotations with my group, so that what we learn stays with the group after people move on.

*Story of:* REQ-012. *Delivered by:* [vig-os/scitadel#325](https://github.com/vig-os/scitadel/issues/325).

Acceptance:

- An annotation records its layer (personal or group) and its author.
- Group members see group annotations, and non-members do not.
- My personal annotations never appear in a group or higher layer unless I publish them there.

## Lab PI

### US-008: Curate at group and organisation level

As a lab PI, I want to keep curated sets and notes at group level on top of the global corpus, so that new members inherit the group's reading and the organisation can build on it.

*Story of:* REQ-012. *Delivered by:* [vig-os/scitadel#325](https://github.com/vig-os/scitadel/issues/325), [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311).

Acceptance:

- Group and organisation layers resolve over the global layer in a documented order.
- A lower layer never leaks into a higher one; the permission-matrix test covers it.
- Removing a member removes their access to the layers, not the group's annotations.

### US-009: Stay current on the lab's topics

As a lab PI, I want to see new publications for my subscribed topics within a day, so that the group reads current literature without paying for a change feed.

*Story of:* REQ-002. *Delivered by:* [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315), [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320).

Acceptance:

- A subscription surfaces new works through the daily delta, newest first.
- The freshness report shows the newest publication date held and the age of the oldest unrefreshed hot work, per subscription.
- One week of daily runs stays within the free key's daily allowance, and credits used are logged.

### US-010: Trust that retracted work is marked

As a lab PI, I want to see retraction status next to every result, so that the group does not cite retracted papers by accident.

*Story of:* REQ-009. *Delivered by:* [vig-os/scitadel#323](https://github.com/vig-os/scitadel/issues/323), [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311).

Acceptance:

- A record that matches a retraction entry by DOI or PMID shows status and date on search and get.
- Result rendering says so in words, not only in a field.
- Flags are present in the shards the hub serves, so they cannot be skipped at query time.

## Librarian or research office

### US-011: Audit licence classes

As a librarian or research office, I want to see the licence class of every row and every artefact and prove that nothing outside the permitted class is served, so that I can answer a licence audit from evidence.

*Story of:* REQ-008. *Delivered by:* [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318).

Acceptance:

- Every row carries a licence class, and the protocol returns it.
- In phase 1 `get` and `search` cannot return anything outside the public licence-clean class; a negative test demonstrates it.
- CC-BY-NC and CC-BY-ND content is not present in any paid hosted tier.

### US-012: Know the lawful basis for mining

As a librarian or research office, I want to see which legal basis covers each tier and that opt-outs are honoured, so that the library can stand behind the service in a procurement review.

*Story of:* REQ-017, REQ-008. *Delivered by:* [vig-os/scitadel#330](https://github.com/vig-os/scitadel/issues/330), [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333).

Acceptance:

- The legal basis per tier is documented, and states that it is not legal advice.
- The hosted tier re-checks robots.txt, TDMRep, noai and ai.txt on every re-ingest.
- Every product pins the upstream snapshot date for audit.

### US-013: Protect personal data

As a librarian or research office, I want to rely on a data-protection impact assessment, an Art. 14 notice, minimal logging and working erasure, so that the service meets data-protection duties before it has users.

*Story of:* REQ-016. *Delivered by:* [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333).

Acceptance:

- The assessment and the notice exist and are reviewed before the first hosted user.
- An erasure request removes the author record from search and keeps only the hash for deduplication.
- Access logs hold entitlement checks only, with a bounded retention period.

### US-014: Keep usage reporting ready

As a librarian or research office, I want to have the schema and the reporting plumbing for publisher usage ready in design, so that turning on licensed content later is a configuration change.

*Story of:* REQ-008. *Delivered by:* [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318).

Acceptance:

- The event schema, hub-side counters and the reporting emit point are designed.
- In phase 1 the recording path is a no-op, because all served content is CC0, CC-BY or public domain.
- No code path that serves non-CC0, non-CC-BY content is reachable in the phase-1 configuration.

## Agent builder (MCP)

### US-015: Ground answers in real records

As an agent builder (MCP), I want to call search, get and neighbours from an MCP client, so that every citation my agent writes points at a record that exists.

*Story of:* REQ-010. *Delivered by:* [vig-os/scitadel#329](https://github.com/vig-os/scitadel/issues/329), [vig-os/scitadel#332](https://github.com/vig-os/scitadel/issues/332).

Acceptance:

- The MCP tools return IDs that resolve through `get` for every cited work.
- Each result names the source that answered it (`answered_by`).
- The grounding benchmark reports the citation-existence rate on a pinned corpus release.

### US-016: Receive provenance and licence with every answer

As an agent builder (MCP), I want to get provenance, licence class and attribution in every response and have all text arrive as untrusted content, so that my agent can show where a claim comes from and cannot be steered by hostile text.

*Story of:* REQ-007, REQ-010. *Delivered by:* [vig-os/scitadel#329](https://github.com/vig-os/scitadel/issues/329), [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316).

Acceptance:

- Each record names the product seal or version that produced it.
- Each record carries its licence class and the attribution the licence requires.
- Every text field arrives wrapped as untrusted content.

### US-017: Send query vectors safely

As an agent builder (MCP), I want to read the hub's capabilities and send a query vector tagged with its model, version and dimensions, so that a model upgrade never silently degrades my recall.

*Story of:* REQ-004. *Delivered by:* [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316).

Acceptance:

- `capabilities` lists, per index, the model id, version, dimensions, Matryoshka truncation, analyzer and rerankers.
- A vector with a mismatched model, version or dimension is rejected with an explicit protocol error.
- Sending text instead makes the hub embed it, and the response says so.

### US-018: Implement the protocol myself

As an agent builder (MCP), I want to build against a documented protocol with conformance vectors and a verifier, so that a third-party client or hub can interoperate without reading the source.

*Story of:* REQ-011, REQ-020. *Delivered by:* [vig-os/scitadel#331](https://github.com/vig-os/scitadel/issues/331), [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333).

Acceptance:

- The protocol crate is licensed `MIT OR Apache-2.0` and the spec is published under the Community Specification License 1.0.
- Conformance vectors (CC0-1.0) and a verifier ship with the kit.
- The reference hub passes the conformance kit in CI.

### US-019: Never see a retracted paper unmarked

As an agent builder (MCP), I want to receive retraction status in every search and get response, so that my agent does not present a retracted result as sound.

*Story of:* REQ-009, REQ-010. *Delivered by:* [vig-os/scitadel#329](https://github.com/vig-os/scitadel/issues/329), [vig-os/scitadel#323](https://github.com/vig-os/scitadel/issues/323).

Acceptance:

- A retracted record carries status and date in the MCP response.
- The MCP schema documents the retraction fields.
- A fixture with a retracted work is part of the MCP end-to-end test.

## On-prem admin

### US-020: Install the hub on our hardware

As an on-prem admin, I want to install the hub from the packaged module, image or chart, so that we run it ourselves under the commercial grant or a support contract.

*Story of:* REQ-015. *Delivered by:* `nerdmachines/scitadel-hub-deploy#2`.

Acceptance:

- A clean machine reaches a passing protocol smoke test from the NixOS module, the OCI image or the Helm chart.
- The on-prem hub serves the same sealed shards as a hosted-stage hub, unchanged.
- The artefacts come from the private deploy repository and are pinned by tag.

### US-021: Back up, restore and expire safely

As an on-prem admin, I want to back up the hub, restore it and expire old generations by policy, so that a disk failure or an upgrade never costs the corpus.

*Story of:* REQ-018. *Delivered by:* [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320), `gerchowl/g-fleet#1363`.

Acceptance:

- A restore drill brings a hub up from backup on an empty host.
- Old bases expire by the retention policy (default: keep the last two), never by an ad-hoc delete.
- Backups are encrypted and the cold tier is separate from the warm tier.

### US-022: Upgrade without silent regressions

As an on-prem admin, I want to see a golden-set diff report before an extractor, model or threshold change reaches the corpus, so that an upgrade cannot quietly make the corpus worse.

*Story of:* REQ-006. *Delivered by:* [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321).

Acceptance:

- A change runs on the golden set and produces a per-work, per-block diff report.
- The corpus is re-derived into new products only after review; originals are untouched.
- Embedding upgrades check drift on the golden set before any re-embedding.

## Owner as operator

### US-023: Build the phase-1 corpus reproducibly

As an owner as operator, I want to build the licence-clean corpus from pinned inputs with one command, so that I can rebuild it after any failure or format change.

*Story of:* REQ-001. *Delivered by:* [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314), [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315).

Acceptance:

- One command with pinned inputs produces the patent corpus and the OpenAlex subset.
- Row counts match the source release, and a sample of 100 patents round-trips field by field.
- A negative fixture with a non-permitted licence is rejected at ingest.

### US-024: Keep GPU use inside the queue policy

As an owner as operator, I want to run all GPU work through the shared queue with declared VRAM and checkpoints, so that I never monopolise the shared GPU or lose a run.

*Story of:* REQ-019. *Delivered by:* [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311), [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314).

Acceptance:

- Every GPU submission declares VRAM, is chunked to the default runtime with checkpoints and writes only new directories.
- No index, embedder or reranker stays resident on the GPU.
- Backfills and re-embedding sweeps run on rented GPU.

### US-025: Operate one stage at a time

As an owner as operator, I want to move serving between stages without changing the data model, the protocol or licence gating, so that growth is a hosting change, not a rewrite.

*Story of:* REQ-018, REQ-019. *Delivered by:* `gerchowl/g-fleet#1363`, [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311).

Acceptance:

- The same binary and sealed shards run at stage 0, stage 1 and on-prem.
- Freshness, QC rates and credits used are visible in monitoring.
- T3 and T4 spend is capped, and work queues when a cap is reached.

### US-026: Isolate and meter tenants

As an owner as operator, I want to simulate several tenants on separate microVMs and meter their usage, so that isolation and metering are proven before the first paying user.

*Story of:* REQ-014. *Delivered by:* `nerdmachines/scitadel-hub-deploy#1`, `nerdmachines/scitadel-cloud#1`.

Acceptance:

- A cross-tenant read attempt fails in the isolation test.
- Metering reconciles against generated usage within the target error.
- The free local tier is never metered.

### US-027: Re-check opt-outs on every ingest

As an owner as operator, I want to have the ingest pipeline re-check every TDM opt-out each time it re-ingests, so that the hosted tier stays within its legal basis.

*Story of:* REQ-017. *Delivered by:* [vig-os/scitadel#330](https://github.com/vig-os/scitadel/issues/330).

Acceptance:

- robots.txt, TDMRep, noai and ai.txt are each covered by a fixture.
- An opt-out that appears between two ingests takes effect at the next one.
- Each skipped source is recorded with the opt-out that caused it.

### US-028: Ship licence-clean releases

As an owner as operator, I want to ship every release with the right licences, a NOTICE and an SBOM, so that downstream users and procurement can trust what they receive.

*Story of:* REQ-020. *Delivered by:* [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333).

Acceptance:

- Licence files and SPDX expressions match the owner decisions.
- The dependency licence check passes and no model weights sit in an image layer.
- The contribution policy switches to the ICLA at the first external pull request.

### US-029: Keep a trail for every row

As an owner as operator, I want to inspect the provenance of any served row back to its raw input, so that any result can be explained, reproduced or re-derived.

*Story of:* REQ-007. *Delivered by:* [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319), [vig-os/tessera#782](https://github.com/vig-os/tessera/issues/782).

Acceptance:

- A row resolves to its product seal, tool, version, config, weights hash and the cascade verdicts.
- Raw inputs resolve by hash and URL even when the bytes are not held.
- Re-extraction writes new products and leaves the originals untouched.

## Patent prior-art searcher

### US-030: Search patent full text with claims

As a patent prior-art searcher, I want to run BM25, vector and hybrid queries over US patent full text including claims and their dependency structure, so that I find prior art in the claims, not only in the abstract.

*Story of:* REQ-001, REQ-003, REQ-005. *Delivered by:* [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314).

Acceptance:

- Grants from 1976 onward are searchable, with abstract, description, claims and the description of the drawings.
- The claim dependency tree is available as edges.
- A query returns snippets with the patent number, the mode that matched and provenance naming the USPTO release.

### US-031: Follow citations between patents and papers

As a patent prior-art searcher, I want to traverse patent-to-patent and patent-to-paper citations and CPC links, so that I can trace what an invention builds on.

*Story of:* REQ-003. *Delivered by:* [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314), [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316).

Acceptance:

- `neighbours` returns patent-cites-patent, patent-cites-paper and work-or-patent-has-CPC edges.
- A depth limit bounds every traversal.
- Each neighbour carries provenance and licence class.

### US-032: See new grants weekly

As a patent prior-art searcher, I want to find newly granted patents within a week, so that my searches stay current.

*Story of:* REQ-002. *Delivered by:* [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314), [vig-os/scitadel#320](https://github.com/vig-os/scitadel/issues/320).

Acceptance:

- The weekly grant release becomes a delta that is searchable after its run.
- A reissued or withdrawn grant is handled by tombstones, not by in-place rewrites.
- The freshness report shows the newest grant date held.

### US-033: Know the source of every passage

As a patent prior-art searcher, I want to see the source release, licence and attribution of each patent passage, so that I can cite the passage and its origin in a legal context.

*Story of:* REQ-007, REQ-008. *Delivered by:* [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314), [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318).

Acceptance:

- Each record shows the upstream release and the licence class (public domain or CC-BY).
- Attribution required by the licence is kept on `search` and `get` responses.
- The raw XML input is referenced by hash and URL.
