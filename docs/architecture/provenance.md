# L3: provenance

What every product, work and row records about how it was made. Source: XADR-SCITADEL-008 §11 (provenance of every process), with the definition hash of §10. The write path is `ProvenanceSink` ([DES-009](tessera-boundary.md)); the `ProvContext` capability and the run ledger are [DES-001](tessera-boundary.md) and [DES-014](tessera-boundary.md); the definitions are [DES-015](tessera-boundary.md). This file fixes the record model they carry.

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). Every DES below is `proposed`. Today tessera records provenance only per product, and a blake3 source reference fails `tessera provenance --require-complete`; [vig-os/tessera#782](https://github.com/vig-os/tessera/issues/782) adds external inputs, typed multi-step pipelines and per-row `prov_id`, and until it lands the interim of DES-009 carries these records.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-040 | Provenance record model: product, work, row and verdict | SYS-009, SYS-068, SYS-069, SYS-028 | DES-009, DES-014, DES-015 |

## 1. Provenance record model (DES-040)

| Level | What is recorded | Where |
|---|---|---|
| Product | tool and version, configuration, model-weights hash, input hashes (raw artefacts or upstream products), GPU job id and host, the cascade verdicts that shaped it, upstream release and subset filter | `ProvenanceSink` pipeline steps of the product; one step per tool or tier |
| Work | which source and extractor produced the rows, and the highest cascade tier reached | columns on `works` ([DES-036](document-model.md)) |
| Row | a `prov_id` naming the step that wrote it, and with it the definition hash of every service definition used | a column on every product row |
| Verdict | per tier: model and version, prompt hash, decision, confidence | a step record keyed by the work and the tier |
| External input | a raw input the hub does not hold: hash and URL with a state `held`, `cold` or `discarded`, and a fetch check | `ProvenanceSink` external artefacts |

- **Definition hash.** Every run records the hash of each definition it used in the ledger, and every output row's provenance carries that hash, so "which model on which machine produced this value" is answerable per row and a re-derive can target "everything produced by definition X" (SYS-068, SYS-069). The `capabilities` response and the re-embedding window use the same registry.
- **Originals are never touched.** Re-extraction and re-embedding write new derived products; nothing is rewritten in place.
- **No write without provenance.** A write takes a `&ProvContext`; a context whose definition hash does not resolve is refused ([DES-001](tessera-boundary.md)).
- **Across products,** one product links to another by provenance, with the input hashes naming the upstream product's seal.
- **On the wire.** Each record in a response names the seal that produced it ([DES-033](protocol.md), SYS-028).

## 2. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-134 | DES-040 | A fixture shard through two cascade tiers with a verdict at each, a re-derive by definition hash, and an external input recorded as `cold` | every row resolves from `prov_id` to its tool, definition hash and inputs; the re-derive selects exactly the rows of that definition; 0 rows without a `prov_id`; the external input shows its state and passes the fetch check |
