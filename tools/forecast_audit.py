"""Post-return diagnostics only. No evaluator result is fed back to Agent."""
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent import Agent
from local_eval import evaluate_agent
from tools.stress_levra import world

def summarize(rows):
    values=[r['measured_net'] for r in rows]
    return dict(n=len(rows),median=float(np.median(values)),minimum=min(values),
        lower_decile=float(np.quantile(values,.1)) if len(rows)>=10 else None,
        positive_fraction=sum(v>0 for v in values)/len(values),
        mean_pilot_cost=float(np.mean([r['pilot_cost'] for r in rows])),
        mean_seconds=float(np.mean([r['seconds'] for r in rows])),
        mean_forecast_error=float(np.mean([r['forecast_net']-r['measured_net'] for r in rows])),
        mean_absolute_error=float(np.mean([abs(r['forecast_net']-r['measured_net']) for r in rows])))

def main():
    rows=[]
    with tempfile.TemporaryDirectory() as d:
        for seed in [*range(20),42]:
            agent=Agent(report_path=Path(d)/'snapshot.json')
            start=time.perf_counter();result=evaluate_agent(agent,seed=seed,verbose=False)
            forecast=agent.engine.forecast(agent.plan)
            rows.append(dict(source='Проверка на данных кейса',split='heldout' if 10<=seed<20 else 'previous',
                seed=seed,measured_net=result['net_arpu_gain'],forecast_net=forecast['net'],
                forecast_cost=forecast['cost'],measured_cost=result['total_cost'],
                forecast_contacts=forecast['contacts'],measured_contacts=result['total_contacts'],
                estimated_unique=forecast['estimated_unique'],measured_unique=result['unique_customers_targeted'],
                pilot_cost=agent.snapshot['spent_budget'],pilot_contacts=agent.snapshot['spent_contacts'],
                pilot_count=len(agent.snapshot['pilots']),seconds=time.perf_counter()-start,
                forecast_details=forecast['details'],measured_details=result.get('campaigns_detail',[])))
            assert forecast['cost']==result['total_cost']
            assert forecast['contacts']==result['total_contacts']
            print('case',seed,round(forecast['net']),round(result['net_arpu_gain']),flush=True)
        history=Path(d)/'history.csv'
        pd.DataFrame([dict(ID_NUMBER=f'historical_{i}',AVG_ARPU_PREV_3M=2500 if i%2 else 6000,
            AVG_ARPU_NEXT_3M=7500 if i%2 else 18000,tariff_plan_code_from='a' if i<80 else 'b',tariff_plan_code_to='c')
            for i in range(160)]).to_csv(history,index=False)
        for scenario in ['stage2_magnitude','stage2_negative_shift','stage2_best_switch','adverse_first_pilots']:
            for seed in [50,51,52]:
                env,score=world(scenario,seed)
                agent=Agent(history_path=history,report_path=Path(d)/'snapshot.json')
                start=time.perf_counter();plan=agent.act(env);measured=score(plan)
                forecast=agent.engine.forecast(plan)
                rows.append(dict(source='Авторская проверка устойчивости',split=scenario,seed=seed,
                    measured_net=measured['net'],forecast_net=forecast['net'],pilot_cost=agent.snapshot['spent_budget'],
                    pilot_count=len(agent.snapshot['pilots']),seconds=time.perf_counter()-start))
                print(scenario,seed,round(forecast['net']),round(measured['net']),flush=True)
    report=dict(protocol='docs/STAGE2_VALIDATION_PROTOCOL.md',agent_sha256=hashlib.sha256((ROOT/'agent.py').read_bytes()).hexdigest(),
        groups={g:summarize([r for r in rows if r['split']==g]) for g in sorted({r['split'] for r in rows})},results=rows)
    (ROOT/'reports/stage2/forecast_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
