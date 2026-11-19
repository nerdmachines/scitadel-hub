# Risks

The cross-level risk register of [ADR-0001](../decisions/0001-v-model-and-traceability.md): each `RISK` names the designs and tests that mitigate it, as `mitigated_by` edges in the [trace graph](../traceability/README.md). The gate rejects a risk without one. A mitigation listed here exists as a node; where none existed, this register says so and adds the smallest node that does.

**Scales.** Likelihood over phase 1: *low* (not expected), *medium* (plausible), *high* (expected unless mitigated). Impact: *low* (a degraded feature), *medium* (lost time or a delayed milestone), *high* (a legal breach, lost data or a hub that cannot serve).

| ID | Risk | Likelihood | Impact | Mitigated by |
|---|---|---|---|---|
| RISK-001 | **General-purpose AI assistants add native grounding in the scientific literature,** so a separate corpus hub is needed less. | high | medium | an open protocol that any agent or client can call ([DES-032](../architecture/protocol.md)); provenance per row, from every answer to its sealed input ([DES-040](../architecture/provenance.md)); the same hub on-prem, in the lab's own environment ([DES-047](../architecture/tenancy-and-layered-hubs.md)) |
| RISK-002 | **A TDM opt-out is missed or a withdrawal is still served** (robots.txt, TDMRep, `noai`, an item-level reservation). | medium | high | the gate order with the opt-out checks before any fetch ([DES-020](../architecture/adapters-and-pool.md)); the recorded exclusion view applied on every paid read ([DES-058](../architecture/tessera-boundary.md#the-paid-read-rule)); TEST-075 |
| RISK-003 | **A GDPR or profiling error:** a reading history or an author profile is kept, or an erasure request is not honoured. | medium | high | privacy controls: erasure, bounded logs, no reading history ([DES-055](../architecture/licensing-and-tdm.md)); TEST-062. Whether soft-delete suffices for erasure is still S-006. |
| RISK-004 | **Tessera features land late** (filter pushdown, vector columns, IVF, media columns, the wave-1 format). | high | medium | every capability behind a hub-owned trait with an interim backend ([DES-001](../architecture/tessera-boundary.md)); one conformance suite per trait run against every backend, so a swap changes no caller ([DES-017](../architecture/tessera-boundary.md)); TEST-110 |
| RISK-005 | **Single-GPU throughput:** one shared GPU cannot keep up with the cascade and the embedding sweeps. | high | medium | chunked, checkpointed GPU jobs queued in the run ledger ([DES-022](../architecture/adapters-and-pool.md)); a tiered cascade that runs the GPU tiers only where cheaper tiers fail ([DES-038](../architecture/extraction-cascade.md)); TEST-070 |
| RISK-006 | **Solo-maintainer bus factor:** the hub depends on one person's knowledge. | medium | high | placement and models in versioned service definitions, not in code or memory ([DES-015](../architecture/tessera-boundary.md)); the restore drill (TEST-067); and a handover drill, TEST-154, added here because no node covered it |
| RISK-007 | **Extraction quality regresses** after a model, tool or definition change. | medium | medium | the golden set and its red/green loop ([DES-043](../architecture/quality.md)); random-sample QC and the upgrade diff ([DES-044](../architecture/quality.md)); TEST-027 |
| RISK-008 | **A licence is misclassified,** so content is cached, processed or served beyond what its licence allows. | medium | high | licence classes and the phase-1 gated features ([DES-054](../architecture/licensing-and-tdm.md)); TEST-021 (per-source audit) and TEST-074 (no NC or ND in a paid index) |
| RISK-009 | **Data loss on stage-0 hardware:** one KC3000 pool, and hot and warm share anvil as one failure domain. | medium | high | snapshots, the cold mirror and restore ([DES-042](../architecture/artefact-store.md)); the off-anvil copy gates keep-everything (TEST-092); TEST-067 |
| RISK-010 | **A restore rolls both authority stores back consistently,** so a fourth base is granted or a forgotten withdrawal is served. | low | high | the hardened restore ([DES-059](../architecture/tessera-boundary.md#hardened-restore)); TEST-153 |

## The handover drill (TEST-154)

RISK-006 had no mitigation in the graph: every existing node assumes the maintainer runs it. TEST-154 is the smallest node that tests the risk itself.

| Test | Mitigates | Method | Pass criterion |
|---|---|---|---|
| TEST-154 | RISK-006 | Once per milestone, a second operator with only the hub's repositories, the runbooks and access to the sops-held secrets installs the hub on an empty microVM from the NixOS module, restores from cold, runs one ingest run and a release dry run, and records every question they had to ask | all four steps complete without the maintainer; every recorded question becomes a documentation fix before the milestone closes |
