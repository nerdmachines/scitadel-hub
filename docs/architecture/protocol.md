# L3: protocol

The client/hub wire contract, the MCP server on top of it and the conformance kit. Source: XADR-SCITADEL-008 §7 (client/hub protocol), the licence split of §16 and the `capabilities` use of §14.

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). **Superseded text.** XADR-SCITADEL-008 §7 and §14 make client-side query embedding the default and tag a client-supplied query vector with a model id; the owner's decision of 2026-11-18 (D-009, SYS-071, SYS-027) replaces that: `search` takes text only, the hub embeds it, and a request carrying a vector is rejected. This file follows SYS-027. Every DES below is `proposed`.

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-032 | Protocol crate and the five calls | SYS-026, SYS-027, SYS-025, SYS-031 | DES-001, DES-016, DES-026, DES-027 |
| DES-033 | Response envelope: provenance, licence class, retraction, attribution, untrusted text | SYS-028, SYS-010, SYS-052 | DES-009, DES-011, DES-032 |
| DES-034 | Standalone MCP server | SYS-029 | DES-032, DES-033 |
| DES-035 | Conformance kit | SYS-030, SYS-026 | DES-032, DES-033 |

## 1. Protocol crate and the five calls (DES-032)

`scitadel-hub-proto` holds the request and response types. It lives in the vig-os/scitadel client repository under `MIT OR Apache-2.0`, ships with its release train and is the only crate the hub and a client share; the client never depends on the hub repository and no integrator inherits AGPL by adding it (XADR-SCITADEL-008 §1, §16; D-001). Domain types (`Paper`, identifiers, `UntrustedText`) come from `scitadel-core`.

| Call | Input | Output |
|---|---|---|
| `search` | query **text**, filters, mode (`bm25`, `vector`, `hybrid`), limit | snippet-only candidates (IDs, scores, snippets), each with the mode that produced it, plus a search-level `reranked: bool` |
| `get` | up to 100 IDs | records |
| `neighbours` | ID, edge kind, depth | graph neighbours ([DES-027](retrieval.md)) |
| `coverage` | none | sources, subsets and product versions held; changes on every delta or release |
| `capabilities` | optionally an index id | per index: embedding model id, revision, quantization, dimensions, truncation, the hash of the query-embedding definition, the analyzer configuration and the rerankers; changes on an index rebuild |

- **Two advertisements, cached independently.** `coverage` says what the hub holds; `capabilities` says how each index is built. A client reads `coverage` to decide whether to fall through ([DES-053](client-app.md)).
- **Text only; vector refused.** A request carrying a query vector is rejected with a documented protocol error whatever model it claims; the hub embeds the text through `QueryEmbedder` ([DES-016](tessera-boundary.md)) and refuses the vector leg on a model mismatch (`ErrorKind::ModelMismatch`), never re-embedding under another model.
- **The wire carries references, not documents.** IDs, scores and snippets; bytes flow only on `detach` ([DES-051](client-app.md)). The hub never serves PDF bytes (D-007).
- **Version and transport.** Every response carries the protocol version (SYS-026). HTTP plus JSON first; the types do not assume it. TLS and anonymous access are [DES-049](tenancy-and-layered-hubs.md).
- **Errors.** The `ErrorKind` of [DES-001](tessera-boundary.md) maps one-to-one to documented protocol errors; no backend type appears on the wire.

## 2. Response envelope (DES-033)

Every record in every response carries the five fields of SYS-028, so a client can ground an agent against them:

| Field | Source |
|---|---|
| product seal or version | the generation that answered ([DES-012](tessera-boundary.md)) |
| licence class | the row's column ([DES-054](licensing-and-tdm.md)) |
| retraction status and date | the shard column joined at index build ([DES-026](retrieval.md)) |
| per-row attribution | licence and source (for example PatentsView, [DES-031](patents.md)) |
| `answered_by` | `hub`, a live source or `local-subset:<id>` ([DES-052](client-app.md)) |

Every text field arrives as `UntrustedText`; the hub wraps it and a client treats it as data, never as instructions. A vector response also names the hash of the query-embedding definition used (SYS-071). Provenance of each record is the `prov_id` of [DES-040](provenance.md).

## 3. Standalone MCP server (DES-034)

A separate binary in the client repository exposes tools for search, get-by-ID, neighbours and coverage over the same crate, with versioned and documented tool schemas (SYS-029). It adds no capability the protocol lacks and no cache of its own; its goal is a citation-existence rate of at least 99 % *(estimate)* (OUT-001). Tool schema versions follow the protocol version.

## 4. Conformance kit (DES-035)

CC0-1.0 test vectors and a verifier live in a sibling repository, so relicensing the hub cannot drag them along; the protocol prose spec is under the Community Specification License 1.0 (XADR-SCITADEL-008 §16; [DES-056](licensing-and-tdm.md)). The reference implementation passes every vector in CI, and the public CC0 slice `scitadel-hub-fixtures` is the one exception to the walled corpus, held open as an open question of the ADR (its question 2).

## 5. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-126 | DES-032 | Each call over HTTP against a fixture hub, including a `search` with a query vector, a vector leg with a mismatched index, `get` of 101 IDs and a cached `coverage` across a delta | 5 calls answer; protocol version on 100 % of responses; vector requests rejected with the documented error; the 101-ID call refused; `coverage` changes with the delta and `capabilities` does not |
| TEST-127 | DES-033 | 1,000 records from `search`, `get` and `neighbours` over a fixture with a retracted work, a patent and a local-subset answer | 100 % of records carry the five fields; 100 % of text wrapped as untrusted; the retracted record shows status and date |
| TEST-128 | DES-034 | The MCP server against the fixture hub, with a tool-schema snapshot | 4 tools answer; every schema versioned; a snapshot change without a version bump fails |
| TEST-129 | DES-035 | The verifier run against the reference implementation and against three deliberately non-conforming servers | 100 % of vectors pass on the reference; each broken server fails at least one vector |
