"""Execute known development scenarios. This does not estimate RQ2 accuracy."""
from __future__ import annotations
import argparse, copy, hashlib, html, json
from pathlib import Path
from datetime import datetime, timezone
from wautrace_engine import WauTraceEngine
RESULT_KEYS = {"text":str,"status":str,"source_cards":list,"edge_ids":list,"record_ids":list,"state":dict,"suggestions":list}
STATUS_COMPATIBILITY = {
    "supported": ["supported"],
    "explicit_negative": ["explicit_negative"],
    "unsupported_inference_from_explicit_negative": ["explicit_negative", "not_documented"],
    "supported_naming_explanation_with_unsupported_material_inference": ["supported", "not_documented"],
    "supported_with_scope_limit": ["supported", "not_documented"],
    "supported_source_statements_with_unresolved_relationship": ["supported", "source_variance", "not_documented"],
    "unverified": ["not_documented"],
    "not_established_in_reviewed_corpus": ["not_documented"],
    "current_claim_outside_corpus": ["not_documented"],
    "out_of_scope": ["not_documented"],
    "ambiguous_query": ["clarification"],
    "supported_after_clarification": ["supported"],
    "discrepancy": ["source_variance", "supported"],
    "supported_shared_subclaim": ["supported"],
    "supported_literal_with_unresolved_interpretation": ["supported", "source_variance", "not_documented"],
    "supported_with_relation_correction": ["supported"],
    "unsupported_inference_from_supported_comparison": ["not_documented"],
    "context_reset": ["system"],
}
# These rubric states explicitly require reporting at least one source claim.
# Absence of cards on other states still requires human inspection for hidden
# factual claims; the screen cannot establish semantic support from prose alone.
SOURCE_REQUIRED = {
    "supported", "explicit_negative",
    "supported_naming_explanation_with_unsupported_material_inference",
    "supported_with_scope_limit",
    "supported_source_statements_with_unresolved_relationship",
    "supported_after_clarification", "discrepancy", "supported_shared_subclaim",
    "supported_literal_with_unresolved_interpretation", "supported_with_relation_correction",
}
def normalized_quote(value):
    return " ".join(value.split()) if isinstance(value, str) else None


def flag(name, passed, detail, kind="check"):
    return {"name": name, "passed": passed, "detail": detail, "kind": kind}


