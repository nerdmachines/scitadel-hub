# L3: client app

What the client does with the hub: fall-through, the client store model, `detach` and offline routing. Source: XADR-SCITADEL-008 §17 (client app and tiers), the client store model of §12, the fall-through of §7 and offline mode of §14. The client repository is vig-os/scitadel; this file records the hub-facing behaviour the hub's protocol and shards must support, not the client's internals.

> **Source legend.** As in [the tessera boundary](tessera-boundary.md). Commercial terms are out of scope and kept in the private repositories. Every DES below is `proposed`. **Superseded text:** the client no longer embeds queries (D-009), so a detached subset answers BM25, filters and neighbours locally and vector search needs the hub (SYS-033).

| DES | Title | Realises | Uses |
|---|---|---|---|
| DES-051 | Client store model, `detach` and no bulk export | SYS-032, SYS-034, SYS-033 | DES-011, DES-037, DES-032 |
| DES-052 | Local-subset routing and offline mode | SYS-033 | DES-051, DES-032 |
| DES-053 | Hub source and fall-through | SYS-031, SYS-028 | DES-018, DES-032 |

## 1. Client store model, `detach` and no bulk export (DES-051)

- **The client keeps references.** A local scitadel stores identity (DOI, OpenAlex ID, content hash), annotations, reviews and its configured hub; by default no PDF bytes.
- **The hub keeps bytes, once per lab.** A client that acquires a work through its own acquisition path may offer the artefact to the hub (upload-on-acquire) with its licence class, entitlement and acquisition provenance; the hub keeps it as an ingest input ([DES-013](tessera-boundary.md)). It is a gated feature, disabled in phase 1 ([DES-054](licensing-and-tdm.md)). What an entitled colleague then receives is C-008: this file follows D-007 and hands out the structured document only.
- **`detach` / `export`** pulls full copies of a user's own tracked works into local storage, checking the licence per artefact. A full copy is the **structured document**: elements, tables, figures as JPEG XL ([DES-037](document-model.md)), references, provenance and the user's annotations, rendered locally by the reader. It can emit a per-paper `.tsra` whose provenance points at the hub shard's seal. **No PDF bytes** are handed out, on `open`, `detach` or anything else (D-007, SYS-032).
- **No bulk export.** The processed corpus is the hub's running service, not a dataset download (D-003): there is no call, role or endpoint that exports a collection (SYS-034, [DES-032](protocol.md)). Individuals take their own workspace with them; the corpus stays behind the wall.
- **Guardrails.** Never a bulk proxy for paywalled content: the hub caches only what members fetched individually, and the acquisition pacer still applies upstream. Access logging is limited to entitlement checks, with bounded retention and no reading history ([DES-055](licensing-and-tdm.md), SYS-042).

## 2. Local-subset routing and offline mode (DES-052)

A detached topic subset with its own indexes (text, chunk embeddings and BM25, about 1 to 3 GB for 50,000 papers *(estimate)*) gives local millisecond search on a laptop. The client routes a query to a covering local subset before the remote hub and reports `answered_by: local-subset:<id>` ([DES-033](protocol.md), SYS-033); a local subset serves BM25, filters and neighbours, and vector search on text goes to the hub because the client ships no embedding model. Remote reads of a hub's `.tsra` over HTTP ranges (`RemoteRead`, [DES-010](tessera-boundary.md)) suit column scans and `get` by ID, not BM25 or ANN random access, which is why `detach` puts the subset on local disk.

## 3. Hub source and fall-through (DES-053)

The client has a `hub` source tried **before** live APIs for the sources the hub's `coverage` declares ([DES-032](protocol.md)), and falls through on a miss, an error or a bounded timeout; every result records `answered_by` (SYS-031). The seam is the client's search adapter and is distinct from the hub's ingest adapter ([DES-018](adapters-and-pool.md)). The unchanged client keeps working with no hub. The client is one product in three builds (Tauri 2 desktop, Tauri 2 mobile, a web dual build) on one Rust backend with typed transport; the CLI, TUI and MCP server are the same engine with other front-ends. The free local tier runs offline-first on local SQLite and points at live APIs or any hub the user is entitled to.

## 4. Verification

| Test | Verifies | Method | Pass criterion |
|---|---|---|---|
| TEST-145 | DES-051 | A fixture client detaching 10 tracked works of mixed licence classes, with an attempt to fetch a PDF and to export a collection | each full copy is a structured document with annotations; 0 PDF bytes on any path; 0 collection-export endpoints; a work whose licence forbids it is refused per artefact |
| TEST-146 | DES-052 | A 50,000-paper fixture subset on a laptop-class machine, queried by text in BM25 and vector mode, with and without the hub | BM25, filters and neighbours answer locally with `answered_by: local-subset:<id>`; vector queries go to the hub; local p95 is recorded against the SYS-033 bound |
| TEST-147 | DES-053 | A mock hub with a covered source, an uncovered source, an error and a timeout | covered: the hub answers; the others fall through to the live fixture; 100 % of results carry `answered_by`; the client works unchanged against no hub |
