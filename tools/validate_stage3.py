"""Preregistered comparison; truth exists only in external scoring harnesses."""
import argparse,hashlib,json,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.stage3_variants import POLICIES
from tools.stage3_worlds import world
from local_eval import evaluate_agent
OUT=ROOT/'reports/stage3'

def summary(rows):
    values=[r['net'] for r in rows if r.get('net') is not None]
    return dict(n=len(rows),median=float(np.median(values)) if values else None,minimum=min(values) if values else None,
        negative_fraction=sum(v<0 for v in values)/len(values) if values else None,
        mean_absolute_error=float(np.mean([abs(r['forecast_net']-r['net']) for r in rows if r.get('net') is not None])),
        mean_forecast_error=float(np.mean([r['forecast_net']-r['net'] for r in rows if r.get('net') is not None])),
        mean_pilot_cost=float(np.mean([r.get('pilot_cost',0) for r in rows])),
        mean_pilot_contacts=float(np.mean([r.get('pilot_contacts',0) for r in rows])),
        mean_pilot_count=float(np.mean([r.get('pilot_count',0) for r in rows])),
        mean_seconds=float(np.mean([r['seconds'] for r in rows])),max_seconds=max(r['seconds'] for r in rows),
        violations=sum(bool(r['violations']) for r in rows))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--split',choices=['development','heldout'],required=True);args=parser.parse_args()
    out=OUT/(args.split+'.jsonl')
    if out.exists():raise SystemExit('Preserving existing outcomes: choose an explicit new report for a rerun.')
    heldout=args.split=='heldout';rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        history=Path(tmp)/'history.csv'
        pd.DataFrame([dict(ID_NUMBER=f'historical_{i}',AVG_ARPU_PREV_3M=2500 if i%2 else 6000,
            AVG_ARPU_NEXT_3M=(2500 if i%2 else 6000)*1.8,tariff_plan_code_from='a' if i<80 else 'b',tariff_plan_code_to='c')
            for i in range(160)]).to_csv(history,index=False)
        jobs=[('official',s) for s in (range(100,110) if heldout else range(5))]
        jobs += [(family,s) for family in ['history_correct','shifted','weakened','adverse'] for s in (range(160,165) if heldout else range(60,63))]
        for family,seed in jobs:
            for policy,factory in POLICIES.items():
                start=time.perf_counter();row=dict(split=args.split,family=family,seed=seed,policy=policy,violations=[])
                try:
                    agent=factory(report_path=Path(tmp)/'knowledge.json',history_path=None if family=='official' else history)
                    if family=='official':
                        result=evaluate_agent(agent,seed=seed,verbose=False)
                        measured=dict(net=result['net_arpu_gain'],cost=result['total_cost'],contacts=result['total_contacts'])
                    else:
                        env,score=world(family,seed,heldout);plan=agent.act(env);measured=score(plan)
                    forecast=agent.engine.forecast(agent.plan)
                    row.update(net=measured['net'],forecast_net=forecast['net'],cost=measured['cost'],contacts=measured['contacts'],
                        pilot_cost=agent.snapshot['spent_budget'],pilot_contacts=agent.snapshot['spent_contacts'],
                        pilot_count=len(agent.snapshot['pilots']),plan=agent.plan,
                        repeat_count=sum(p.get('repeat_validation',False) for p in agent.snapshot['pilots']))
                    if not 1<=len(agent.plan)<=10:row['violations'].append('plan length')
                    if forecast['cost']!=measured['cost'] or forecast['contacts']!=measured['contacts']:row['violations'].append('resource mismatch')
                    if any(agent.engine.validate(c) for c in agent.plan):row['violations'].append('invalid campaign')
                    if row['pilot_count']<1 or row['pilot_count']>20:row['violations'].append('pilot count')
                    if row['cost']>agent.engine.total_budget or row['contacts']>agent.engine.total_contacts:row['violations'].append('resource cap')
                except Exception as error:row.update(net=None,error=f'{type(error).__name__}: {error}');row['violations'].append('exception')
                row['seconds']=time.perf_counter()-start
                if row['seconds']>=240:row['violations'].append('runtime')
                with out.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
                rows.append(row);print(args.split,family,seed,policy,round(row['net']) if row['net'] is not None else row['error'],round(row['seconds'],2),flush=True)
    report=dict(protocol='docs/STAGE3_VALIDATION_PROTOCOL.md',completed_at=datetime.now(timezone.utc).isoformat(),
        variant_sha256=hashlib.sha256((ROOT/'tools/stage3_variants.py').read_bytes()).hexdigest(),
        groups={f'{family}/{policy}':summary([r for r in rows if r['family']==family and r['policy']==policy]) for family in sorted({r['family'] for r in rows}) for policy in POLICIES},results=rows)
    (OUT/(args.split+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
