# Traceability

[ADR-0001](../decisions/0001-v-model-and-traceability.md) defines levels, identifiers
and edge kinds; [schema.json](schema.json) defines the JSON shape.

The graph needs at least one `REQ`. Keep this directory flat: only `README.md`,
`schema.json` and `*.json` are allowed; subdirectories and other files fail.

1. Add a node to [nodes.json](nodes.json) with a unique ID, `kind`, `title`,
   `status` and `source`. Use `proposed` initially. Designs need `level` (`L3` or
   `L4`); tests need `test_kind` (`acceptance`, `system`, `integration`, `unit`).
2. Add edges to [edges.json](edges.json) with `from`, `to` and `kind`.
   Each requirement needs `verified_by`; each system node needs `verified_by`; each
   risk needs `mitigated_by`. These are required at every status. The downward
   edges (`decomposes_into` for a requirement, `realised_by` for a system node) are
   required only once the node is past `proposed`, or always with `--strict`: the V
   lands one level per PR, so a level cannot name the level below before it exists.
3. Before `planned`, add `delivered_by` to an issue such as
   `nerdmachines/scitadel-hub#3`. It remains required at `in-progress` and `done`.
4. Run `python3 -m unittest discover -s tools/tests -v` and
   `tools/trace-check docs` from the repository root (Python 3.11+).
   `--strict` also requires delivery edges and the downward edges for proposed nodes
   (CI switches to it in [#6](https://github.com/nerdmachines/scitadel-hub/issues/6)).

Local ADR nodes resolve to one decision file with a matching `Status:` line;
external ADR nodes require a source URL. The gate checks IDs mentioned in Markdown
and prints coverage per level. `example: true` nodes are temporary examples to be
replaced by [#3](https://github.com/nerdmachines/scitadel-hub/issues/3).
