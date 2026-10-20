"""Safeguard tests with synthetic rows; these are not chatbot accuracy tests."""
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('rq2_tool',Path(__file__).with_name('rq2_tool.py'))
rq2=importlib.util.module_from_spec(spec);spec.loader.exec_module(rq2)


def sample():
    data=rq2.load(Path(__file__).with_name('question_collection_template.json'))
    data['independence']={
        'question_author':'Synthetic tester','gold_reviewer':'Synthetic reviewer',
        'authoring_started_at_utc':'2026-01-01T02:00:00+00:00','authoring_completed_at_utc':'2026-01-01T03:00:00+00:00',
        'author_did_not_develop_engine':True,'questions_not_seen_by_developer_before_build_freeze':True,
        'questions_written_without_bot_answers':True,'gold_fixed_before_execution':True}
    for q in data['questions']:
        q.update(question='Synthetic input '+q['question_id'],expected_answer='Synthetic required answer',required_claims=['Synthetic criterion'],forbidden_claims=[],evidence=[],scope_reason='Synthetic scope',expected_context='Synthetic antecedent',gold_reviewer='Synthetic reviewer')
        if q['stratum']=='context':q['expected_state']='supported'
        q['answerable_from_sources']=q['expected_state'] not in {'not_documented','out_of_scope'}
        if q['expected_state'] in {'supported','explicit_negative','source_variance'}:q['evidence']=[{'source_id':'SYNTHETIC','page':1,'quote':'Synthetic quotation'}]
    lock={'frozen_at_utc':'2026-01-01T01:00:00+00:00','artifacts':{}}
    return data,lock


def scoring(data):
    rows=[]
    for q in data['questions']:
        rows.append({'question_id':q['question_id'],'score':'full','state_correct':True,'answer_present':q['answerable_from_sources'],'unsupported_claim_count':0,'cited_claim_count':1 if q['evidence'] else 0,'supported_cited_claim_count':1 if q['evidence'] else 0,'appropriate_refusal':True if q['stratum']=='out_of_scope' else None,'context_correct':True if q['turn_index']>1 else None,'reviewer':'Synthetic reviewer','reviewed_at_utc':'2026-01-01T04:00:00+00:00','reason':'Synthetic criterion met'})
    return {'scores':rows}