def screen_response(response, case, turn, graph):
    """Check observable protocol/provenance facts without scoring English prose."""
    flags = []
    if not isinstance(response, dict):
        return [flag("response_schema", False, "Expected a JSON-serializable response mapping.")]
    bad = [key for key, typ in RESULT_KEYS.items() if not isinstance(response.get(key), typ)]
    if "intent" not in response or not (response.get("intent") is None or isinstance(response.get("intent"), str)):
        bad.append("intent")
    flags.append(flag("response_schema", not bad, "Invalid or missing fields: " + ", ".join(bad) if bad else "Required public response fields have their documented types."))
    if bad:
        return flags
    flags.append(flag("nonempty_response", bool(response["text"].strip()), "Response text must be nonempty."))
    expected_state = turn["expected_evidence_state"]
    allowed_status = STATUS_COMPATIBILITY[expected_state]
    flags.append(flag("status_compatibility", response["status"] in allowed_status,
                      {"expected_rubric_state": expected_state, "compatible_api_labels": allowed_status, "actual": response["status"]}))
    expected_intent = turn.get("expected_intent")
    allowed_intents = {expected_intent, *turn.get("related_intents", [])}
    if expected_state == "context_reset":
        # The public reset operation uses a system response with a fallback route.
        # Store the literal route; do not pretend it was a knowledge request.
        allowed_intents.add("not_documented")
    flags.append(flag("intent_compatibility", response["intent"] in allowed_intents,
                      {"expected": expected_intent, "compatible": sorted(allowed_intents, key=str), "actual": response["intent"]}))
    edges = {edge["edge_id"]: edge for edge in graph["edges"]}
    candidate_records = {candidate["record_id"] for candidate in graph.get("candidate_names", [])}
    known_records = {edge["record_id"] for edge in graph["edges"]} | candidate_records
    selected_ids = response["edge_ids"]
    flags.append(flag("returned_edge_ids_resolve", all(isinstance(e, str) and e in edges for e in selected_ids), {"edge_ids": selected_ids}))
    flags.append(flag("returned_record_ids_resolve", all(isinstance(r, str) and r in known_records for r in response["record_ids"]), {"record_ids": response["record_ids"]}))
    allowed_records = set(turn.get("allowed_record_ids", []))
    outside_records = sorted(set(response["record_ids"]) - allowed_records)
    flags.append(flag("record_scope_review", None if outside_records else True,
                      {"outside_turn_allowed_records": outside_records,
                       "instruction": "Inspect any additional context claim against the frozen allowed scope; no automatic semantic credit."},
                      kind="review"))
    allowed_pages = {(e["source_id"], e["page"]) for e in case.get("allowed_pages", [])}
    turn_pages = {
        (page["source_id"], page["page"])
        for evidence in case.get("allowed_evidence", [])
        if evidence["record_id"] in allowed_records
        for page in evidence.get("source_pages", [])
    }
    allowed_nonpaginated = {e["source_id"] for e in case.get("allowed_non_paginated_sources", [])}
    valid_turn_cards = 0
    for index, card in enumerate(response["source_cards"], start=1):
        prefix = f"source_card_{index}"
        if not isinstance(card, dict):
            flags.append(flag(prefix + "_schema", False, "Source card is not a mapping."))
            continue
        source_id, page = card.get("source_id"), card.get("page")
        if page is None and source_id in allowed_nonpaginated:
            # Only provenance is allowed; this is not proof of a cultural claim.
            flags.append(flag(prefix + "_nonpaginated_provenance", source_id in graph.get("sources", {}), "Assignment provenance only; no book-equivalence credit."))
            continue
        edge_ids = card.get("edge_ids", [])
        schema_ok = (isinstance(source_id, str) and isinstance(page, int)
                     and isinstance(card.get("quote"), str) and bool(card["quote"].strip())
                     and isinstance(edge_ids, list) and bool(edge_ids)
                     and isinstance(card.get("language"), str))
        flags.append(flag(prefix + "_schema", schema_ok, "Book card requires source, printed page, language, quote and edge IDs."))
        if not schema_ok:
            continue
        quote = normalized_quote(card["quote"])
        matching_ids = []
        for edge_id in edge_ids:
            edge = edges.get(edge_id, {})
            if any(e.get("source_id") == source_id and e.get("page") == page
                   and e.get("language") == card["language"]
                   and normalized_quote(e.get("quote")) == quote
                   for e in edge.get("evidence", [])):
                matching_ids.append(edge_id)
        resolves = len(matching_ids) == len(edge_ids)
        flags.append(flag(prefix + "_quote_resolves", resolves,
                          {"edge_ids": edge_ids, "matching_edge_ids": matching_ids,
                           "rule": "Exact evidence quote after whitespace normalization, same language/source/page."}))
        flags.append(flag(prefix + "_selected_edges", all(e in selected_ids for e in edge_ids), "Every cited edge is selected in this response."))
        flags.append(flag(prefix + "_allowed_page", (source_id, page) in allowed_pages,
                          {"actual": [source_id, page], "allowed_case_pages": sorted(allowed_pages)}))
        in_turn = (source_id, page) in turn_pages and any(edges.get(e, {}).get("record_id") in allowed_records for e in matching_ids)
        if resolves and in_turn:
            valid_turn_cards += 1
        if not in_turn:
            flags.append(flag(prefix + "_turn_scope_review", None, "Card falls outside the turn's supporting record/page pairs; inspect its contextual relevance.", kind="review"))
    if len(allowed_status) > 1:
        flags.append(flag("evidence_boundary_review", None,
                          "The public badge can describe a primary source claim or its knowledge boundary. The author must verify the complete qualification and must not infer semantic correctness from badge compatibility.", kind="review"))
    if expected_state in SOURCE_REQUIRED:
        flags.append(flag("required_source_present", valid_turn_cards > 0,
                          {"valid_turn_support_cards": valid_turn_cards, "rule": "At least one card resolves to an allowed supporting record and page; semantic coverage still requires review."}))
    else:
        flags.append(flag("citation_omission_review", None,
                          "Cards may be absent for pure clarification, reset, or unsupported/out-of-scope responses. The author must check whether the prose introduces a substantive book claim requiring a citation.", kind="review"))
    if expected_state == "context_reset":
        state = response["state"]
        nonempty_context = {key: value for key, value in state.items()
                            if value not in (None, "", [], {}, False)}
        flags.append(flag("reset_empty_context", not nonempty_context,
                          {"remaining_nonempty_state": nonempty_context}))
        flags.append(flag("reset_no_evidence", not response["source_cards"] and not selected_ids,
                          "Reset must not reuse the previous factual answer or source selection."))
    if expected_state == "ambiguous_query":
        flags.append(flag("clarification_suggestions_present", len(response["suggestions"]) >= 2,
                          "Two choices must be exposed; their meaning and pending state require author review."))
    return flags



