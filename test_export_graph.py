#!/usr/bin/env python3
"""Round-trip checks for operational graph exports, not chatbot evaluation."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from export_graph import BASE, GRAPHML_NS, export_network, validate_network


def quoted_attribute(text, attribute):
    pattern = re.compile(r'\b' + re.escape(attribute) + r'=("(?:\\.|[^"\\])*")')
    return [json.loads(json.loads(match.group(1))) for match in pattern.finditer(text)]


class ExportContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = json.loads((BASE / 'WauTrace_Network_Template.json').read_text(encoding='utf-8'))
        cls.temporary = tempfile.TemporaryDirectory(prefix='wautrace_export_test_')
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / 'network.json'
        cls.source.write_text(json.dumps(cls.network, ensure_ascii=False), encoding='utf-8')
        cls.output = cls.root / 'exports'
        cls.payload = export_network(cls.source, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def assert_edges_equal(self, actual):
        expected = self.network['edges']
        self.assertEqual({edge['edge_id'] for edge in expected}, {edge['edge_id'] for edge in actual})
        self.assertEqual(len(expected), len(actual))
        self.assertEqual({edge['edge_id']: edge for edge in expected}, {edge['edge_id']: edge for edge in actual})

    def test_json_preserves_nodes_edges_and_network_metadata(self):
        loaded = json.loads((self.output / 'full_graph.json').read_text(encoding='utf-8'))
        self.assertEqual(loaded['nodes'], self.network['nodes'])
        self.assert_edges_equal(loaded['edges'])
        self.assertEqual(loaded['metadata']['network_metadata'],
                         {key: value for key, value in self.network.items() if key not in ('nodes', 'edges')})
        endpoint_ids = {edge[key] for edge in loaded['edges'] for key in ('subject', 'object')}
        self.assertTrue(endpoint_ids.issubset({node['id'] for node in loaded['nodes']}))
        self.assertEqual(loaded['metadata']['counts']['isolated_nodes'], len(loaded['nodes']) - len(endpoint_ids))

    def test_csv_roundtrip_preserves_all_operational_fields(self):
        with (self.output / 'full_graph_edges.csv').open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assert_edges_equal([json.loads(row['edge_json']) for row in rows])
        for original, row in zip(self.network['edges'], rows):
            self.assertEqual(row['edge_id'], original['edge_id'])
            self.assertEqual(row['subject'], original['subject'])
            self.assertEqual(row['object'], original['object'])
            for field in ('intent', 'polarity', 'status', 'semantic_fact_id', 'canonical_answer_edge_id'):
                self.assertEqual(row[field], original[field])
            self.assertEqual(json.loads(row['evidence']), original['evidence'])
            self.assertEqual(json.loads(row['kb_triple']), original['kb_triple'])
            for field in ('quantifier', 'inheritance'):
                if field in original:
                    self.assertEqual(row[field], original[field])

    def test_graphml_roundtrip_preserves_endpoints_and_metadata(self):
        ns = {'g': GRAPHML_NS}
        root = ET.parse(self.output / 'full_graph.graphml').getroot()
        keys = {element.get('id'): element.get('attr.name') for element in root.findall('g:key', ns)}
        nodes, edges = [], []
        for element in root.findall('.//g:node', ns):
            attrs = {keys[item.get('key')]: item.text for item in element.findall('g:data', ns)}
            node = json.loads(attrs['node_json'])
            self.assertEqual(element.get('id'), node['id'])
            nodes.append(node)
        for element in root.findall('.//g:edge', ns):
            attrs = {keys[item.get('key')]: item.text for item in element.findall('g:data', ns)}
            edge = json.loads(attrs['edge_json'])
            self.assertEqual((element.get('id'), element.get('source'), element.get('target')),
                             (edge['edge_id'], edge['subject'], edge['object']))
            for field in ('intent', 'polarity', 'status', 'semantic_fact_id', 'canonical_answer_edge_id'):
                self.assertEqual(attrs[field], edge[field])
            self.assertEqual(json.loads(attrs['evidence']), edge['evidence'])
            self.assertEqual(json.loads(attrs['kb_triple']), edge['kb_triple'])
            edges.append(edge)
        self.assertEqual(nodes, self.network['nodes'])
        self.assert_edges_equal(edges)

    def test_dot_roundtrip_preserves_records_and_negative_labels(self):
        text = (self.output / 'full_graph.dot').read_text(encoding='utf-8')
        self.assertEqual(quoted_attribute(text, 'node_json'), self.network['nodes'])
        self.assert_edges_equal(quoted_attribute(text, 'edge_json'))
        for edge in self.network['edges']:
            line = next(line for line in text.splitlines() if f'id="{edge["edge_id"]}"' in line)
            self.assertTrue(line.startswith(json.dumps(edge['subject'], ensure_ascii=False) + ' -> ' + json.dumps(edge['object'], ensure_ascii=False)))
            if edge['polarity'] == 'negative':
                self.assertRegex(line, r'label="(?:NOT |not |lacks |does not )')
        if shutil.which('dot'):
            parsed = subprocess.run(['dot', '-Tdot', str(self.output / 'full_graph.dot')], capture_output=True, timeout=30)
            self.assertEqual(parsed.returncode, 0, parsed.stderr.decode('utf-8', errors='replace'))

    def test_unicode_quotes_newlines_and_backslashes_roundtrip(self):
        network = copy.deepcopy(self.network)
        sample = 'Juru anjong — “Malay” / café "quoted" \\ path\nsecond line <tag> & value'
        network['nodes'][0]['label'] = sample
        network['edges'][0]['answer_en'] = sample
        network['edges'][0]['future_structured_metadata'] = {'text': sample, 'enabled': True, 'value': None}
        source = self.root / 'unicode.json'
        source.write_text(json.dumps(network, ensure_ascii=False), encoding='utf-8')
        output = self.root / 'unicode'
        export_network(source, output)
        dot = (output / 'full_graph.dot').read_text(encoding='utf-8')
        self.assertEqual(quoted_attribute(dot, 'node_json')[0]['label'], sample)
        self.assertEqual(quoted_attribute(dot, 'edge_json')[0], network['edges'][0])
        ns = {'g': GRAPHML_NS}
        root = ET.parse(output / 'full_graph.graphml').getroot()
        key = next(key.get('id') for key in root.findall('g:key', ns) if key.get('attr.name') == 'edge_json')
        first = root.find('.//g:edge', ns)
        value = next(item.text for item in first.findall('g:data', ns) if item.get('key') == key)
        self.assertEqual(json.loads(value), network['edges'][0])
        if shutil.which('dot'):
            parsed = subprocess.run(['dot', '-Tdot', str(output / 'full_graph.dot')], capture_output=True, timeout=30)
            self.assertEqual(parsed.returncode, 0, parsed.stderr.decode('utf-8', errors='replace'))

    def test_invalid_ids_and_endpoints_are_rejected(self):
        network = copy.deepcopy(self.network)
        network['edges'][0]['object'] = 'missing_endpoint'
        with self.assertRaisesRegex(ValueError, 'endpoint missing'):
            validate_network(network)
        network = copy.deepcopy(self.network)
        network['edges'].append(copy.deepcopy(network['edges'][0]))
        with self.assertRaisesRegex(ValueError, 'unique'):
            validate_network(network)

    def test_review_status_survives_export_without_approval(self):
        loaded = json.loads((self.output / 'full_graph.json').read_text(encoding='utf-8'))
        decisions = {edge['edge_id']: edge.get('author_decision') for edge in self.network['edges']}
        self.assertEqual(decisions, {edge['edge_id']: edge.get('author_decision') for edge in loaded['edges']})
        counts = loaded['metadata']['author_edge_review']
        self.assertEqual(counts['approved'], sum(value == 'approved' for value in decisions.values()))
        self.assertEqual(counts['pending'], sum(value != 'approved' for value in decisions.values()))
        self.assertFalse(loaded['metadata']['study_ready'])

    def test_cli_default_input_resolves_from_script_directory(self):
        result = subprocess.run([sys.executable, str(BASE / 'export_graph.py'),
                                 '--output', str(self.root / 'cli')], cwd=self.root,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads((self.root / 'cli' / 'full_graph.json').read_text(encoding='utf-8'))
        self.assertEqual(payload['nodes'], self.network['nodes'])
        self.assert_edges_equal(payload['edges'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='Optional JSON report path')
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExportContractTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if args.report:
        args.report.write_text(json.dumps({'suite': 'Operational export round-trip checks',
                                          'not_a_bot_evaluation': True, 'passed': result.wasSuccessful(),
                                          'tests_run': result.testsRun,
                                          'failures': [{'test': str(case), 'detail': detail} for case, detail in result.failures],
                                          'errors': [{'test': str(case), 'detail': detail} for case, detail in result.errors]}, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
