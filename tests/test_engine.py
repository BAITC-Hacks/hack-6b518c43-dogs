import ast
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from agent import Agent, Engine, expected_best, normal_update

CHANNELS = {'push': {'cost_per_contact': 0, 'conversion_multiplier': .5},
            'sms': {'cost_per_contact': 4, 'conversion_multiplier': .65},
            'call': {'cost_per_contact': 160, 'conversion_multiplier': 1.2}}


def fixture(n=40, missing=False):
    profile = pd.DataFrame({'ID_NUMBER': [f'id_{i:06}' for i in range(n)],
        'current_tariff': ['a'] * n, 'arpu_segment': ['MID'] * n,
        'data_segment': ['LITE' if i % 2 else 'HEAVY' for i in range(n)],
        'call_segment': ['LOW'] * n, 'predicted_arpu': [1000.] * n})
    if missing:
        profile.loc[0, 'current_tariff'] = None
    tariffs = pd.DataFrame({'tariff_plan_code': ['a', 'b', 'c'], 'price_tariff': [1000, 1300, 900]})
    return profile, tariffs


def fake_env(observation=.3, n=40, contacts=15000, budget=100000):
    p, t = fixture(n)
    env = SimpleNamespace(customer_profile=p, tariffs=t, channels=CHANNELS,
                          remaining_budget=budget, remaining_contacts=contacts, pilots_left=20, pilot_history=[])
    def pilot(target_tariff, channel, n_customers=100, **filters):
        actual = min(n_customers, n, env.remaining_contacts)
        price = CHANNELS[channel]['cost_per_contact']
        if price:
            actual = min(actual, int(env.remaining_budget // price))
        if actual <= 0:
            raise RuntimeError('empty')
        env.remaining_budget -= actual * price
        env.remaining_contacts -= actual
        env.pilots_left -= 1
        value = observation(target_tariff, channel, len(env.pilot_history)) if callable(observation) else observation
        result = dict(n_customers=actual, cost=actual * price, observed_lift_ratio=value)
        env.pilot_history.append(result)
        return result
    env.run_pilot = pilot
    return env


class EngineTests(unittest.TestCase):
    def engine(self, n=40, **kw):
        p,t=fixture(n)
        return Engine(p,t,CHANNELS,100000,15000,history_path=Path('/nonexistent/history.csv'),**kw)

    def set_ratio(self, engine, target, value, variance=.00001):
        for key, state in engine.states.items():
            if key.split('|')[2] == target:
                state.update(mean=value, variance=variance, samples=200)

    def test_precision_uses_actual_n_and_repeated_observations(self):
        m1,v1=normal_update(0,.04,.3,10)
        m2,v2=normal_update(0,.04,.3,200)
        self.assertGreater(m2,m1);self.assertLess(v2,v1)
        a,b=normal_update(m1,v1,-.1,20)
        precision=1/.04+30/.804**2
        self.assertAlmostEqual(a,(.3*10-.1*20)/.804**2/precision)
        self.assertAlmostEqual(b,1/precision)

    def test_negative_best_and_repeated_contact_cost(self):
        e=self.engine();self.set_ratio(e,'b',-.2);self.set_ratio(e,'c',-.4)
        c=e.campaign('a|MID','b','sms')
        f=e.forecast([c,c]);self.assertAlmostEqual(f['gross'],-5200)
        self.assertEqual(f['contacts'],80);self.assertEqual(f['cost'],320)
        self.assertEqual(f['details'][1]['final_overlap'],40)
        self.assertEqual(f['details'][1]['marginal_net'],-160)
        self.assertAlmostEqual(expected_best([(.5,-.2)]),-.1)
        self.assertAlmostEqual(expected_best([(.5,-.2)],-.3),-.25)

    def test_order_money_contact_caps(self):
        e=self.engine(6000);self.set_ratio(e,'b',.2);self.set_ratio(e,'c',.8)
        b=e.campaign('a|MID','b','sms');c=e.campaign('a|MID','c','sms')
        f=e.forecast([b,c],{'budget':24000,'contacts':5500})
        self.assertEqual([d['contacts'] for d in f['details']],[5000,500])
        self.assertEqual(f['cost'],22000);self.assertTrue(f['details'][0]['campaign_capped'])
        g=e.forecast([c,b],{'budget':24000,'contacts':5500})
        self.assertGreater(g['net'],f['net'])
        h=e.forecast([b],{'budget':44});self.assertEqual(h['contacts'],11)

    def test_pilot_overlap_expectation_and_sunk_cost(self):
        e=self.engine();self.set_ratio(e,'b',.4)
        key=e.state_key('a|MID','b','sms')
        e.observe(dict(cell='a|MID',target='b',channel='sms',key=key,requested_n=100),
                  dict(n_customers=10,cost=40,observed_lift_ratio=.26),
                  dict(budget=100000,contacts=15000),dict(budget=99960,contacts=14990))
        f=e.forecast([e.campaign('a|MID','b','sms')])
        self.assertEqual(f['contacts'],50);self.assertEqual(f['cost'],200)
        self.assertAlmostEqual(f['estimated_unique'],40)
        with self.assertRaises(ValueError):e.solve({'budget':39})
        before=json.dumps(e.snapshot(),sort_keys=True)
        e.solve({'budget':100,'channels':['push']})
        self.assertEqual(before,json.dumps(e.snapshot(),sort_keys=True))

    def test_saturation_independent_from_linear_update(self):
        e=self.engine();key=e.state_key('a|MID','b','sms')
        call_before=dict(e.states[e.state_key('a|MID','b','call')])
        e.observe(dict(cell='a|MID',target='b',channel='sms',key=key,requested_n=100),
                  dict(n_customers=40,cost=160,observed_lift_ratio=.4),
                  dict(budget=100000,contacts=15000),dict(budget=99840,contacts=14960))
        self.assertEqual(call_before,e.states[e.state_key('a|MID','b','call')])
        sms=e.estimate('a|MID','b','sms')[0];push=e.estimate('a|MID','b','push')[0]
        self.assertAlmostEqual(sms/push,.65/.5)

    def test_validation_missing_and_small_groups(self):
        e=self.engine(2)
        self.assertTrue(e.validate(dict(target_tariff='b',channel='push',explicit_ids=['x'])))
        self.assertTrue(e.validate(dict(target_tariff='b',channel='push',filter_arpu_segment='FAKE')))
        self.assertTrue(e.validate(dict(target_tariff='a',channel='push')))
        p,t=fixture(4,True);e=Engine(p,t,CHANNELS,100,20,history_path=Path('/absent'))
        self.assertEqual(e.diagnostics['excluded_missing_or_invalid'],1)
        env=fake_env(n=2,contacts=30,budget=10)
        with tempfile.TemporaryDirectory() as d:
            a=Agent(report_path=Path(d)/'r.json');plan=a.act(env)
        self.assertTrue(1<=len(plan)<=10)
        self.assertTrue(all(p['actual_n']<=2 for p in a.engine.log))
        self.assertGreaterEqual(env.remaining_budget,0);self.assertGreaterEqual(env.remaining_contacts,0)

    def test_observations_change_decision_and_new_act_resets(self):
        def run(sign):
            env=fake_env(lambda target,ch,step: sign*(.8 if target=='b' else -.8),n=800)
            originals=env.customer_profile.copy(deep=True)
            with tempfile.TemporaryDirectory() as d:
                a=Agent(report_path=Path(d)/'r.json');plan=a.act(env)
                a.act(fake_env(lambda target,ch,step: sign*(.8 if target=='b' else -.8),n=800))
            pd.testing.assert_frame_equal(env.customer_profile,originals)
            self.assertGreater(len(env.pilot_history),0)
            self.assertEqual(plan,a.plan)
            return plan
        self.assertNotEqual(run(1),run(-1))

    def test_snapshot_replay_and_passports(self):
        e=self.engine();s=e.snapshot();r=Engine.from_snapshot(e.profile,pd.DataFrame({'tariff_plan_code':['a','b','c'],'price_tariff':[1000,1300,900]}),s)
        self.assertEqual(e.solve(),r.solve())
        passports=e.passports(e.solve());self.assertTrue(passports[0]['evidence'])
        self.assertIn('best_rejected_alternative',passports[0])

    def test_audit_and_repair(self):
        e=self.engine();self.set_ratio(e,'b',.6);self.set_ratio(e,'c',-.2)
        c=e.campaign('a|MID','b','sms');bad=[c,c,dict(c,channel='absent')]
        before=e.audit(bad,{'budget':80,'channels':['push']})
        codes={f['code'] for f in before['findings']}
        self.assertTrue({'invalid_campaign','disabled_channel','requested_resources','empty'}<=codes)
        repaired=e.solve({'budget':80,'channels':['push']})
        after=e.audit(repaired,{'budget':80,'channels':['push']})
        self.assertTrue(after['valid']);self.assertFalse(any(f['code']=='overlap' for f in after['findings']))

    def test_no_forbidden_runtime_imports_or_attributes(self):
        tree=ast.parse(Path('agent.py').read_text())
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports += [a.name for a in node.names]
            if isinstance(node,ast.ImportFrom):imports.append(node.module)
            if isinstance(node,ast.Attribute):self.assertNotIn(node.attr,{'__closure__','__dict__','_rng','executed_pilot_campaigns'})
        self.assertFalse(set(imports)&{'mock_environment','scoring_core','local_eval','gc','inspect','requests','httpx'})

if __name__=='__main__':unittest.main()
