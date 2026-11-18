# L3: quality

The golden set, the red/green loop and the sampling that catches silent errors. Source: XADR-SCITADEL-008 §13 (quality: golden set, red/green loop, random-sample QC; H7, vig-os/scitadel [#321](https://github.com/vig-os/scitadel/issues/321)). The patent corpus uses the same harness (§6). The run ledger's QC gate is `QcGate` ([DES-014](tessera-boundary.md)); promotion is `GenerationCatalog` ([DES-012](tessera-boundary.md)).

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). Every DES below is `proposed`. Where the ADR names the ANN-recall check after vig-os/tessera#769, the interim index is checked the same way (S-001).

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-043 | Golden set and the red/green loop | SYS-007, SYS-066 | DES-014, DES-038 |
| DES-044 | Random-sample QC, embedding checks and upgrade diff | SYS-007, SYS-060, SYS-069 | DES-012, DES-014, DES-043 |

## 1. Golden set and red/green loop (DES-043)

- **The set.** A stratified fixture set of about 500 to 2,000 papers (SYS-007). Strata: source type (JATS, HTML, TEI, PDF), publisher, field, year, language; hard cases: math-heavy, table-heavy, scanned, two-column, supplementary material, retracted; **a patent stratum** of utility, design, plant and reissue patents, chemistry-heavy, many-claims and drawings-heavy ones. Each fixture is the raw input plus the expected output, as `insta` snapshot tests.
- **Split by licence.** CC BY, CC0 and public-domain fixtures live in the public fixtures crate and run in public CI; all others live in a private fixture bucket and run on fleet runners only. A fixture's licence class decides its home when it is added.
- **The loop.** Every extraction failure or QC flag: (1) quarantine the raw input; (2) add a fixture with a failing test (red); (3) fix it (green); (4) the case joins the golden set permanently. The hub may open the issue itself, respecting the licence split.
- **Calibration.** Escalation thresholds of the cascade ([DES-038](extraction-cascade.md)) are fit on the set and refit when a tier's model changes.

## 2. Random-sample QC and upgrade diff (DES-044)

| Check | Rule |
|---|---|
| QC metrics per work | extracted-text-to-PDF ratio, empty sections, table parse rate, extractor confidence; columns on `works` ([DES-036](document-model.md)) |
| Ingest sample | a fixed random sample per batch goes through T3 and T4 (licence permitting) regardless of flags; 300 samples with 0 errors bound the error rate below about 1 % at 95 % confidence (rule of three); error rates are tracked per source and per extractor version |
| Embedding checks | NaN, norm and duplicate checks; self-retrieval; recall@k on golden queries; ANN recall against exact search; drift between model versions on the golden set before any re-embedding |
| Confirmed errors | become red fixtures ([DES-043](quality.md)) |
| Upgrades | an extractor, model or threshold change runs on the golden set and produces a diff report; only after review is the corpus re-derived (SYS-069) |
| Promotion | a candidate generation is promoted only when its QC gate passed ([DES-012](tessera-boundary.md), SYS-060); the QC report is kept ([DES-021](adapters-and-pool.md)) |

## 3. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-137 | DES-043 | Inject a failing extraction on a fixture work and drive it through the loop; add one CC BY-NC fixture | the raw input is quarantined; a red test exists before the fix; the fixed case stays in the set; the NC fixture lands in the private bucket and never in public CI |
| TEST-138 | DES-044 | A fixture batch of 300 with one silent error, an embeddings product with a NaN and a duplicate, and a changed extractor version | the sample catches the error and records a red fixture; the NaN and duplicate are flagged and block promotion; the diff report exists before any re-derive starts |
