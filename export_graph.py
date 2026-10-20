#!/usr/bin/env python3
"""Export the operational WauTrace network without changing IDs or metadata.

Usage: python export_graph.py [package_dir] [--input network.json] [--output dir]
Defaults resolve relative to this script, not the caller's current directory.
Uses only the Python standard library. These are complete data exports; the
18-edge publication figure is produced separately by build_publication_graph.py.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
GRAPHML_NS = 'http://graphml.graphdrawing.org/xmlns'
EXPORT_FILES = ('full_graph.json', 'full_graph_edges.csv', 'full_graph.graphml', 'full_graph.dot')


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_network(network):
    """Check export preconditions without asserting source or chatbot accuracy."""
    nodes, edges = network.get('nodes'), network.get('edges')
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError('Operational nodes and edges must be lists.')
    ids = [node['id'] for node in nodes]
    edge_ids = [edge['edge_id'] for edge in edges]
    if len(ids) != len(set(ids)) or len(edge_ids) != len(set(edge_ids)):
        raise ValueError('Operational node and edge IDs must be unique.')
    if any(not isinstance(value, str) or not value for value in ids + edge_ids):
        raise ValueError('Operational IDs must be nonempty strings.')
    for edge in edges:
        if edge.get('subject') not in ids or edge.get('object') not in ids:
            raise ValueError(f"{edge['edge_id']}: endpoint missing from operational nodes.")
        if edge.get('polarity') not in ('positive', 'negative'):
            raise ValueError(f"{edge['edge_id']}: invalid polarity.")
        for field in ('relation', 'status', 'record_id', 'scope', 'intent'):
            if not isinstance(edge.get(field), str) or not edge[field]:
                raise ValueError(f"{edge['edge_id']}: nonempty {field} required.")
    # Reject NaN/Infinity rather than exporting non-standard JSON.
    json_text(network)


def make_payload(network, source_path):
    validate_network(network)
    endpoints = {edge[key] for edge in network['edges'] for key in ('subject', 'object')}
    counts = {'nodes': len(network['nodes']), 'assertion_endpoint_nodes': len(endpoints),
              'isolated_nodes': len(network['nodes']) - len(endpoints), 'edges': len(network['edges']),
              'edge_status_counts': dict(Counter(edge['status'] for edge in network['edges']))}
    return {
        'metadata': {
            'source_file': Path(source_path).name,
            'source_sha256': sha256_file(source_path),
            'knowledge_sha256': network.get('provenance', {}).get('knowledge_sha256'),
            'counts': counts,
            'scope': 'All operational nodes and assertion edges, including isolated candidates.',
            'identity_policy': 'Operational node IDs and E### edge IDs are preserved verbatim.',
            'metadata_policy': 'All node, edge and network fields are retained without a whitelist.',
            'not_a_bot_evaluation': True,
            'author_edge_review': {
                'approved': sum(edge.get('author_decision') == 'approved' for edge in network['edges']),
                'pending': sum(edge.get('author_decision') != 'approved' for edge in network['edges'])},
            'study_ready': False,
            'network_metadata': copy.deepcopy({key: value for key, value in network.items() if key not in ('nodes', 'edges')}),
        },
        'nodes': copy.deepcopy(network['nodes']),
        'edges': copy.deepcopy(network['edges']),
    }


def fields_for(items, preferred=()):
    keys = {key for item in items for key in item}
    return [key for key in preferred if key in keys] + sorted(keys.difference(preferred))


def export_csv(path, edges):
    fields = fields_for(edges, ('edge_id', 'record_id', 'subject', 'relation', 'object', 'object_type',
                                'object_value', 'polarity', 'status', 'scope', 'intent'))
    with Path(path).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields + ['edge_json'])
        writer.writeheader()
        for edge in edges:
            row = {key: value if isinstance(value, str) else json_text(value) for key, value in edge.items()}
            row['edge_json'] = json_text(edge)
            writer.writerow(row)


def export_graphml(path, payload):
    ET.register_namespace('', GRAPHML_NS)
    root = ET.Element(f'{{{GRAPHML_NS}}}graphml')
    fields = {'node': fields_for(payload['nodes']), 'edge': fields_for(payload['edges'])}
    keys = {}
    def declare(target, field, index):
        key = f'{target}_{index}'
        ET.SubElement(root, 'key', {'id': key, 'for': target, 'attr.name': field, 'attr.type': 'string'})
        keys[target, field] = key
    declare('graph', 'metadata_json', 0)
    for target, target_fields in fields.items():
        for index, field in enumerate(target_fields):
            declare(target, field, index)
        declare(target, target + '_json', len(target_fields))
    graph = ET.SubElement(root, 'graph', {'id': 'WauTrace', 'edgedefault': 'directed'})
    ET.SubElement(graph, 'data', {'key': keys['graph', 'metadata_json']}).text = json_text(payload['metadata'])
    for node in payload['nodes']:
        element = ET.SubElement(graph, 'node', {'id': node['id']})
        for field, value in node.items():
            ET.SubElement(element, 'data', {'key': keys['node', field]}).text = value if isinstance(value, str) else json_text(value)
        ET.SubElement(element, 'data', {'key': keys['node', 'node_json']}).text = json_text(node)
    for edge in payload['edges']:
        element = ET.SubElement(graph, 'edge', {'id': edge['edge_id'], 'source': edge['subject'], 'target': edge['object']})
        for field, value in edge.items():
            ET.SubElement(element, 'data', {'key': keys['edge', field]}).text = value if isinstance(value, str) else json_text(value)
        ET.SubElement(element, 'data', {'key': keys['edge', 'edge_json']}).text = json_text(edge)
    ET.indent(root, space='  ')
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def display_relation(edge):
    text = edge['relation'].replace('_', ' ')
    if edge['polarity'] == 'negative' and not re.match(r'^(not|lacks|does not)\b', text, re.I):
        text = 'NOT ' + text
    return text


def dot_text(payload):
    # JSON string quoting is compatible with DOT double-quoted strings; backslashes,
    # embedded quotes, newlines and non-ASCII cultural terms remain recoverable.
    q = lambda value: json.dumps(str(value), ensure_ascii=False)
    lines = ['digraph WauTrace {',
             'graph [rankdir=LR, bgcolor="white", metadata_json=' + q(json_text(payload['metadata'])) + '];',
             'node [shape=box, style=rounded, color=black, fontname="DejaVu Sans"];',
             'edge [color=black, fontcolor=black, fontname="DejaVu Sans"];']
    for node in payload['nodes']:
        lines.append(f"{q(node['id'])} [label={q(node.get('label', node['id']))}, node_json={q(json_text(node))}];")
    for edge in payload['edges']:
        style = 'dashed' if edge['status'] == 'source_variance' else 'solid'
        lines.append(f"{q(edge['subject'])} -> {q(edge['object'])} [id={q(edge['edge_id'])}, label={q(display_relation(edge))}, style={q(style)}, edge_json={q(json_text(edge))}];")
    return '\n'.join(lines + ['}']) + '\n'


def export_network(source_path, output_dir):
    source_path, output_dir = Path(source_path), Path(output_dir)
    network = json.loads(source_path.read_text(encoding='utf-8'))
    payload = make_payload(network, source_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / 'full_graph.json', payload)
    export_csv(output_dir / 'full_graph_edges.csv', payload['edges'])
    export_graphml(output_dir / 'full_graph.graphml', payload)
    (output_dir / 'full_graph.dot').write_text(dot_text(payload), encoding='utf-8')
    manifest = {'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'metadata': payload['metadata'],
                'files': {name: {'sha256': sha256_file(output_dir / name)} for name in EXPORT_FILES},
                'csv_encoding': 'UTF-8 with BOM; nested values are JSON; edge_json is the lossless row payload.',
                'graphml_encoding': 'String attributes; nested values are JSON; node_json and edge_json preserve exact types and field presence.',
                'dot_encoding': 'Quoted UTF-8 strings; node_json and edge_json preserve full records.',
                'publication_figure': 'Separate selected 18-edge drawing; not overwritten by this exporter.'}
    write_json(output_dir / 'export_manifest.json', manifest)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', nargs='?', type=Path, default=BASE)
    parser.add_argument('--input', type=Path, help='Operational network JSON; defaults to package/WauTrace_Network_Template.json')
    parser.add_argument('--output', type=Path, help='Export directory; defaults to package/graphs')
    args = parser.parse_args()
    source = args.input or args.package / 'WauTrace_Network_Template.json'
    output = args.output or args.package / 'graphs'
    payload = export_network(source, output)
    print(json.dumps({'exported': True, **payload['metadata']['counts'], 'output': str(output.resolve())}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
