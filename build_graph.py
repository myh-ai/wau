#!/usr/bin/env python3
"""Validate and export the complete documentary graph without altering its data.

Run: python build_graph.py
This checks record structure and exact triple-to-edge correspondence. It does
not approve knowledge or measure chatbot performance. The separate
build_publication_graph.py creates the selected paper figure.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from export_graph import export_network, validate_network

BASE = Path(__file__).resolve().parent
STATUS_ENUM = ("supported", "explicit_negative", "discrepancy", "unverified")


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(data):
    """Structural/source-link checks; not independent fact verification."""
    errors = []
    checks = []
    records = data.get('records', [])
    sources = data.get('sources', {})
    seen = set()
    required = ('record_id', 'record_group', 'topic_en', 'claim_en',
                'status', 'triples', 'evidence', 'limits_en', 'review')
    snake = re.compile(r'^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$')
    forbidden = {'same_as', 'sameAs', 'equivalent_to', 'identical_to', 'disjoint_with', 'disjointWith'}
    for record in records:
        rid = record.get('record_id', '<missing>')
        missing = [k for k in required if k not in record]
        if missing:
            errors.append(f'{rid}: missing fields {missing}')
            continue
        if rid in seen:
            errors.append(f'{rid}: duplicate record ID')
        seen.add(rid)
        for key in ('record_id', 'record_group', 'topic_en', 'claim_en', 'limits_en'):
            if not nonempty(record.get(key)):
                errors.append(f'{rid}: empty {key}')
        if not isinstance(record.get('review'), dict) or not record.get('review'):
            errors.append(f'{rid}: review metadata missing')
        if record.get('status') not in STATUS_ENUM:
            errors.append(f'{rid}: unknown status')
        if not isinstance(record.get('triples'), list) or not isinstance(record.get('evidence'), list):
            errors.append(f'{rid}: triples/evidence must be lists')
            continue
        if record.get('status') == 'unverified':
            if record['triples'] or record['evidence']:
                errors.append(f'{rid}: unverified records must have no assertions or invented evidence')
        elif not record['evidence'] or not record['triples']:
            errors.append(f'{rid}: asserted record requires evidence and triples')
        for ev in record['evidence']:
            for key in ('language', 'quote', 'source_id', 'scan_path', 'verification'):
                if not nonempty(ev.get(key)):
                    errors.append(f'{rid}: missing evidence {key}')
            if not isinstance(ev.get('page'), int) or ev['page'] < 1:
                errors.append(f'{rid}: invalid evidence page')
            if ev.get('source_id') not in sources:
                errors.append(f'{rid}: unknown evidence source')
        for index, triple in enumerate(record['triples'], 1):
            prefix = f'{rid}/T{index:02d}'
            if any(key not in triple for key in ('subject', 'relation', 'object', 'object_type', 'polarity', 'scope')):
                errors.append(f'{prefix}: missing triple field')
                continue
            if not snake.fullmatch(str(triple['subject'])) or not nonempty(triple['relation']):
                errors.append(f'{prefix}: invalid subject or relation')
            if triple['relation'] in forbidden:
                errors.append(f'{prefix}: unconditional identity/disjointness forbidden by corpus contract')
            if not nonempty(triple['scope']):
                errors.append(f'{prefix}: source scope is required')
            factual_intents = {x['id'] for x in data.get('intent_taxonomy', {}).get('categories', []) if x.get('kind') == 'factual'}
            if triple.get('intent') not in factual_intents:
                errors.append(f'{prefix}: valid factual intent is required')
            if triple['relation'] == 'most_have' and (triple.get('quantifier') != 'most' or triple.get('inheritance') != 'context_only'):
                errors.append(f'{prefix}: majority context must preserve most and prohibit universal inheritance')
            kind, value = triple['object_type'], triple['object']
            if kind not in ('entity', 'literal', 'number', 'boolean'):
                errors.append(f'{prefix}: invalid object_type')
            elif kind == 'entity' and not snake.fullmatch(str(value)):
                errors.append(f'{prefix}: invalid entity object')
            elif kind == 'literal' and not nonempty(value):
                errors.append(f'{prefix}: empty literal')
            elif kind == 'number' and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                errors.append(f'{prefix}: invalid number')
            elif kind == 'boolean' and not isinstance(value, bool):
                errors.append(f'{prefix}: invalid boolean')
            if triple['polarity'] not in ('positive', 'negative'):
                errors.append(f'{prefix}: invalid polarity')
            if record['status'] == 'explicit_negative' and triple['polarity'] != 'negative':
                errors.append(f'{prefix}: negative record has non-negative triple')
            if record['status'] != 'explicit_negative' and triple['polarity'] == 'negative':
                errors.append(f'{prefix}: negative polarity outside explicit_negative record')
            if 'kemetek' in (str(triple['subject']) + ' ' + str(value)).lower():
                errors.append(f'{prefix}: unsupported Kemetek assertion')
        for parent in record.get('parent_record_ids', []):
            if parent not in {r.get('record_id') for r in records}:
                errors.append(f'{rid}: unknown parent record {parent}')
        if record['status'] == 'discrepancy':
            wording = [t for t in record['triples'] if t.get('relation') == 'has_source_shape_wording']
            if len(wording) < 2 or not any('Malay' in t['scope'] for t in wording) or not any('English' in t['scope'] for t in wording):
                errors.append(f'{rid}: discrepancy requires both language-scoped wordings')
    by_id = {r.get('record_id'): r for r in records}
    for rid, page in (('RQ1-N02', 73), ('RQ1-S01', 144)):
        if rid not in by_id or page not in [e.get('page') for e in by_id[rid].get('evidence', [])]:
            errors.append(f'{rid}: required separate source-scoped naming/classification record missing')
    kemetek = by_id.get('RQ1-N04', {})
    if kemetek.get('status') != 'unverified' or kemetek.get('triples') or kemetek.get('evidence'):
        errors.append('RQ1-N04: Kemetek must remain unverified without assertion edges')
    counts = {'records': len(records), 'by_status': dict(Counter(r.get('status') for r in records)),
              'triples': sum(len(r.get('triples', [])) for r in records),
              'evidence_entries': sum(len(r.get('evidence', [])) for r in records),
              'core_records': sum(r.get('record_group') in ('core', 'original_24') for r in records),
              'supplemental_records': sum(r.get('record_group') == 'supplemental_atomic' for r in records)}
    for key in ('by_status', 'triples', 'evidence_entries', 'core_records', 'supplemental_records'):
        if data.get('counts', {}).get(key) != counts[key]:
            errors.append(f'declared count differs from computed count: {key}')
    checks.extend(['Required bilingual record fields and four-state enum', 'Unique record IDs and valid parent references',
                   'Nonempty evidence page/quote and known source IDs for asserted records',
                   'Typed triples, explicit polarity, nonempty documentary scope',
                   'Kemetek retained unverified without assertion edges',
                   'No unconditional identity or disjointness relations',
                   'Separate p.73 heading and p.144 classification retained',
                   'Both language-specific discrepancy wordings retained', 'Declared counts match computed counts'])
    return errors, counts, checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=BASE / 'knowledge.json')
    parser.add_argument('--network', type=Path)
    parser.add_argument('--output', type=Path, default=BASE / 'graphs')
    parser.add_argument('--report', type=Path, default=BASE / 'validation_report.json')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    errors, counts, checks = validate(data)
    network_path = args.network or args.input.parent / 'WauTrace_Network_Template.json'
    network = json.loads(network_path.read_text(encoding='utf-8'))
    if network.get('provenance', {}).get('knowledge_sha256') != sha256_file(args.input):
        errors.append('Network knowledge hash differs from the knowledge input.')
    try:
        validate_network(network)
    except (ValueError, KeyError) as exc:
        errors.append(str(exc))
    records = {record['record_id']: record for record in data['records']}
    expected = {(record['record_id'], index): triple
                for record in data['records']
                for index, triple in enumerate(record['triples'], 1)}
    actual = {}
    for edge in network.get('edges', []):
        origin = edge.get('origin', {})
        key = (origin.get('record_id'), origin.get('triple_index'))
        if key in actual:
            errors.append(f"{edge.get('edge_id')}: duplicate canonical origin.")
        actual[key] = edge.get('kb_triple')
        if edge.get('record_id') != key[0] or expected.get(key) != edge.get('kb_triple'):
            errors.append(f"{edge.get('edge_id')}: triple differs from its knowledge origin.")
    if actual != expected:
        errors.append('Operational edge origins do not match the complete canonical triple set.')
    counts.update({'graph_nodes': len(network['nodes']), 'graph_edges': len(network['edges']),
                   'assertion_endpoint_nodes': len({edge[key] for edge in network['edges'] for key in ('subject', 'object')}),
                   'edge_status_counts': dict(Counter(edge['status'] for edge in network['edges']))})
    checks += ['Unique operational IDs and resolving endpoints',
               'Exact bijection between knowledge triples and network assertion edges',
               'Exact knowledge-file hash in network provenance']
    pending = [edge['edge_id'] for edge in network['edges'] if edge.get('author_decision') != 'approved']
    report = {'artifact': 'Documentary knowledge structure and export checks',
              'not_a_bot_evaluation': True, 'source_file': args.input.name,
              'source_sha256': sha256_file(args.input), 'network_sha256': sha256_file(network_path),
              'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'passed': not errors, 'errors': errors, 'checks': checks, 'computed_counts': counts,
              'author_edge_review': {'approved': len(network['edges'])-len(pending), 'pending': len(pending)},
              'study_ready': False,
              'limits': ['Structural consistency does not establish factual correctness, cultural completeness or chatbot accuracy.',
                         'Source checking and author approval of the operational representation are separate activities.',
                         'This export does not certify participant-study readiness or institutional approval.']}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if not errors and not args.validate_only:
        export_network(network_path, args.output)
    write_json(args.report, report)
    print(json.dumps({'passed': not errors, 'counts': counts, 'author_edge_review': report['author_edge_review'], 'errors': errors}, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
