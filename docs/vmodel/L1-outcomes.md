# L1: outcomes

The wanted outcomes as measurable targets. A target marked *(estimate)* is a first value derived from back-of-envelope figures in the source decision record or from the shape of the work; it is calibrated by the first measurement and then confirmed or changed by the owner. A target without the mark is fixed by an invariant, a statistic or a legal deadline. Each outcome `measures` one or more [requirements](L1-requirements.md).

> **Source legend.** `XADR-SCITADEL-008` is the vig-os/scitadel decision record "scitadel-hub: a lab corpus server" (ADR 008, status Proposed, [pull request 317](https://github.com/vig-os/scitadel/pull/317)). `§N` is a section of it and "decision N" one of its numbered decisions. Issue references such as `vig-os/scitadel#314` point at the issue that delivers the node. Every identifier below is a node in the [trace graph](../traceability/README.md), checked by `tools/trace-check`.

| ID | Outcome | Target | Unit | Measured by | Measures |
|---|---|---|---|---|---|
| OUT-001 | Citation-existence rate of grounded answers | ≥ 99 *(estimate)* | % of cited DOIs and patent numbers that resolve to a record the hub holds | grounding benchmark on a pinned corpus release | REQ-010, REQ-007 |
| OUT-002 | Citation support rate | ≥ 90 *(estimate)* | % of citations whose cited passage supports the claim | grounding benchmark with a human-labelled sample | REQ-010 |
| OUT-003 | Licence correctness | 0 | rows served outside the permitted licence class, over the whole test corpus and fuzzed queries | negative test suite plus query fuzzing in CI (an invariant, not a statistic) | REQ-008 |
| OUT-004 | Ingest throughput per GPU-hour | ≥ 5,000,000 *(estimate)* | text chunks embedded per GPU-hour | job logs of bulk-embedding runs (derived from about 250 M chunks in 1 to 2 days on the local GPU) | REQ-019, REQ-005 |
| OUT-005 | Query latency on CPU | ≤ 250 *(estimate)* | ms, p95, hybrid search without rerank at lab scale (about 20 users) on a CPU-only host | load test recording p95 per step | REQ-019, REQ-003 |
| OUT-006 | Delta freshness, literature | ≤ 24 *(estimate)* | hours from publication to searchable, for subscribed topics | freshness report per subscription | REQ-002 |
| OUT-007 | Delta freshness, patents | ≤ 7 *(estimate)* | days from weekly grant release to searchable | freshness report for the grant delta | REQ-002 |
| OUT-008 | Free-key budget compliance | ≤ 100 | % of the daily free-key allowance used, on each of 7 consecutive days | credits-used log of the daily jobs | REQ-002 |
| OUT-009 | Extraction QC pass rate | ≥ 95 *(estimate)* | % of works per batch that pass automated QC without escalation beyond T1 | per-work QC columns on the works block | REQ-006 |
| OUT-010 | Silent-error bound per batch | < 1 | % upper bound on the error rate at 95 % confidence (300 random samples with no confirmed error) | random-sample QC through T3 and T4 on every batch (rule of three) | REQ-006 |
| OUT-011 | Retrieval quality | ≥ 0.90 and ≥ 0.95 *(estimate)* | recall@10 on golden queries, and ANN recall against exact search | golden-query evaluation and ANN-versus-exact comparison | REQ-003, REQ-004 |
| OUT-012 | Provenance completeness | 100 | % of served rows that resolve to a product seal and to their raw-input hash and URL | completeness check over the sealed products | REQ-007 |
| OUT-013 | Retraction coverage | 100 | % of held records matching the retraction list that are flagged; the flag lags by at most one index build | join audit against the retraction list at each index build | REQ-009 |
| OUT-014 | Added latency on hub failure | ≤ 3 *(estimate)* | s, p95 extra time before the live-source answer when the hub is down or slow | fault-injection test of the hub source adapter | REQ-011 |
| OUT-015 | Offline subset size and latency | ≤ 3 and ≤ 100 *(estimate)* | GB for a 50,000-paper subset with its indexes, and ms p95 local query on a laptop | size and latency measurements on a detached reference subset | REQ-013 |
| OUT-016 | Opt-out compliance | 100 | % of re-ingested sources whose TDM opt-outs are re-checked and honoured in the same cycle | audit log of each re-ingest | REQ-017 |
| OUT-017 | Recovery time | ≤ 8 *(estimate)* | hours from an empty host to a serving hub from backup | restore drill | REQ-018 |
| OUT-018 | Erasure turnaround | ≤ 30 | days from an erasure request to its removal from the index | request log and erasure test (the GDPR response deadline is one month) | REQ-016 |
| OUT-019 | On-prem time to first query | ≤ 8 *(estimate)* | hours from a clean machine to a passing protocol smoke test | install drill on a clean machine | REQ-015 |
| OUT-020 | Tenant isolation and metering accuracy | 0; ≤ 1 *(estimate)* | cross-tenant reads in the isolation tests; % metering reconciliation error | microVM tenant simulation | REQ-014 |
| OUT-021 | Annotation layer isolation | 0 | annotation leaks across layers in the permission-matrix test | permission-matrix test | REQ-012 |
| OUT-022 | Release hygiene | 100 and 0 | % of releases that ship a NOTICE and an SBOM, and dependencies that violate the licence allowlist | release-checklist automation | REQ-020 |
| OUT-023 | Phase-1 corpus depth | ≥ 5,000,000 *(estimate)* | licence-clean works held with structured text or abstracts, plus all US grants from 1976 (about 8,000,000 patents) | corpus row counts per source in the coverage response | REQ-001 |
| OUT-024 | Lossless figure fidelity | 100 | % of stored figures whose decoded pixels (or rendered SVG) equal the source image; figures that came from an embedded JPEG also reproduce the original bytes | figure round-trip check on golden-set fixtures | REQ-005 |

## Sources

- OUT-001: [vig-os/scitadel#332](https://github.com/vig-os/scitadel/issues/332); delivered by [vig-os/scitadel#332](https://github.com/vig-os/scitadel/issues/332)
- OUT-002: [vig-os/scitadel#332](https://github.com/vig-os/scitadel/issues/332); delivered by [vig-os/scitadel#332](https://github.com/vig-os/scitadel/issues/332)
- OUT-003: [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318); delivered by [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)
- OUT-004: XADR-SCITADEL-008 §15; delivered by [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311), [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314)
- OUT-005: XADR-SCITADEL-008 §14; delivered by [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311)
- OUT-006: [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315); delivered by [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315)
- OUT-007: [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314); delivered by [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314)
- OUT-008: [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315); delivered by [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315)
- OUT-009: [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321); delivered by [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321)
- OUT-010: XADR-SCITADEL-008 §13; delivered by [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321)
- OUT-011: [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321); delivered by [vig-os/scitadel#321](https://github.com/vig-os/scitadel/issues/321), [vig-os/tessera#778](https://github.com/vig-os/tessera/issues/778)
- OUT-012: [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319); delivered by [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319), [vig-os/tessera#782](https://github.com/vig-os/tessera/issues/782)
- OUT-013: XADR-SCITADEL-008 §15; delivered by [vig-os/scitadel#323](https://github.com/vig-os/scitadel/issues/323)
- OUT-014: [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316); delivered by [vig-os/scitadel#316](https://github.com/vig-os/scitadel/issues/316)
- OUT-015: XADR-SCITADEL-008 §14; delivered by [vig-os/scitadel#318](https://github.com/vig-os/scitadel/issues/318)
- OUT-016: [vig-os/scitadel#330](https://github.com/vig-os/scitadel/issues/330); delivered by [vig-os/scitadel#330](https://github.com/vig-os/scitadel/issues/330)
- OUT-017: XADR-SCITADEL-008 §8; delivered by `gerchowl/g-fleet#1363`
- OUT-018: XADR-SCITADEL-008 §12; delivered by [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333)
- OUT-019: XADR-SCITADEL-008 §8; delivered by `nerdmachines/scitadel-hub-deploy#2`
- OUT-020: XADR-SCITADEL-008 §8; delivered by `nerdmachines/scitadel-hub-deploy#1`
- OUT-021: XADR-SCITADEL-008 §12; delivered by [vig-os/scitadel#325](https://github.com/vig-os/scitadel/issues/325)
- OUT-022: XADR-SCITADEL-008 §16; delivered by [vig-os/scitadel#333](https://github.com/vig-os/scitadel/issues/333)
- OUT-023: XADR-SCITADEL-008 §15; delivered by [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314), [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315)
- OUT-024: XADR-SCITADEL-008 §9; delivered by [vig-os/scitadel#319](https://github.com/vig-os/scitadel/issues/319)

## Notes

- Targets state what the programme wants, not what a current system achieves; no measurement exists yet.
- OUT-004 is derived from the phase-1 embedding budget: about 250 million chunks in one to two GPU-days is 5 to 10 million chunks per GPU-hour, so the target takes the lower end.
- OUT-010 is the rule of three: 300 random samples with no confirmed error bound the error rate below about 1 % at 95 % confidence.
- No outcome here sets a commercial figure (PRIN-013).
