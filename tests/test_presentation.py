"""Presentation facts must not invent certainty or mutate the research record."""
import copy,unittest
from backend.presentation import activity,evidence_summary

class PresentationTests(unittest.TestCase):
    def test_grade_cannot_hide_unobserved_or_zero_crossing_groups(self):
        evidence=[dict(samples=220,pilots=2,interval=[.1,.4],prior={'n_history':7})]
        passport=dict(evidence=evidence,pilots=[1,2])
        pilots=[dict(index=1,actual_n=100,requested_n=200),dict(index=2,actual_n=120,requested_n=200)]
        before=copy.deepcopy((passport,pilots))
        result=evidence_summary(passport,pilots)
        self.assertEqual(result['level'],'strong')
        self.assertEqual(result['sample_size'],220)
        self.assertEqual(result['pilot_count'],2)
        self.assertEqual((passport,pilots),before)
        evidence.append(dict(samples=0,pilots=0,interval=[.1,.4],prior={'n_history':30}))
        self.assertEqual(evidence_summary(passport,pilots)['level'],'limited')
        evidence.pop();evidence[0]['interval']=[-.1,.4]
        self.assertEqual(evidence_summary(passport,pilots)['level'],'limited')
        evidence[0].update(interval=[.1,.4],pilots=1)
        self.assertEqual(evidence_summary(passport,pilots)['level'],'moderate')

    def test_hypotheses_do_not_double_count_channel_models_or_fake_missing_trace(self):
        snapshot=dict(states={
            'tariff_1|LOW|tariff_2|linear':{'prior':{'n_history':5}},
            'tariff_1|LOW|tariff_2|call':{'prior':{'n_history':5}},
            'tariff_2|LOW|tariff_1|linear':{'prior':{'n_history':0}}},
            pilots=[dict(index=1),dict(index=2,repeat_validation=True,decision_change={'selection_changed':True})],
            total_budget=100000,total_contacts=15000,spent_budget=400,spent_contacts=2995,
            stop_reason='Ожидаемая ценность информации не покрывает расход ресурсов')
        before=copy.deepcopy(snapshot);result=activity(snapshot)
        self.assertEqual((result['hypotheses'],result['direct_history_hypotheses']),(2,1))
        self.assertEqual((result['changed_decisions'],result['traced_pilots'],result['material_repeats']),(1,1,1))
        self.assertIn('контактный резерв',result['stop_reason'])
        self.assertEqual(snapshot,before)

if __name__=='__main__':unittest.main()