class EvaluationSafeguards(unittest.TestCase):
    def test_fixed_design_accepts_complete_synthetic_collection(self):
        d,l=sample();s=rq2.validate_dataset(d,l)
        self.assertEqual((s['question_turns'],s['sessions'],s['follow_up_turns']),(72,66,6))
    def test_blank_template_cannot_register(self):
        d=rq2.load(Path(__file__).with_name('question_collection_template.json'))
        with self.assertRaises(ValueError):rq2.validate_dataset(d,{'frozen_at_utc':'2026-01-01T00:00:00+00:00'})
    def test_pre_freeze_questions_rejected(self):
        d,l=sample();d['independence']['authoring_started_at_utc']='2025-12-31T23:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'predates'):rq2.validate_dataset(d,l)
    def test_development_overlap_rejected(self):
        d,l=sample();dev={'scenarios':[{'inputs':[{'input_type':'message','input':d['questions'][0]['question']}]}]}
        with self.assertRaisesRegex(ValueError,'overlap'):rq2.validate_dataset(d,l,dev)
    def test_additional_development_overlap_rejected(self):
        d,l=sample();dev={'sessions':[{'turns':[{'question':d['questions'][0]['question']}]}]}
        with self.assertRaisesRegex(ValueError,'overlap'):rq2.validate_dataset(d,l,dev)

    def test_exposed_question_registry_rejects_exact_overlap(self):
        d,l=sample()
        dev={'exposed_questions':[d['questions'][0]['question']]}
        with self.assertRaisesRegex(ValueError,'overlap'):rq2.validate_dataset(d,l,dev)

    def test_conversation_and_registry_are_loaded_as_development(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            rq2.save_new(p/'test_scenarios.json',{'scenarios':[]})
            rq2.save_new(p/'evaluation/conversation_development.json',{'sessions':[{'turns':[{'question':'Synthetic dialogue question'}]}]})
            rq2.save_new(p/'evaluation/development_questions.json',{'questions':['Synthetic unit question']})
            material=rq2.development_material(p)
            self.assertEqual(material['sessions'][0]['turns'][0]['question'],'Synthetic dialogue question')
            self.assertEqual(material['exposed_questions'],['Synthetic unit question'])
    def test_duplicate_questions_rejected(self):
        d,l=sample();d['questions'][1]['question']=d['questions'][0]['question']
        with self.assertRaisesRegex(ValueError,'Duplicate'):rq2.validate_dataset(d,l)
    def test_missing_follow_up_definition_rejected(self):
        d,l=sample();next(q for q in d['questions'] if q['turn_index']==2)['expected_context']=''
        with self.assertRaisesRegex(ValueError,'Follow-up'):rq2.validate_dataset(d,l)
    def test_changed_locked_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'engine.py').write_text('initial')
            l={'artifacts':{'engine.py':rq2.digest(p/'engine.py')}}
            rq2.verify_build(p,l);(p/'engine.py').write_text('changed')
            with self.assertRaisesRegex(ValueError,'mismatch'):rq2.verify_build(p,l)
    def test_write_cannot_overwrite_record(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'record.json';rq2.save_new(p,{'x':1})
            with self.assertRaises(FileExistsError):rq2.save_new(p,{'x':2})
    def test_coverage_and_correctness_have_distinct_denominators(self):
        d,l=sample();s=scoring(d)
        # One supported abstention and one attempted wrong answer.
        s['scores'][0].update(score='abstain',answer_present=False,state_correct=False,reason='No answer')
        s['scores'][1].update(score='wrong',state_correct=False,reason='Wrong answer')
        out=rq2.summarise(d,s)
        self.assertEqual(out['answerable_coverage'],rq2.ratio(47,48))
        self.assertEqual(out['strict_correctness_among_attempted_answerable'],rq2.ratio(46,47))
        self.assertEqual(out['answerable_full_credit'],rq2.ratio(46,48))
        self.assertEqual(out['follow_up_context'],rq2.ratio(6,6))
        self.assertEqual(out['scope_refusal'],rq2.ratio(12,12))
        self.assertEqual(out['strict_in_scope_success'],rq2.ratio(58,60))
    def test_unsupported_claim_cannot_receive_partial_or_full_credit(self):
        d,l=sample();s=scoring(d);s['scores'][0].update(score='partial',unsupported_claim_count=1)
        with self.assertRaisesRegex(ValueError,'unsupported'):rq2.summarise(d,s)
    def test_full_answerable_credit_requires_answer(self):
        d,l=sample();s=scoring(d);s['scores'][0]['answer_present']=False
        with self.assertRaisesRegex(ValueError,'substantive answer'):rq2.summarise(d,s)
    def test_pending_scores_do_not_yield_accuracy(self):
        d,l=sample();s=scoring(d);s['scores'][0]['score']=None
        with self.assertRaisesRegex(ValueError,'completed'):rq2.summarise(d,s)
    def test_pending_operational_review_blocks_freeze(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);rq2.save_new(p/'WauTrace_Network_Template.json',{'edges':[],'record_catalog':[],'response_catalog':{}})
            with self.assertRaisesRegex(ValueError,'operational approval'):rq2.freeze(p,p/'lock.json')
            self.assertFalse((p/'lock.json').exists())
    def test_exact_approved_synthetic_review_accepts_then_rejects_changed_profile(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            evidence=[{'source_id':'SYNTHETIC','page':1,'language':'en','quote':'Synthetic quote'}]
            edge={'edge_id':'E1','record_id':'R1','subject':'s','relation':'r','polarity':'positive','status':'supported','scope':'synthetic','answer_en':'Synthetic answer','kb_triple':{'object':'o'},'evidence':evidence}
            catalog={'profiles':{'p':{'edge_ids':['E1']}},'clarifications':{},'messages':{},'suggestions':{}}
            graph={'edges':[edge],'record_catalog':[{'record_id':'R1','limits_en':'Synthetic limit'}],'response_catalog':catalog}
            claim={k:edge[k] for k in ('edge_id','record_id','subject','relation','polarity','status','scope','answer_en')}
            claim.update(object='o',limits_en='Synthetic limit',evidence=[{'page':1,'language':'en','quote':'Synthetic quote'}])
            decision={'author_decision':'approved','decision_reason':'Synthetic test approval','author_reviewer':'Synthetic reviewer','author_review_date':'2026-01-01'}
            claim.update(decision)
            response={'profiles':[dict(profile_id='p',profile_payload=catalog['profiles']['p'],profile_sha256=rq2.value_digest(catalog['profiles']['p']),**decision)],'response_catalog_sha256':rq2.value_digest(catalog),'additional_catalog_content':{k:catalog[k] for k in ('clarifications','messages','suggestions')},'additional_catalog_review':decision.copy()}
            rq2.save_new(p/'WauTrace_Network_Template.json',graph);rq2.save_new(p/'knowledge.json',{'synthetic':True})
            rq2.save_new(p/'reviews/operational_claim_review.json',{'claims':[claim]});rq2.save_new(p/'reviews/response_composition_review.json',response)
            receipt_path=p/'reviews/operational_approval_receipt.json';receipt=rq2.approval_template(p,receipt_path)
            receipt.update(status='approved',reviewer='Synthetic reviewer',reviewed_at_utc='2026-01-01T00:00:00+00:00',reason='Synthetic approval')
            receipt_path.write_text(__import__('json').dumps(receipt))
            self.assertEqual(rq2.verify_operational_review(p)['approved_edges'],1)
            graph['response_catalog']['profiles']['p']['edge_ids']=[]
            (p/'WauTrace_Network_Template.json').write_text(__import__('json').dumps(graph))
            with self.assertRaisesRegex(ValueError,'differs'):rq2.verify_operational_review(p)
    def test_single_execution_and_tampered_response_safeguards(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);d,l=sample()
            (p/'wautrace_engine.py').write_text("class WauTraceEngine:\n def respond(self, question, state):\n  return {'text':'Synthetic answer','status':'supported','state':state}\n")
            rq2.save_new(p/'test_scenarios.json',{'scenarios':[]})
            l['artifacts']={'wautrace_engine.py':rq2.digest(p/'wautrace_engine.py')}
            rq2.save_new(p/'lock.json',l);rq2.save_new(p/'questions.json',d)
            rq2.register(p,p/'lock.json',p/'questions.json',p/'registration.json')
            result=rq2.execute(p,p/'lock.json',p/'questions.json',p/'registration.json',p/'results')
            self.assertEqual(result['executed_turns'],72)
            with self.assertRaises(FileExistsError):rq2.execute(p,p/'lock.json',p/'questions.json',p/'registration.json',p/'second_results')
            score=scoring(d);score.update(dataset_sha256=rq2.digest(p/'questions.json'),execution_sha256=rq2.digest(p/'results/responses.jsonl'))
            rq2.save_new(p/'completed_scores.json',score)
            result=rq2.score(p/'questions.json',p/'results',p/'completed_scores.json',p/'metrics.json')
            self.assertEqual(result['unit_counts']['question_turns'],72)
            with (p/'results/responses.jsonl').open('a') as f:f.write('tampered')
            with self.assertRaisesRegex(ValueError,'responses changed'):rq2.score(p/'questions.json',p/'results',p/'completed_scores.json',p/'bad_metrics.json')
    def test_registered_gold_cannot_be_changed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);d,l=sample()
            rq2.save_new(p/'test_scenarios.json',{'scenarios':[]})
            rq2.save_new(p/'lock.json',l);rq2.save_new(p/'questions.json',d)
            rq2.register(p,p/'lock.json',p/'questions.json',p/'registration.json')
            d['questions'][0]['expected_answer']='Changed after registration'
            (p/'questions.json').write_text(__import__('json').dumps(d))
            with self.assertRaisesRegex(ValueError,'changed after registration'):rq2.execute(p,p/'lock.json',p/'questions.json',p/'registration.json',p/'results')
            self.assertFalse((p/'results').exists())
    def test_zero_denominator_is_not_applicable(self):
        self.assertEqual(rq2.ratio(0,0),{'numerator':0,'denominator':0,'proportion':None})

if __name__=='__main__':unittest.main(verbosity=2)
