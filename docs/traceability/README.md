# Traceability

[ADR-0001](../decisions/0001-v-model-and-traceability.md) defines levels, identifiers
and edge kinds; [schema.json](schema.json) defines the JSON shape.

1. Add a node to [nodes.json](nodes.json) with a unique ID, `kind`, `title`,
   `status` and `source`. Use `proposed` initially. Designs need `level` (`L3` or
   `L4`); tests need `test_kind` (`acceptance`, `system`, `integration`, `unit`).
2. Add edges to [edges.json](edges.json) with `from`, `to` and `kind`.
   Each requirement needs `decomposes_into` and `verified_by`; each system node
   needs `realised_by` and `verified_by`; each risk needs `mitigated_by`.
3. Before `planned`, add `delivered_by` to an issue such as
   `nerdmachines/scitadel-hub#3`. It remains required at `in-progress` and `done`.
4. Run `python3 -m unittest discover -s tools/tests -v` and
   `tools/trace-check docs` from the repository root (Python 3.11+).
   `--strict` also requires delivery edges for proposed nodes.

Local ADR nodes resolve to one decision file with a matching `Status:` line;
external ADR nodes require a source URL. The gate checks IDs mentioned in Markdown
and prints coverage per level. `example: true` nodes are temporary examples to be
replaced by [#3](https://github.com/nerdmachines/scitadel-hub/issues/3).