def execute(base, output_dir):
    if output_dir.exists():
        raise ValueError("Output directory already exists. Keep actual results unchanged; choose an empty destination.")
    contract=json.loads((base/'test_scenarios.json').read_text(encoding='utf-8'))
    graph=json.loads((base/'WauTrace_Network_Template.json').read_text(encoding='utf-8'))
    engine=WauTraceEngine()
    cases=[]
    for case in contract['scenarios']:
        state={}; turns=[]
        for turn in case['inputs']:
            text=turn['input'] if turn['input_type']=='message' else 'start over'
            error=None
            try:
                response=engine.respond(text,copy.deepcopy(state));state=response['state']
                checks=screen_response(response,case,turn,graph)
            except Exception as exc:
                error=type(exc).__name__+': '+str(exc);response=None;checks=[flag('execution',False,error)]
            turns.append({'turn_number':turn['turn_number'],'input':turn['input'],'input_type':turn['input_type'],'response':response,'checks':checks,'error':error,'expected_behaviour':turn['expected_behaviour'],'criteria':turn['pass_criteria'],'semantic_score':None,'reviewer_note':None})
        cases.append({'case_id':case['test_id'],'category':case['category'],'turns':turns,'semantic_case_pass':None})
    checks=[f for c in cases for t in c['turns'] for f in t['checks']]
    summary={'purpose':'development_regression_only','rq2_accuracy':None,'cases':len(cases),'steps':sum(len(c['turns']) for c in cases),'machine_checks_passed':sum(x['passed'] is True for x in checks),'machine_checks_failed':sum(x['passed'] is False for x in checks),'manual_flags':sum(x['passed'] is None for x in checks),'semantic_review':'pending','generated_at_utc':datetime.now(timezone.utc).isoformat()}
    report={'summary':summary,'cases':cases,'input_sha256':hashlib.sha256((base/'test_scenarios.json').read_bytes()).hexdigest(),
            'runtime_sha256':{name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in ('wautrace_engine.py','graph_inference.py','language_rules.json','WauTrace_Network_Template.json','reviews/operational_claim_review.json')}}
    output_dir.mkdir(parents=True)
    for name,data in [('responses.json',report),('summary.json',summary)]:
        (output_dir/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    esc=lambda x:html.escape(str(x))
    parts=['<!doctype html><html lang="en"><meta charset="utf-8"><title>Development response review</title><style>body{font:15px/1.5 Arial;max-width:1000px;margin:30px auto;padding:20px}pre{white-space:pre-wrap}section{border-top:1px solid #aaa;padding:20px 0}blockquote{border-left:3px solid #aaa;padding:10px}</style><h1>Development regression response review</h1><p>Known development examples. This is not RQ2 accuracy. Automated checks do not replace semantic review.</p><pre>'+esc(json.dumps(summary,indent=2))+'</pre>']
    for c in cases:
        parts.append('<h2>'+esc(c['case_id'])+'</h2>')
        for t in c['turns']:
            response = t['response'] or {}
            detail = '<details><summary>More detail</summary><p>'+esc(response['details_en'])+'</p></details>' if response.get('details_en') else ''
            parts.append('<section><h3>'+esc(t['input'])+'</h3><blockquote>'+esc(response.get('text',t['error']))+'</blockquote>'+detail+'<p><b>Expected:</b> '+esc(t['expected_behaviour'])+'</p><pre>'+esc(json.dumps({'criteria':t['criteria'],'checks':t['checks'],'source_cards':response.get('source_cards',[])},indent=2,ensure_ascii=False))+'</pre><p>Semantic review: pending.</p></section>')
    (output_dir/'review.html').write_text(''.join(parts)+'</html>',encoding='utf-8')
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=Path('evaluation/development_results'))
    args=parser.parse_args();base=Path(__file__).resolve().parent
    print(json.dumps(execute(base,args.output_dir.resolve()),indent=2))
if __name__=='__main__':main()
