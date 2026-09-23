"""Inspect saved, post-return public forecasts and evaluator results. No new training."""
import json
import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent import Engine

def main():
    records=[json.loads(p.read_text()) for p in (ROOT/'reports/runs').glob('*.json') if not p.name.endswith('.knowledge.json')]
    record=max((r for r in records if r.get('identity') and r['seed']==42),key=lambda r:r['created_at'])
    engine=Engine.from_snapshot(pd.read_csv(ROOT/'customer_profile.csv'),pd.read_csv(ROOT/'data/dict_tariff.csv'),record['knowledge'])
    plan=record['plan'];forecast=engine.forecast(plan);passports=engine.passports(plan)
    measured=dict(measured_details=record['official']['campaigns_detail'],measured_net=record['official']['net_arpu_gain'],measured_unique=record['official']['unique_customers_targeted'])
    (ROOT/'reports/stage3/decision_trace.json').write_text(json.dumps(dict(run_id=record['run_id'],identity=record['identity'],pilots=engine.log,plan=plan),ensure_ascii=False,indent=2))
    final=measured['measured_details'][-len(plan):];rows=[]
    for i,(detail,actual,passport) in enumerate(zip(forecast['details'],final,passports)):
        ids=engine.audience(plan[i])[:detail['contacts']];weighted=0.;unpiloted=0;unsupported=0
        cells=[]
        for cell in sorted(set(engine.cell_keys[ids])):
            if not cell:continue
            selected=ids[engine.cell_keys[ids]==cell];arpu=float(engine.arpu[selected].sum())
            state=engine.states[engine.state_key(cell,plan[i]['target_tariff'],plan[i]['channel'])]
            mean,sd=engine.estimate(cell,plan[i]['target_tariff'],plan[i]['channel'])
            weighted+=arpu*mean
            if not state['samples']:unpiloted+=len(selected)
            if not state['prior']['n_history']:unsupported+=len(selected)
            cells.append(dict(cell=cell,contacts=len(selected),arpu_sum=arpu,mean=mean,sd=sd,
                pilot_contacts=state['samples'],historical_rows=state['prior']['n_history']))
        assert detail['contacts']==actual['n_contacts'] and detail['cost']==actual['cost']
        rows.append(dict(index=i+1,contacts=detail['contacts'],cost=detail['cost'],
            forecast_gross_before_overlap=weighted,measured_gross_before_overlap=actual['gross_lift'],
            forecast_marginal_net=detail['marginal_net'],unpiloted_contacts=unpiloted,
            contacts_without_direct_history=unsupported,cells=cells))
    pilot_net=engine.forecast([])['net']
    assert abs(pilot_net+sum(d['marginal_net'] for d in forecast['details'])-forecast['net'])<1e-6
    report=dict(run_id=record['run_id'],identity=record['identity'],source='Диагностика сохранённого прогона 42 после возврата плана',
        forecast_net=forecast['net'],measured_net=measured['measured_net'],
        forecast_error=forecast['net']-measured['measured_net'],
        relative_error=(forecast['net']-measured['measured_net'])/abs(measured['measured_net']),
        pilot_forecast_net=pilot_net,pilot_cost=engine.spent_budget,pilot_contacts=engine.spent_contacts,
        final_contacts=sum(d['contacts'] for d in forecast['details']),
        forecast_unique=forecast['estimated_unique'],measured_unique=measured['measured_unique'],
        cost_and_contacts_exact_for_every_final_campaign=True,rows=rows)
    (ROOT/'reports/stage3/forecast_diagnosis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
