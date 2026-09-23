"""GPT mini adapter protocol verification, explicitly without external API calls."""
import os,unittest
from unittest.mock import patch
import test_assistant as fixtures

class MiniTests(unittest.TestCase):
    setUp=fixtures.AssistantTests.setUp
    tearDown=fixtures.AssistantTests.tearDown
    assistant=fixtures.AssistantTests.assistant

    def test_default_mini_real_planning_tools_and_token_prices(self):
        with patch.dict(os.environ):
            os.environ.pop('OPENAI_MODEL',None)
            a,fake=self.assistant('scenario')
            self.assertEqual(a.configuration()[:2],('gpt-5.4-mini',(.75,.075,4.5,.75)))
            result=a.ask(self.id,self.id,'Сократи бюджет на 30%, исключи звонки')
        self.assertEqual(result['status'],'completed')
        self.assertFalse(result['network_call'])
        self.assertEqual(result['proposal']['forecast']['constraints']['budget'],7000)
        self.assertEqual(self.service.active_id(self.id),self.id)
        for request in fake.requests:
            self.assertEqual(request['model'],'gpt-5.4-mini')
            self.assertEqual(request['reasoning'],{'effort':'low'})
            self.assertFalse(request['store'])
            self.assertFalse(request['parallel_tool_calls'])
        self.assertAlmostEqual(a.ledger.stats()['estimated_usd'],.00213)

if __name__=='__main__':unittest.main()

class ReferenceRepairTests(unittest.TestCase):
    setUp=fixtures.AssistantTests.setUp
    tearDown=fixtures.AssistantTests.tearDown

    def test_invalid_reference_can_be_corrected_once_without_new_scenario(self):
        import json
        from backend.assistant import Assistant
        class OnceBad(fixtures.FakeClient):
            async def create(self,**kwargs):
                response=await super().create(**kwargs)
                if len(self.requests)==2:
                    data=json.loads(response.output_text);data['metric_ids']=['unverified-reference']
                    response.output_text=json.dumps(data)
                return response
        fake=OnceBad('scenario')
        with patch.dict(os.environ,{'OPENAI_MODEL':'gpt-5.4-mini'}):
            a=Assistant(self.service,self.root/'repair.sqlite3',client_factory=lambda:fake)
            result=a.ask(self.id,self.id,'Сократи бюджет')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(fake.requests),3)
        self.assertEqual(len(result['tool_trace']),1)
        self.assertEqual(result['tool_trace'][0]['tool'],'propose_scenario')
        self.assertEqual(self.service.active_id(self.id),self.id)
        self.assertNotIn('unverified-reference',json.dumps(result))
        self.assertFalse(result['network_call'])
