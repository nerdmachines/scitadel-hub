# ADR 0001: V-model levels, identifiers and traceability

Status: proposed

## Decision

Use the V-model from [epic #1](https://github.com/nerdmachines/scitadel-hub/issues/1),
with graph nodes and edges stored as JSON and checked during development.

| Level | Content | Prefixes | Verification pair |
|---|---|---|---|
| L0 | Principles and owner decisions | `PRIN`, `D` | Decision review |
| L1 | Requirements, user stories, wanted outcomes | `REQ`, `US`, `OUT` | Acceptance tests |
| L2 | System and infrastructure requirements | `SYS` | System tests |
| L3 | Architecture, design and interfaces, including ADRs | `DES`, `ADR`, `XADR` | Integration tests |
| L4 | Detailed design and technical questions | `DES`, `S`, `C` | Unit tests |
| Cross-level | Risks ([register](../vmodel/risks.md)) | `RISK` | Mitigations in designs or tests |
| Verification | Test specifications | `TEST` | Test execution in subsequent slices |

The schema in [schema.json](../traceability/schema.json) owns identifiers:

| Prefix | ID format | Node kind |
|---|---|---|
| `PRIN`, `D`, `REQ`, `US`, `OUT`, `SYS`, `DES`, `RISK`, `TEST`, `S`, `C` | Prefix, hyphen, exactly three decimal digits (for example `REQ-001`) | Same as prefix |
| `ADR` | `ADR-` and exactly four decimal digits | `adr` |
| `XADR` | `XADR-`, uppercase repository slug, hyphen, exactly three decimal digits | `adr` |

Identifiers are unique across all trace files. Repository slugs in external ADR
IDs use uppercase letters, digits and hyphens, starting with a letter.
Local ADR IDs resolve to exactly one `docs/decisions/NNNN-*.md` file. Its standalone
`Status: <status>` header line must equal the node's status. The gate requires
exactly one such unindented line, with one space after the colon, outside
backtick or tilde code fences; fenced examples cannot supply the status. External
ADRs require an HTTP(S) `source` URL; the gate validates its format without fetching it.
Owner decision nodes (`D`) can point to an ADR or issue in `source`.

[Traceability JSON](../traceability/README.md) consists of `nodes.json` and
`edges.json`; additional `*.json` files in that directory may contain either
`{"nodes": [...]}` or `{"edges": [...]}`. `schema.json` is excluded from graph
input. The layout is flat: subdirectories and files other than `README.md`,
`schema.json` and top-level `*.json` are rejected, so trace data cannot be
silently skipped. Every node has `id`, `kind`, `title`, `status` and `source`.
`source` is a provenance string; it may be empty except for external ADRs. Designs also declare
`level` (`L3` or `L4`); tests declare `test_kind` (`acceptance`, `system`,
`integration`, `unit`). The test classification is separate from node `kind`.
The optional `example: true` marks temporary examples; none remain after #3. Every edge has `from`,
`to` and `kind`.

| Edge kind | From | To |
|---|---|---|
| `decomposes_into` | `REQ` | `SYS` |
| `realised_by` | `SYS` | `DES` |
| `refines` | `DES` | `DES` |
| `verified_by` | `REQ`, `US`, `SYS`, `DES` | `TEST` |
| `delivered_by` | Any node | Issue reference, `owner/repo#number` |
| `mitigated_by` | `RISK` | `DES`, `TEST` |
| `justifies` | `adr`, `D` | `DES` |
| `story_of` | `US` | `REQ` |
| `measures` | `OUT` | `REQ` |

Nodes progress through `proposed` → `planned` → `in-progress` → `done`.
A node at `planned` or later must have a `delivered_by` edge. `--strict` requires
that edge for all nodes; CI runs `--strict` since [#6](https://github.com/nerdmachines/scitadel-hub/issues/6)
(amendment below). Issue targets are external references, not nodes.

**Amendment (#3): downward decomposition is staged by status.** The V lands top-down,
one level per PR: L1 ([#3](https://github.com/nerdmachines/scitadel-hub/issues/3)),
then L2 ([#4](https://github.com/nerdmachines/scitadel-hub/issues/4)), then L3 and L4
([#5](https://github.com/nerdmachines/scitadel-hub/issues/5)). An always-required
`REQ --decomposes_into--> SYS` or `SYS --realised_by--> DES` edge would leave the
graph red until the level below exists, so the plan could never be green level by
level. The two downward edges therefore follow the same rule as `delivered_by`: they
are required when the node's status is past `proposed`, and always under `--strict`.
`verified_by` (every `REQ`, `SYS` and, since [#78](https://github.com/nerdmachines/scitadel-hub/issues/78), every `DES`) and `mitigated_by` (every `RISK`) stay required at
every status, so each level ships with its own acceptance or system `TEST` stubs.
Issue [#6](https://github.com/nerdmachines/scitadel-hub/issues/6) switches CI to
`--strict`, so the milestone cannot close with an undecomposed requirement.

**Amendment (#6): CI is strict, delivery means implementation, and an index is generated.**
- **Strict in CI.** The workflow runs `tools/trace-check docs --strict`, so every node needs
  `delivered_by` at every status, and every requirement and system node its downward edge.
- **What delivers a node.** A `delivered_by` edge names the issue whose work makes the node true,
  in the repository where that work lands, not the issue that wrote the node down. A design or its
  integration test is delivered by an implementation issue; hub-side work is filed in this repository,
  because issues cannot move across owners (vig-os/scitadel#313). An ADR node is delivered by the issue
  or pull request that decides it. The M0 documentation issues deliver only the principles, risks, open
  questions and decisions they record.
- **Status stays `proposed`.** The schema defines no trigger for `planned` beyond the delivery edge,
  which `--strict` now requires at every status, and XADR-SCITADEL-008 and this ADR are still
  proposed. A node moves to `planned` when the record that justifies it is accepted and its delivering
  issue is scheduled; that transition is a later, explicit change.
- **Issues index.** `tools/issues-index docs` writes [docs/issues-index.md](../issues-index.md) from
  the graph: every node by level with its delivering issues, their repositories and the node status.
  Issues in private repositories appear in code style. `--strict` requires that file to match the graph,
  and the gate checks it whenever it exists. Node titles are plain text: the schema rejects a Markdown
  link in a title, which would resolve against the wrong directory once rendered there.

**Amendment (#78, 2026-11-19): every design node is verified.** The epic pairs each V level
with a verification level: an L3 `DES` is verified by an integration `TEST`, an L4 `DES` by a
unit `TEST`. The gate had required `verified_by` only on `REQ` and `SYS`, so a `DES` could lose
its last `TEST` edge and still pass `--strict` (found by the M0 milestone review). A `DES` now
requires at least one `verified_by` edge to a `TEST` at every status and in `--strict` alike,
the same as `REQ` and `SYS`; a seeded fixture (`unverified-des`) proves the failure. The schema
records a `test_kind`, but the kind-to-level rule is **not** enforced yet: 7 of the 8 L4 designs
(DES-017, DES-019, DES-020, DES-021, DES-022, DES-058, DES-059) are verified only by integration
tests. Enforcing it needs a decision on those tests, not a relabel; it stays open until that is made.

The executable `tools/trace-check <docs-root>` uses Python 3.11 or later and only
the standard library. It validates the schema's supported keywords, ID formats,
unique IDs, edge endpoints and allowed kinds, local ADR files/status, external
ADR source format, and references to IDs in all Markdown under the docs root.
Markdown scanning recognizes only `PRIN`, `D`, `REQ`, `US`, `OUT`, `SYS`, `DES`,
`RISK`, `TEST`, `S`, `C`, `ADR` and `XADR` numeric identifiers. Unrelated names
such as UTF-8 and SHA-256 are ignored.
The graph must contain at least one `REQ` node; an empty graph fails explicitly.
It also rejects a requirement, system or design node without verification, a risk without
mitigation, and missing delivery edges at the applicable statuses. A requirement
without a system node, or a system node without a design, is rejected once its
status is past `proposed`, and always under `--strict`. Each violation is one stderr line, with a
nonzero exit code. Coverage on stdout counts nodes, nodes with verification and
nodes with delivery per level; it describes graph links, not executed tests.

Seeded fixtures prove each failure mode. CI runs the unit tests and gate on PRs
into `dev` and pushes to `dev`, and checks Markdown links with a pinned action.
The temporary example nodes of the initial graph were replaced by the L0 and L1
content of [#3](https://github.com/nerdmachines/scitadel-hub/issues/3); this ADR is a real node.

## Rationale

A fixed vocabulary keeps levels aligned before content grows. Graph-shaped JSON
can later be imported into cx-graph without scraping prose. Seeded failures prove
that missing work cannot pass vacuously. A standard-library gate runs without a
package installation or language build.

## Alternatives

| Option | Reason not chosen |
|---|---|
| Trace links only in Markdown | No single machine-checkable graph or completeness gate |
| Introduce cx runtime now | Adds infrastructure before the initial plan exists |
| Require delivery for all proposed nodes immediately | Conflicts with the staged issue-backfill slice |
| Always require `decomposes_into` and `realised_by` | The V lands one level per PR, so the level above could never be green until the level below exists |
| Drop the downward edges from the gate | Lets a requirement stay undecomposed unnoticed; the status rule and `--strict` keep the check |

## Consequences

Authors must update graph rows and links alongside documentation. IDs are owned
here and must not be invented in downstream slices. Schema shape and graph rules
are checked together; the bounded Python validator must be extended and tested
if new JSON Schema keywords are introduced. Unsupported keywords, malformed
keyword shapes, incomplete `if`/`then` pairs and recursive references produce
clean schema diagnostics before graph evaluation. The subset supports schema
objects, scalar enums/constants and acyclic references to local definitions.
The gate checks trace completeness; verification execution and the richer content arrive in later slices.

## Sources

- [Issue #2 and architect's ADR-node decision](https://github.com/nerdmachines/scitadel-hub/issues/2)
- [M0 epic and level table](https://github.com/nerdmachines/scitadel-hub/issues/1)
- [kit ADR 0008](https://github.com/nerdmachines/kit/blob/docs/initial-architecture/docs/decisions/0008-traceability-and-parity-are-cx-graph-gates.md)
- [kit ADR 0002 (format reference)](https://github.com/nerdmachines/kit/blob/docs/initial-architecture/docs/decisions/0002-kit-repo-and-cx-boundary.md)
