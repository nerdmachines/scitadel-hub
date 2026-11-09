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
| Cross-level | Risks | `RISK` | Mitigations in designs or tests |
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
`Status: <status>` line must equal the node's status. External ADRs require an
HTTP(S) `source` URL; the gate validates its format without fetching it.
Owner decision nodes (`D`) can point to an ADR or issue in `source`.

[Traceability JSON](../traceability/README.md) consists of `nodes.json` and
`edges.json`; additional `*.json` files in that directory may contain either
`{"nodes": [...]}` or `{"edges": [...]}`. `schema.json` is excluded from graph
input. Every node has `id`, `kind`, `title`, `status` and `source`. `source` is a
provenance string; it may be empty except for external ADRs. Designs also declare
`level` (`L3` or `L4`); tests declare `test_kind` (`acceptance`, `system`,
`integration`, `unit`). The test classification is separate from node `kind`.
The optional `example: true` marks temporary examples. Every edge has `from`,
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
that edge for all nodes; [#6](https://github.com/nerdmachines/scitadel-hub/issues/6)
will enable strict mode later. Issue targets are external references, not nodes.

The executable `tools/trace-check <docs-root>` uses Python 3.11 or later and only
the standard library. It validates the schema's supported keywords, ID formats,
unique IDs, edge endpoints and allowed kinds, local ADR files/status, external
ADR source format, and references to IDs in all Markdown under the docs root.
It rejects an orphan requirement, a requirement or system node without verification,
a system node without design, a risk without mitigation, and missing delivery
edges at the applicable statuses. Each violation is one stderr line, with a
nonzero exit code. Coverage on stdout counts nodes, nodes with verification and
nodes with delivery per level; it describes graph links, not executed tests.

Seeded fixtures prove each failure mode. CI runs the unit tests and gate on PRs
into `dev` and pushes to `dev`, and checks Markdown links with a pinned action.
The five content nodes in the initial graph are examples to be replaced by
[#3](https://github.com/nerdmachines/scitadel-hub/issues/3); this ADR is a real node.

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

## Consequences

Authors must update graph rows and links alongside documentation. IDs are owned
here and must not be invented in downstream slices. Schema shape and graph rules
are checked together; the bounded Python validator must be extended and tested
if new JSON Schema keywords are introduced. The gate checks trace completeness;
verification execution and the richer content arrive in later slices.

## Sources

- [Issue #2 and architect's ADR-node decision](https://github.com/nerdmachines/scitadel-hub/issues/2)
- [M0 epic and level table](https://github.com/nerdmachines/scitadel-hub/issues/1)
- [kit ADR 0008](https://github.com/nerdmachines/kit/blob/docs/initial-architecture/docs/decisions/0008-traceability-and-parity-are-cx-graph-gates.md)
- [kit ADR 0002 (format reference)](https://github.com/nerdmachines/kit/blob/docs/initial-architecture/docs/decisions/0002-kit-repo-and-cx-boundary.md)
