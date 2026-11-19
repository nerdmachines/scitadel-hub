# L3: patents

The walled patent corpus from USPTO bulk data. Source: XADR-SCITADEL-008 §6 (patent corpus), with the phase-1 sources of §15. Acquisition goes through the ingest fabric and pool of [adapters and pool](adapters-and-pool.md); the cascade is [extraction cascade](extraction-cascade.md); the document model is [document model](document-model.md).

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). Source issue: vig-os/scitadel [#314](https://github.com/vig-os/scitadel/issues/314) (H1). Every DES below is `proposed`. Pre-grant publications are the second product under #314, sequenced after grants ([C-009 ruling](https://github.com/nerdmachines/scitadel-hub/issues/36#issuecomment-6995802389); XADR-SCITADEL-008 §6 now matches §15).

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-030 | Patent build: T0 parse, claim tree, drawings, tables and embeddings | SYS-004, SYS-008, SYS-065 | DES-018, DES-036, DES-037, DES-038 |
| DES-031 | Patent weekly delta, walled serving and attribution | SYS-004, SYS-028, SYS-034 | DES-024, DES-033, DES-020 |

## 1. Patent build (DES-030)

- **Inputs.** The `PVGPATDIS` TSVs (disambiguated assignees, inventors, locations, CPC, citations) and the weekly Grant Full Text XML, 1976 to now, through one `IngestAdapter` per source ([DES-018](adapters-and-pool.md)). Lapse and legal status come from USPTO's maintenance-fee events file through its own first-party adapter ([C-004 ruling](https://github.com/nerdmachines/scitadel-hub/issues/22#issuecomment-6995799805)). Pre-grant publications are the same adapter with a second descriptor, switched on only after the grant product passes QC and the warm tier exists, and after a size check on one year of pre-grant bulk data ([C-009 ruling](https://github.com/nerdmachines/scitadel-hub/issues/36#issuecomment-6995802389)); EPO DOCDB and other offices are later adapters, each with its own licence check. Pre-1976 patents (images only, would need OCR) are out of scope.
- **Tables.** Patents, claims, description sections, CPC, citations patent→patent and patent→paper, assignees and inventors, as blocks of the document model ([DES-036](document-model.md)); the shard key is in [DES-023](data-model-and-lifecycle.md).
- **T0 for patents.** The USPTO-specific T0 parses the ICE-DTD XML into abstract, description, claims, embedded tables, math and chemistry (MathML, chemical structures) and the description of the drawings. The **claim dependency tree** becomes `claim_depends_on` edges ([DES-027](retrieval.md)). The cascade above T0 is the common one ([DES-038](extraction-cascade.md)).
- **Drawings.** TIFF images take the figure path of [DES-037](document-model.md): lossless storage, image embedding, the vision tier when needed.
- **Embeddings.** Title and abstract, about 8M grants, about 12 GB at fp16 *(estimate)*; the model is a service definition ([DES-015](tessera-boundary.md)).
- **Licence.** US patent text is public domain, so every tier up to T4 is allowed (SYS-006, [DES-020](adapters-and-pool.md)); PatentsView tables are CC BY 4.0 and keep their attribution.
- **Golden set.** The patent stratum of [DES-043](quality.md).

## 2. Weekly delta, walled serving and attribution (DES-031)

- The weekly grant XML becomes a new delta product ([DES-024](data-model-and-lifecycle.md)); the quarterly PatentsView release becomes the new base.
- The patent `.tsra` is **walled**: the hub ingests, embeds, indexes and serves it over `search`, `get` and `neighbours` ([DES-032](protocol.md)) and publishes no bulk copy and no dataset (D-003; SYS-034). Size 100 to 150 GB *(estimate)* in the warm tier for grants; the pre-grant product is sized by the one-year check before it is switched on.
- Per-row attribution rides every `search` and `get` response ([DES-033](protocol.md), SYS-028): PatentsView CC BY 4.0 with attribution, USPTO text public domain in the US.
- **PatentRef stays a client-side stopgap** (a configurable PatentSearch-compatible endpoint, default PatentRef); once a hub holds the patents, the client asks the hub first and PatentRef is only the fall-through ([DES-053](client-app.md)). The hub never depends on it and uses it per request only; it ingests no PatentRef bulk snapshot ([C-004 ruling](https://github.com/nerdmachines/scitadel-hub/issues/22#issuecomment-6995799805)).

## 3. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-124 | DES-030 | One recorded utility patent with 20 claims (6 dependent), a chemistry block, a table and 3 TIFF drawings, plus a PatentsView extract, built end to end | every claim, table and drawing present; 6 `claim_depends_on` edges with the right targets; drawings stored losslessly and bit-identical on decode; every row carries a licence class and a `prov_id` |
| TEST-125 | DES-031 | A weekly delta applied to a base, then `search` and `get` through the protocol for a patent in the delta | the delta row wins; attribution present on 100 % of records; no call or endpoint returns a bulk export or a PDF |
