"""Seeded fixtures exercise the public executable and exact diagnostic lines."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / 'tools/trace-check'
FIXTURES = Path(__file__).parent / 'fixtures'

FAILURES = {
    'duplicate-across-files': 'duplicate ID: PRIN-001',
    'wrong-container': 'traceability/nodes.json.nodes: expected array',
    'unknown-field': 'traceability/nodes.json.nodes[0]: unknown field unexpected',
    'invalid-external-id': "traceability/nodes.json.nodes[7].id: invalid format 'XADR-kit-008'",
    'unknown-id': "traceability/nodes.json.nodes[8].id: invalid format 'BOGUS-001'",
    'duplicate-id': 'duplicate ID: PRIN-001',
    'dangling-target': 'dangling edge: DES-001 --refines--> DES-999 (unknown target)',
    'dangling-source': 'dangling edge: DES-999 --refines--> DES-001 (unknown source)',
    'orphan-req': 'REQ-001: missing decomposes_into',
    'unverified-req': 'REQ-001: missing verified_by',
    'unverified-sys': 'SYS-001: missing verified_by',
    'unrealised-sys': 'SYS-001: missing realised_by',
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

    def test_every_fixture_is_exercised(self):
        self.assertEqual({p.name for p in FIXTURES.iterdir() if p.is_dir()},
                         set(FAILURES) | {'clean', 'delivered', 'all-edge-kinds'})


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
