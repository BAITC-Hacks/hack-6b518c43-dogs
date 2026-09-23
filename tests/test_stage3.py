"""Version provenance and online decision trace regressions; no paid requests."""
import copy,json,tempfile,unittest
from pathlib import Path
import test_assistant as fixtures
from backend.identity import verified_measurement
from agent import Engine

class Stage3Tests(unittest.TestCase):
    setUp=fixtures.AssistantTests.setUp
    tearDown=fixtures.AssistantTests.tearDown
    assistant=fixtures.AssistantTests.assistant
    # Reuse the real Engine/PlanService fixture; only new behaviours are tested here.
    def test_measurement_requires_all_identity_fields_and_exact_plan(self):
        self.assertIsNotNone(self.service.get(self.id)['measurement'])
        original=copy.deepcopy(self.record)
        for field in ['algorithm_version','engine_sha256','data_fingerprint']:
            self.record['identity'][field]='different'
            self.assertIsNone(self.service.get(self.id)['measurement'])
            self.assertTrue(self.service.get(self.id)['archived'])
            with self.assertRaisesRegex(ValueError,'Архивный'):self.service.propose(self.id,self.id,{})
            self.record=copy.deepcopy(original)
        self.record['plan'][0]['channel']='call'
        self.assertIsNone(self.service.get(self.id)['measurement'])
        self.record=copy.deepcopy(original);self.record['measurement_binding']['plan_id']='wrong'
        self.assertIsNone(self.service.get(self.id)['measurement'])
        self.record=copy.deepcopy(original);self.record['measurement_binding']['run_id']='wrong'
        self.assertIsNone(self.service.get(self.id)['measurement'])
        self.record=copy.deepcopy(original);self.record.pop('identity')
        self.assertTrue(self.service.get(self.id)['archived'])

    def test_proposals_are_unmeasured_and_survive_reloading(self):
        proposed=self.service.propose(self.id,self.id,{'budget':7000,'max_campaigns':5})
        self.assertIsNone(proposed['measurement']);self.assertEqual(proposed['identity'],self.record['identity'])
        self.service.apply(self.id,proposed['plan_id'],self.id)
        self.assertEqual(self.service.active_id(self.id),proposed['plan_id'])
        disk=json.loads((self.service.directory/(proposed['plan_id']+'.json')).read_text())
        disk['measurement']=self.record['official']
        (self.service.directory/(proposed['plan_id']+'.json')).write_text(json.dumps(disk))
        self.assertIsNone(self.service.get(self.id,proposed['plan_id'])['measurement'])
        self.assertEqual(self.service.get(self.id)['plan'],self.record['plan'])
        disk['identity']['data_fingerprint']='different'
        (self.service.directory/(proposed['plan_id']+'.json')).write_text(json.dumps(disk))
        with self.assertRaisesRegex(ValueError,'другому набору'):self.service.get(self.id,proposed['plan_id'])

    def test_trace_captures_actual_update_without_claiming_gain(self):
        pilot=self.record['knowledge']['pilots'][0];trace=pilot['decision_change']
        self.assertAlmostEqual(trace['estimate_channel_before'],pilot['prior']['mean']*.65)
        self.assertAlmostEqual(trace['estimate_channel_after'],pilot['posterior']['mean']*.65)
        self.assertEqual(trace['selection_changed'],trace['before']['plan']!=trace['after']['plan'])
        self.assertTrue(trace['before']['plan']);self.assertTrue(trace['after']['plan'])
        self.assertNotIn('measured_gain',trace)

    def test_external_call_trace_distinguishes_fake_and_cached(self):
        assistant,fake=self.assistant('scenario')
        first=assistant.ask(self.id,self.id,'Сократи бюджет')
        self.assertEqual(first['status'],'completed');self.assertFalse(first['network_call'])
        self.assertGreater(first['usage']['calls'],0)
        trace=first['tool_trace'][0]
        self.assertEqual(trace['parameters']['budget_change_percent'],-30)
        self.assertEqual(trace['validated_constraints']['budget'],7000)
        cached=assistant.ask(self.id,self.id,'Сократи бюджет')
        self.assertTrue(cached['cached']);self.assertFalse(cached['network_call'])
        self.assertEqual(cached['usage']['calls'],0);self.assertEqual(cached['usage']['estimated_usd'],0)

