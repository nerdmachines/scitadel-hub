# scitadel-hub

A lab, organisation or personal **corpus server** for [scitadel](https://github.com/vig-os/scitadel). It is the grounded scientific backend that researchers and AI agents query instead of re-fetching and re-parsing the same papers.

> **Status: design.** No code yet. The architecture is
> [ADR-008](https://github.com/vig-os/scitadel/pull/317) (Proposed), tracked in the epic
> [vig-os/scitadel#311](https://github.com/vig-os/scitadel/issues/311). The repo split is
> [H0, vig-os/scitadel#313](https://github.com/vig-os/scitadel/issues/313).

## What it will do

- **Corpus:**
  - an OpenAlex mirror (CC0), from a quarterly snapshot plus daily deltas;
  - worldwide patents;
  - licence-clean full text (CC0, CC-BY, public domain).
- **Document model:** papers are stored as a structured Arrow document model (elements, tables, figures, references) in [tessera](https://github.com/vig-os/tessera) `.tsra` files. The hub stores and serves no PDFs.
- **Extraction:** a tiered cascade, with full provenance for every process, a golden set and random-sample QC.
- **Retrieval:** BM25, vector and citation-graph retrieval, all in Rust and served through DataFusion. No graph database.
- **Answers for agents:** grounded, citable responses. Every record carries provenance and a per-row licence class, served over the scitadel protocol and MCP.
- **Layered hubs:** global → org → group → user, with institutional notes, annotations and reviews on top.

## What is open and what is not

The **tools are published; the processed corpus is not.**
- This server's source: AGPL-3.0-only or a commercial licence, see [LICENSE.md](LICENSE.md).
- The scitadel client and the protocol crate: MIT OR Apache-2.0.
- Supported deployment packaging: comes with the commercial licence.
