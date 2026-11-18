# Open questions

Spikes (`S`) and contradictions between sources (`C`) found while designing L3 and L4. Each has a discussion issue in milestone M0 with the label `question`, and a node in the [trace graph](traceability/README.md) delivered by that issue. A row stays here until its issue closes; the decision then moves into the design it names. Decided points are not repeated here: where the query embedder runs is decided (hub-side, D-009, SYS-071), and choosing its model and placement is the benchmark of TEST-091, not an open question.

> **Source legend.** As in [the tessera boundary](architecture/tessera-boundary.md). The "Proposed" option is the one the design uses until the issue is settled.

## Spikes

| ID | Question | Options | Owner | Issue |
|---|---|---|---|---|
| S-001 | Does the interim IVF-flat index meet SYS-019 on the stage-0 slice (recall ≥ 0.95 against exact scan, p95 ≤ 20 ms *(estimate)*), or is the optional HNSW cache needed before [vig-os/tessera#769](https://github.com/vig-os/tessera/issues/769)? ([DES-006](architecture/tessera-boundary.md)) | IVF-flat only, tuned (proposed); IVF-flat plus HNSW cache in a `+C` subvolume; exact scan only | hub architect (spike on ksb) | [#17](https://github.com/nerdmachines/scitadel-hub/issues/17) |
| S-002 | Is the interim streaming `TableProvider`, without tessera filter pushdown ([vig-os/tessera#654](https://github.com/vig-os/tessera/issues/654)), fast enough for `get` of 100 IDs (SYS-025) and hybrid search (SYS-022) on the slice? ([DES-003](architecture/tessera-boundary.md)) | key index to leaf, decode only those leaves (proposed); a hot-leaf cache in `index/`; wait for tessera | hub architect (spike on ksb) | [#18](https://github.com/nerdmachines/scitadel-hub/issues/18) |

## Contradictions

| ID | Question | Options | Owner | Issue |
|---|---|---|---|---|
| C-001 | SYS-019 stores embeddings as native Vortex fixed-size lists, which tessera refuses above width 8 until [vig-os/tessera#768](https://github.com/vig-os/tessera/issues/768); the interim stores them as fp16 blob blocks inside `.tsra`. ([DES-006](architecture/tessera-boundary.md)) | accept the interim and re-seal on #768 (proposed); wait for #768; vectors outside `.tsra` (rejected) | owner | [#19](https://github.com/nerdmachines/scitadel-hub/issues/19) |
| C-002 | Issue #5's example of "Parquet-in-object-store staging" against XADR-SCITADEL-008 §2 (internal staging only) and `.tsra` as the only product format. ([DES-021](architecture/adapters-and-pool.md)) | `staging/parquet/` only, never in a bucket (proposed); also in `scitadel-hub-runs` | hub architect; owner confirms | [#20](https://github.com/nerdmachines/scitadel-hub/issues/20) |
| C-003 | OpenAlex paging: `per_page=200` in SYS-003 and XADR-SCITADEL-008 §5, a documented maximum of 100 in [vig-os/scitadel#315](https://github.com/vig-os/scitadel/issues/315). Sets the pool's credit budget. ([DES-019](architecture/adapters-and-pool.md)) | verify against the API and amend SYS-003 in a follow-up (proposed); keep 200 if documented | hub architect | [#21](https://github.com/nerdmachines/scitadel-hub/issues/21) |
| C-004 | The PatentRef snapshot (about 504 GB) recommended on [vig-os/scitadel#314](https://github.com/vig-os/scitadel/issues/314) exceeds the 380 GiB stage-0 raw budget under keep-everything (SYS-014). ([DES-021](architecture/adapters-and-pool.md)) | no bulk snapshot at stage 0, per-request only (proposed); the 167 GB part as a one-off; defer to the warm tier | owner | [#22](https://github.com/nerdmachines/scitadel-hub/issues/22) |
