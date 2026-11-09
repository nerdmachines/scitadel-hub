"""Seeded fixtures exercise the public executable and exact diagnostic lines."""
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
GATE = Path(os.environ.get('TRACE_CHECK_GATE', ROOT / 'tools/trace-check'))
FIXTURES = Path(__file__).parent / 'fixtures'

FAILURES = {
    'empty-graph': 'traceability: graph must contain at least one REQ node',
    'no-req': 'traceability: graph must contain at least one REQ node',
    'invalid-edge-target-kind': 'invalid edge kinds: ADR-0001 --justifies--> REQ-001',
    'invalid-justifies-source': 'invalid edge kinds: PRIN-001 --justifies--> DES-001',
    'fenced-adr-status': 'ADR-0001: ADR Status must match node status proposed',
    'nested-json': 'traceability/nested: unexpected entry (subdirectories are not supported)',
    'unexpected-file': 'traceability/nodes.yml: unexpected file (only README.md, schema.json and *.json are allowed)',
    'duplicate-across-files': 'duplicate ID: PRIN-001',
    'wrong-container': 'traceability/nodes.json.nodes: expected array',
    'unknown-field': 'traceability/nodes.json.nodes[0]: unknown field unexpected',
    'invalid-external-id': "traceability/nodes.json.nodes[7].id: invalid format 'XADR-kit-008'",
    'unknown-id': "traceability/nodes.json.nodes[8].id: invalid format 'BOGUS-001'",
    'duplicate-id': 'duplicate ID: PRIN-001',
    'dangling-target': 'dangling edge: DES-001 --refines--> DES-999 (unknown target)',
    'dangling-source': 'dangling edge: DES-999 --refines--> DES-001 (unknown source)',
    'unverified-req': 'REQ-001: missing verified_by',
    'unverified-sys': 'SYS-001: missing verified_by',
    'undelivered-planned': 'PRIN-001: missing delivered_by',
    'undelivered-in-progress': 'PRIN-001: missing delivered_by',
    'undelivered-done': 'PRIN-001: missing delivered_by',
    'unmitigated-risk': 'RISK-001: missing mitigated_by',
    'undefined-markdown': 'README.md:1: undefined markdown ID REQ-999',
    'missing-local-adr': 'ADR-0001: expected one local ADR file, found 0',
    'adr-status-mismatch': 'ADR-0001: ADR Status must match node status proposed',
    'external-adr-without-source': 'traceability/nodes.json.nodes[7]: missing source',
    'external-adr-bad-url': "traceability/nodes.json.nodes[7].source: invalid format 'not-a-url'",
    'invalid-edge-kinds': 'invalid edge kinds: PRIN-001 --realised_by--> DES-001',
    'invalid-issue': 'PRIN-001: delivered_by target must be owner/repo#number: https://github.com/owner/repo/issues/1',
    'unknown-edge-kind': "traceability/edges.json.edges[7].kind: invalid value 'invented'",
    'missing-field': 'traceability/nodes.json.nodes[0]: missing title',
    'invalid-status': "traceability/nodes.json.nodes[0].status: invalid value 'accepted'",
    'wrong-node-kind': "traceability/nodes.json.nodes[0].kind: expected 'PRIN'",
    'missing-test-kind': 'traceability/nodes.json.nodes[4]: missing test_kind',
    'missing-design-level': 'traceability/nodes.json.nodes[3]: missing level',
    'malformed-json': 'traceability/nodes.json: invalid JSON: Expecting property name enclosed in double quotes: line 2 column 1 (char 2)',
}

# Downward decomposition edges are required once a node is past `proposed`, and
# always under --strict. Each fixture has delivery edges, so the single expected
# violation is the missing decomposition edge itself.
STAGED = {
    'req-proposed-undecomposed': ('REQ-001: missing decomposes_into', False),
    'req-planned-undecomposed': ('REQ-001: missing decomposes_into', True),
    'sys-proposed-unrealised': ('SYS-001: missing realised_by', False),
    'sys-planned-unrealised': ('SYS-001: missing realised_by', True),
}


