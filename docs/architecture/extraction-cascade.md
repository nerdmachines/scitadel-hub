# L3: extraction cascade

The tiered, licence-gated pipeline that turns raw inputs into document-model rows, and the image processing that reuses kept originals. Source: XADR-SCITADEL-008 §10 (extraction pipeline) and the image-processing part of §12 (raw retention). The service definitions the tiers run through are `ServiceRegistry` ([DES-015](tessera-boundary.md)); the licence gate that precedes each tier is gate 5 of [DES-020](adapters-and-pool.md); intermediates are kept by `ArtefactStore` ([DES-013](tessera-boundary.md)); GPU exchange is [DES-022](adapters-and-pool.md).

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). Every DES below is `proposed`. No tier names a host or a model: each runs through a service definition (SYS-067). The model sizes of open question 9 and the budgets of open question 10 of the ADR are definition values, set by the golden-set bake-off and the owner.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-038 | Tiered cascade runner | SYS-006, SYS-067, SYS-069 | DES-014, DES-015, DES-020, DES-040 |
| DES-039 | Image processing from kept originals | SYS-064, SYS-065, SYS-066 | DES-013, DES-022, DES-037 |

## 1. Tiered cascade runner (DES-038)

**Source preference per work:** JATS (PMC and Europe PMC bulk); publisher HTML; Grobid TEI from the OpenAlex content API (fills gaps only: each download is paced by its small daily allowance); the hub's own PDF extraction.

| Tier | What | Executor (a definition's choice) | Escalates when |
|---|---|---|---|
| T0 | parse JATS, publisher HTML or USPTO XML ([DES-030](patents.md)) | CPU | no structured source, or a QC flag |
| T1 | tool extraction (layout, OCR, math OCR) | CPU and GPU queue | a QC flag, or two extractors disagree |
| T2 | System One yes/no checks ("is this table complete?", "is this the reading order?") | a hosted or local scorer | the answer is below the calibrated confidence |
| T3 | a vision-language model compares the page image with the extraction and repairs it; the smallest model that meets the QC target ([DES-043](quality.md)) | a GPU queue, optionally another host, by definition | it cannot repair, or confidence is low |
| T4 | a frontier model's final verdict through an external API | external API | fails: quarantine and a red fixture |

- **Runner.** `CascadeRunner` takes a work and its raw artefact, resolves the active definition of each tier from the registry, runs only the tiers the verdicts require and writes rows through `ProductStore`, each with a `ProvContext` carrying the definition hash (SYS-068). A move of a tier to another executor is a new definition version, not a code change (SYS-069).
- **Licence-gated.** The tier gate refuses a class a definition does not list; T4 takes only CC BY, CC0 and public domain, so paywalled or unlicensed content stops at T3 on the hub's own hardware (SYS-006).
- **Budgets.** T3 and T4 have caps; at a cap the work **queues**, nothing is skipped silently (SYS-006).
- **Verdicts.** Every tier's verdict (model and version, prompt hash, decision, confidence) is recorded ([DES-040](provenance.md)).
- **Thresholds** are calibrated against the golden set and recalibrated when a tier's model changes ([DES-043](quality.md)).
- **Structured first.** Where JATS, LaTeX or XML exists, T0 ingests native structure (equations, tables, figure references, bibliographies); T1 to T3 are reserved for PDF-only items. Formulas come as LaTeX or MathML; a flattened formula text is a last fallback only.

## 2. Image processing from kept originals (DES-039)

Because every raw input and every tier's intermediate is kept (SYS-014), three jobs start from stored bytes with no upstream fetch:

- **Page renders and region crops** for the extraction-feedback loop: a report on a bad table or formula is shown against its source region and re-extracted from it; a crop shown to a reporting user is a derived image of a licence-clean page, gated like any other content (SYS-064). On the paid tier it is served only through `PaidTier::crop`, which resolves the element through the paid read gate before rendering, so a withdrawn source's or item's crop is never shown ([DES-057](tessera-boundary.md), path 21). Renders live in an evictable cache with a hard size cap ([DES-021](adapters-and-pool.md)).
- **Image embeddings** of figures and page regions ([DES-037](document-model.md), SYS-065).
- **Re-running a vision tier** (T1 to T4) on a chosen element, work or batch from stored inputs and intermediates alone. A re-run writes new intermediates keyed by input hash, tool, model, version and definition hash, leaves the old ones intact and passes the golden-set diff and promotion ([DES-044](quality.md), SYS-066).

Kept is not served: PDFs are never served and intermediates are internal inputs, not products (D-007).

## 3. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-132 | DES-038 | A fixture set across the four sources with injected QC flags, a CC BY-NC item and a paywalled item, a T3 cap and a stub definition for each tier | each work stops at the lowest tier its verdicts allow; the NC and paywalled items never reach T4; work over the cap queues and is reported; every row names its definition hash; changing a tier's executor needs only a new definition |
| TEST-133 | DES-039 | A fixture work re-run at T3 from stored intermediates with the network disabled; a reported region crop | 0 upstream fetches; new intermediates written and old ones byte-identical; the crop comes from the kept page and is gated by its licence class; the re-run is held at the golden-set diff |
