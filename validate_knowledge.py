#!/usr/bin/env python3
"""Check the source-linked knowledge and semantic-network contracts.

Run: python validate_knowledge.py
Optional image-integrity check:
    python validate_knowledge.py --source-root /path/to/sources

Structural success does not grant author approval, establish chatbot accuracy,
or authorize a participant study. Scenario validation is a separate activity.
Only Python's standard library is required.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from graph_inference import deduplicate_answers, resolve_feature

BASE = Path(__file__).resolve().parent
EXPECTED_RQ1 = 'What documented names, forms, characteristics, and cultural practices describe Wau Kikik in the project sources?'
EXPECTED_PAGES = {72, 73, 144, 146, 148}
EXPECTED_IDS = {f'RQ1-{prefix}{i:02d}' for prefix, total in [('N', 5), ('F', 4), ('C', 6), ('P', 9), ('S', 12)] for i in range(1, total + 1)}
STATUS_MAP = {'supported': 'supported', 'explicit_negative': 'explicit_negative',
              'unverified': 'not_documented', 'discrepancy': 'source_variance'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--knowledge', type=Path, default=BASE / 'knowledge.json')
    parser.add_argument('--network', type=Path, default=BASE / 'WauTrace_Network_Template.json')
    parser.add_argument('--review', type=Path, default=BASE / 'source_review.json')
    parser.add_argument('--report', type=Path, default=BASE / 'knowledge_validation_report.json')
    parser.add_argument('--source-root', type=Path)
    args = parser.parse_args()
    checks, errors, warnings = [], [], []

    def check(code, condition, detail):
        row = {'check': code, 'result': 'pass' if condition else 'fail', 'detail': detail}
        checks.append(row)
        if not condition:
            errors.append(row)

    try:
        kb, net, review = [json.loads(path.read_text(encoding='utf-8')) for path in (args.knowledge, args.network, args.review)]
    except (OSError, ValueError) as exc:
        args.report.write_text(json.dumps({'result': 'fail', 'input_error': str(exc)}, indent=2) + '\n', encoding='utf-8')
        print('FAIL: a required knowledge input could not be read.')
        return 1
    records = {record.get('record_id'): record for record in kb.get('records', [])}
    nodes = {node.get('id'): node for node in net.get('nodes', [])}
    edges = {edge.get('edge_id'): edge for edge in net.get('edges', [])}
    expected = {(rid, i): triple for rid, record in records.items() for i, triple in enumerate(record.get('triples', []), 1)}
    khash = digest(args.knowledge)
    check('canonical_rq1', kb.get('canonical_rq1') == net.get('canonical_rq1') == EXPECTED_RQ1, 'KB and network use the same RQ1 wording.')
    check('record_identity', len(records) == len(kb.get('records', [])) and set(records) == EXPECTED_IDS, 'All 36 source records have distinct, resolving IDs.')
    check('knowledge_hash', net.get('provenance', {}).get('knowledge_sha256') == khash == review.get('knowledge_sha256'), 'Network and source-review ledger reference the actual knowledge file.')
    check('node_identity', len(nodes) == len(net.get('nodes', [])), 'All operational node IDs are unique.')
    check('edge_identity', len(edges) == len(net.get('edges', [])) == len(expected), 'One distinct edge exists per typed knowledge triple.')
    check('source_registry', set(kb.get('sources', {})) == set(net.get('sources', {})), 'Source IDs are shared by the knowledge and network.')
    check('status_mapping', net.get('kb_status_mapping') == STATUS_MAP, 'Record statuses map explicitly to operational evidence states.')
    taxonomy = net.get('intent_taxonomy', {}).get('categories', [])
    factual = {row.get('id') for row in taxonomy if row.get('kind') == 'factual'}
    intents = {row.get('id') for row in taxonomy}
    check('intent_taxonomy', len(factual) == 12 and intents - factual == {'not_documented'} and net.get('intent_taxonomy') == kb.get('intent_taxonomy'), 'Twelve factual intents and one fallback share a consistent taxonomy.')
    supplemental = {item.get('supplemental_evidence_id'): item for item in review.get('supplemental_evidence', [])}
    origins = []
    for eid, edge in edges.items():
        origin = edge.get('origin', {})
        key = (origin.get('record_id'), origin.get('triple_index'))
        origins.append(key)
        triple = expected.get(key)
        record = records.get(edge.get('record_id'), {})
        check(eid + ':origin', triple is not None and key[0] == edge.get('record_id'), 'The assertion resolves to its source record and one-based triple index.')
        if triple is None:
            continue
        check(eid + ':triple', edge.get('kb_triple') == triple, 'The complete typed triple is retained exactly.')
        fields = ('subject', 'relation', 'object_type', 'polarity', 'scope', 'intent')
        check(eid + ':predication', all(edge.get(field) == triple.get(field) for field in fields) and edge.get('object_value') == triple.get('object'), 'Operational predication preserves its knowledge triple.')
        check(eid + ':endpoints', edge.get('subject') in nodes and edge.get('object') in nodes, 'Both edge endpoints resolve.')
        obj = nodes.get(edge.get('object'), {})
        type_ok = obj.get('value_type') == triple.get('object_type')
        if triple.get('object_type') == 'entity':
            type_ok = type_ok and edge.get('object') == triple.get('object')
        else:
            type_ok = type_ok and obj.get('value') == triple.get('object') and type(obj.get('value')) is type(triple.get('object'))
        check(eid + ':object_type', type_ok, 'Entity identity and typed literal values are not conflated.')
        status = 'supported' if key == ('RQ1-F03', 1) else STATUS_MAP.get(record.get('status'))
        check(eid + ':status', edge.get('status') == status and edge.get('record_status') == record.get('status'), 'Evidence state preserves the record and the supported Form 2 tail subclaim.')
        check(eid + ':negative', (edge.get('polarity') == 'negative') == (edge.get('status') == 'explicit_negative'), 'Negative polarity is restricted to explicit source negation.')
        check(eid + ':intent', edge.get('intent') in factual and edge.get('intent') in net.get('relation_intents', {}).get(edge.get('relation'), []), 'The assertion has a declared factual retrieval intent.')
        check(eid + ':limits', edge.get('scope_note') == record.get('limits_en'), 'The operational limit is the exact English record limit.')
        check(eid + ':answer', isinstance(edge.get('answer_en'), str) and bool(edge['answer_en'].strip()), 'A source-linked English answer is present; this is not a semantic correctness score.')
        check(eid + ':source_review', edge.get('source_review_status') == 'source_checked', 'Source checking is represented separately from author approval.')
        decision = edge.get('author_decision')
        if decision == 'approved':
            check(eid + ':author_review', bool(edge.get('author_reviewer')) and bool(edge.get('author_review_date')) and bool(edge.get('edge_author_review_evidence')), 'Approved edges require an explicitly identified, dated per-edge review artifact.')
        else:
            check(eid + ':author_review', decision == 'pending' and edge.get('author_reviewer') is None and edge.get('author_review_date') is None, 'Pending operational review is not attributed to an author or approval date.')
        context = edge.get('required_context_edge_ids', [])
        check(eid + ':context', len(context) == len(set(context)) and all(item in edges and item != eid for item in context), 'Required context links resolve without self-links or duplicates.')
        check(eid + ':canonical_answer', bool(edge.get('semantic_fact_id')) and edge.get('canonical_answer_edge_id') in edges, 'Presentation deduplication points to a resolving canonical answer.')
        evidence = edge.get('evidence', [])
        check(eid + ':evidence', bool(evidence), 'Every assertion has source evidence.')
        for i, quote in enumerate(evidence, 1):
            prefix = f'{eid}:quote{i}'
            check(prefix + ':fields', quote.get('source_id') == 'S01' and quote.get('page') in EXPECTED_PAGES and quote.get('language') in {'en', 'ms'} and isinstance(quote.get('quote'), str) and bool(quote['quote'].strip()), 'Evidence identifies a source, printed page, language and quotation.')
            qr = records.get(quote.get('evidence_record_id'), {})
            qi = quote.get('evidence_index')
            source = None
            if isinstance(qi, int) and 1 <= qi <= len(qr.get('evidence', [])):
                source = qr['evidence'][qi - 1]
            elif quote.get('supplemental_evidence_id') in supplemental:
                source = supplemental[quote['supplemental_evidence_id']]
            check(prefix + ':origin', source is not None and all(quote.get(field) == source.get(field) for field in ('source_id', 'page', 'language', 'quote')), 'The quote resolves byte-for-byte to source-record evidence or a registered heading.')
            check(prefix + ':scan', quote.get('source_page_sha256') == net.get('sources', {}).get('S01', {}).get('scan_sha256', {}).get(str(quote.get('page'))), 'Evidence carries the recorded source-image checksum.')
    check('origin_bijection', len(origins) == len(set(origins)) and set(origins) == set(expected), 'Every canonical triple occurs exactly once in the operational edge set.')
    check('no_identity_predicates', not any(re.sub(r'[^a-z]', '', edge.get('relation', '').lower()) in {'sameas', 'equivalentto', 'identicalto', 'disjointwith'} for edge in edges.values()), 'No unconditional identity or disjointness relation is introduced.')
    check('laga_senses', all(item in nodes for item in ('wau_laga_named_type', 'wau_laga_practice')), 'The named type and practice have separate graph identities.')
    # Stable identifiers protect source-claim identity independently of ordering.
    identity_contract = {
        'E067': ('RQ1-P02', 'wau_laga_attack', 'has_source_objective'),
        'E068': ('RQ1-P03', 'glass_glazed_string', 'has_source_competitive_purpose'),
        'E069': ('RQ1-P05', 'wau_laga_launch', 'has_source_role_label'),
        'E070': ('RQ1-P05', 'wau_laga_launch', 'has_source_role_label'),
        'E071': ('RQ1-P07', 'wau_laga_launch', 'includes_preparation'),
        'E072': ('RQ1-P08', 'wau_laga_control', 'has_source_difficulty_reason'),
        'E073': ('RQ1-S11', 'powdered_glass_on_string', 'has_source_competitive_purpose'),
        'E074': ('RQ1-S11', 'powdered_glass_on_string', 'has_source_competitive_purpose'),
        'E077': ('RQ1-S12', 'traditional_malay_wau', 'most_have'),
    }
    for eid, identity in identity_contract.items():
        edge = edges.get(eid, {})
        check(eid + ':claim_identity', tuple(edge.get(field) for field in ('record_id', 'subject', 'relation')) == identity, 'The canonical edge identifier denotes its declared source-claim identity.')
    check('launch_role_identity', edges.get('E069', {}).get('object_value') == 'juru anjong' and edges.get('E070', {}).get('object_value') == 'juru main tali', 'Distinct source role labels retain their canonical assertion identifiers.')
    check('glass_record_identity', 'RQ1-S11' in records and all(triple.get('subject') == 'powdered_glass_on_string' and triple.get('relation') == 'has_source_competitive_purpose' for triple in records['RQ1-S11'].get('triples', [])) and bool(records['RQ1-S11'].get('triples')), 'S11 denotes the source-scoped competitive purpose of the glass-coated string.')
    majority = [edge for edge in edges.values() if edge.get('relation') == 'most_have']
    check('qualified_class_context', len(majority) == 1 and majority[0].get('record_id') == 'RQ1-S12' and majority[0].get('edge_id') == 'E077' and majority[0].get('quantifier') == 'most' and majority[0].get('inheritance') == 'context_only', 'S12/E077 is a qualified class statement; it cannot establish an undocumented subtype property.')
    feature_results = []
    for subject, wanted in [('wau_kikik', 'explicit_negative'), ('wau_laga_named_type', 'not_documented'), ('traditional_malay_wau', 'supported')]:
        result = resolve_feature(net, subject, 'leaf_shaped_wings')
        ok = result.get('status') == wanted and result.get('inherited_as_subtype_fact') is False
        if subject != 'traditional_malay_wau':
            ok = ok and result.get('class_context_edge_ids') == ['E077']
        else:
            ok = ok and result.get('quantifier') == 'most'
        check('feature:' + subject, ok, 'Qualified class context does not override direct exclusion or imply universal inheritance.')
        feature_results.append(result)
    for rid in ('RQ1-F03', 'RQ1-F04'):
        group = [edge for edge in edges.values() if edge.get('variance_group_id') == rid]
        langs = {(quote.get('language'), quote.get('page')) for edge in group for quote in edge.get('evidence', [])}
        check(rid + ':source_variance', len(group) == 2 and langs == {('ms', 72), ('en', 73)} and all({other['edge_id'] for other in group if other != edge} <= set(edge.get('required_context_edge_ids', [])) for edge in group), 'Both language-specific source descriptions remain paired.')
    candidates = net.get('candidate_names', [])
    candidate = candidates[0] if len(candidates) == 1 else {}
    check('kemetek_unasserted', candidate.get('candidate_id') == 'E005' and candidate.get('status') == 'not_documented' and candidate.get('asserted') is False and candidate.get('traversable') is False and candidate.get('evidence') == [] and records.get('RQ1-N04', {}).get('triples') == [] and not any('wau_kemetek_name' in (edge.get('subject'), edge.get('object')) for edge in edges.values()), 'Kemetek has no invented book citation or traversable assertion.')
    group = deduplicate_answers([edges['E012'], edges['E052']])
    check('defence_deduplication', len(group) == 1 and group[0].get('canonical_answer_edge_id') == 'E012' and group[0].get('source_edge_ids') == ['E012', 'E052'], 'The defence action is presented once with both record references.')
    catalog = net.get('record_catalog', [])
    check('catalog_identity', len(catalog) == len(records) and {record.get('record_id') for record in catalog} == set(records), 'The record catalog covers the complete knowledge registry.')
    for record in catalog:
        rid = record['record_id']
        check(rid + ':catalog', set(record.get('edge_ids', [])) == {eid for eid, edge in edges.items() if edge.get('record_id') == rid}, 'Catalog edge links exactly cover the record assertions.')
    source_records = review.get('records', [])
    check('source_review_coverage', len(source_records) == len(records) and {record.get('record_id') for record in source_records} == set(records), 'The source-check ledger covers all records.')
    check('source_review_scope', set(review.get('scope', {}).get('original_page_images_reviewed', [])) == EXPECTED_PAGES, 'Source-check scope is the five named page images.')
    check('no_expert_review_claim', all(record.get('cultural_expert_review') == 'not_performed' for record in source_records), 'No cultural-expert validation is inferred from source checking.')
    pending = [eid for eid, edge in edges.items() if edge.get('author_decision') != 'approved']
    approved = len(edges) - len(pending)
    check('review_count', net.get('author_review', {}).get('approved_edges') == approved, 'The network approval count matches actual per-edge decisions.')
    if pending:
        check('approval_not_inferred', net.get('source_review', {}).get('human_author_approval') is False and net.get('author_review', {}).get('status') != 'approved', 'Pending edge review is not represented as global human approval.')
        warnings.append(f'{len(pending)} operational edges require explicit per-edge author review; source checking alone does not approve their representation.')
    expected_counts = {'records': len(records), 'assertion_edges': len(edges), 'nodes': len(nodes), 'candidate_names': len(candidates)}
    check('network_counts', all(net.get('counts', {}).get(key) == value for key, value in expected_counts.items()), 'Published representation counts match the actual objects.')
    check('edge_status_counts', net.get('counts', {}).get('edge_statuses') == dict(Counter(edge.get('status') for edge in edges.values())), 'Evidence-state totals are computed from the current edges.')
    for path in (args.knowledge, args.network, args.review):
        raw = path.read_text(encoding='utf-8')
        check(path.name + ':metadata_language', not re.search(r'[\u0600-\u06ff]', raw), 'Operational explanatory metadata is English; verbatim Malay evidence is retained.')
        check(path.name + ':personal_identifier', not re.search(r'\bTP\d{6}\b', raw), 'No student identifier is present in the public-facing knowledge artifacts.')
    if args.source_root:
        for page in sorted(EXPECTED_PAGES):
            image = args.source_root / f'page-{page:04d}.jpg'
            check(f'source_image_{page}', image.is_file() and digest(image) == net['sources']['S01']['scan_sha256'][str(page)], 'Available original source-image bytes match the recorded checksum.')
    else:
        warnings.append('Original image bytes were not checked in this run; use --source-root to check available source images.')
    report = {'validation_kind': 'structural_source_link_contract', 'validated_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'result': 'fail' if errors else 'pass', 'inputs': {path.name: digest(path) for path in (args.knowledge, args.network, args.review)},
              'counts': {**expected_counts, 'canonical_triples': len(expected), 'checks': len(checks), 'failed_checks': len(errors)},
              'author_edge_review': {'approved': approved, 'pending': len(pending), 'pending_edge_ids': pending},
              'human_author_approval_claimed': False, 'bot_tests_executed': False, 'performance_results_claimed': False,
              'prototype_source_consistency': 'pass' if not errors else 'fail', 'study_ready': False,
              'readiness_note': 'Structural source consistency permits prototype inspection only. Operational author review, independent held-out evaluation and applicable study requirements remain separate gates.',
              'feature_resolution_contract_checks': feature_results, 'warnings': warnings, 'errors': errors, 'checks': checks}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"{report['result'].upper()}: {len(records)} records, {len(edges)} edges; {len(errors)} structural errors; {len(pending)} edges awaiting author review.")
    print('No chatbot accuracy or participant-study readiness is established by this check.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