class TraceCheckTests(unittest.TestCase):
    def run_gate(self, fixture, *flags):
        return subprocess.run([str(GATE), str(FIXTURES / fixture), *flags],
                              text=True, capture_output=True, check=False)

    def test_clean(self):
        result = self.run_gate('clean')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout.splitlines(), [
            'coverage L0: nodes=1 verified_by=0 delivered_by=0',
            'coverage L1: nodes=1 verified_by=1 delivered_by=0',
            'coverage L2: nodes=1 verified_by=1 delivered_by=0',
            'coverage L3: nodes=3 verified_by=1 delivered_by=0',
            'coverage L4: nodes=0 verified_by=0 delivered_by=0',
            'coverage risks: nodes=1 verified_by=0 delivered_by=0',
            'coverage tests: nodes=1 verified_by=0 delivered_by=0',
        ])

    def test_strict_rejects_proposed_without_delivery(self):
        result = self.run_gate('clean', '--strict')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(set(result.stderr.splitlines()), {
            f'{ident}: missing delivered_by' for ident in
            ('PRIN-001', 'REQ-001', 'SYS-001', 'DES-001', 'TEST-001',
             'ADR-0001', 'RISK-001', 'XADR-KIT-008')})

    def test_downward_edges_are_staged_by_status(self):
        for fixture, (violation, fails_normally) in STAGED.items():
            with self.subTest(fixture=fixture, strict=False):
                result = self.run_gate(fixture)
                self.assertEqual(result.returncode, int(fails_normally), result.stderr)
                self.assertEqual(result.stderr.splitlines(), [violation] if fails_normally else [])
            with self.subTest(fixture=fixture, strict=True):
                result = self.run_gate(fixture, '--strict')
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr.splitlines(), [violation])

    def test_delivered_nodes_pass_normal_and_strict(self):
        for flags in ((), ('--strict',)):
            with self.subTest(flags=flags):
                result = self.run_gate('delivered', *flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, '')

    def test_all_prefixes_and_edge_kinds(self):
        result = self.run_gate('all-edge-kinds', '--strict')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')

    def test_markdown_encoding_names(self):
        result = self.run_gate('markdown-encoding-names')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        undefined = self.run_gate('undefined-markdown')
        self.assertEqual(undefined.returncode, 1)
        self.assertEqual(undefined.stderr.splitlines(),
                         ['README.md:1: undefined markdown ID REQ-999'])

    def test_missing_root(self):
        result = self.run_gate('does-not-exist')
        self.assertEqual(result.returncode, 1)
        self.assertIn('docs root is not a directory', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_schema_uses_only_supported_keywords(self):
        # Prevent schema changes from silently bypassing the stdlib validator.
        schema = json.loads((ROOT / 'docs/traceability/schema.json').read_text())
        supported = {'$schema', '$defs', '$ref', 'title', 'description', 'type',
                     'properties', 'additionalProperties', 'required', 'items',
                     'oneOf', 'allOf', 'if', 'then', 'enum', 'const', 'pattern', 'minLength'}
        def visit(value):
            self.assertLessEqual(value.keys(), supported)
            for key, item in value.items():
                if key in ('$defs', 'properties'):
                    for child in item.values():
                        visit(child)
                elif key in ('oneOf', 'allOf'):
                    for child in item:
                        visit(child)
                elif key in ('if', 'then', 'items'):
                    visit(item)
        visit(schema)
        validate = runpy.run_path(str(GATE))['validate']
        # Unsupported or partial shapes must be diagnostics, never a traceback
        # or an ignored constraint. The current schema still has to validate.
        malformed = [
            ({'if': {}}, 'schema: if requires then'),
            ({'$defs': {'loop': {'$ref': '#/$defs/loop'}}},
             'schema.$defs.loop.$ref: recursive schema references are not supported'),
            ({'then': {}}, 'schema: then requires if'),
            ({'else': {}}, 'schema: unsupported keyword else'),
            ({'type': 'number'}, 'schema.type: unsupported type'),
            ({'properties': []}, 'schema.properties: expected an object'),
            ({'oneOf': []}, 'schema.oneOf: expected a nonempty array'),
            ({'items': True}, 'schema.items: expected a schema object'),
            ({'pattern': '['}, 'schema.pattern: invalid regular expression'),
            ({'$ref': '#/$defs/missing'}, 'schema.$ref: unresolved local definition'),
            ({'required': 'id'}, 'schema.required: expected an array of unique strings'),
            ({'additionalProperties': {}}, 'schema.additionalProperties: expected a boolean'),
        ]
        for broken, diagnostic in malformed:
            with self.subTest(schema=broken):
                self.assertEqual(list(validate({}, broken, broken, 'input')),
                                 [diagnostic])

    def test_partial_schema_is_a_clean_gate_error(self):
        gate = runpy.run_path(str(GATE))
        schema_path = Path(__file__).parent / 'schema-fixtures/partial-if.json'
        with patch.dict(gate['check'].__globals__, {'SCHEMA': schema_path}):
            errors, summary = gate['check'](FIXTURES / 'clean')
        self.assertEqual(errors, ['schema: if requires then'])
        self.assertEqual(summary, [])

    def test_workflow_pins_releases_and_bounds_jobs(self):
        workflow = (ROOT / '.github/workflows/trace.yml').read_text()
        uses = re.findall(r'^\s+- uses: (.+)$', workflow, re.MULTILINE)
        self.assertTrue(uses)
        for action in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r'^[^@ ]+@[0-9a-f]{40} # v[0-9]+\.[0-9]+\.[0-9]+$')
        jobs = re.findall(r'^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:|\Z)',
                          workflow.split('jobs:\n', 1)[1], re.MULTILINE | re.DOTALL)
        self.assertTrue(jobs)
        for name, body in jobs:
            with self.subTest(job=name):
                self.assertRegex(body, r'(?m)^    timeout-minutes: [1-9][0-9]*$')

    def test_every_fixture_is_exercised(self):
        self.assertEqual({p.name for p in FIXTURES.iterdir() if p.is_dir()},
                         set(FAILURES) | set(STAGED) | {'clean', 'delivered', 'all-edge-kinds', 'markdown-encoding-names'})


def failure_test(fixture, expected):
    def test(self):
        result = self.run_gate(fixture)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(expected, result.stderr.splitlines())
        self.assertNotIn('Traceback', result.stderr)
    return test


for name, diagnostic in FAILURES.items():
    setattr(TraceCheckTests, 'test_fixture_' + name.replace('-', '_'), failure_test(name, diagnostic))


if __name__ == '__main__':
    unittest.main()
