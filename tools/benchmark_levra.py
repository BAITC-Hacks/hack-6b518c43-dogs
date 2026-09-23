"""Official evaluator comparisons. Never imported by the agent."""
import json
import statistics
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent import Agent
from agent_template import Agent as Template
from local_eval import evaluate_agent
from backend.server import clean


def summarize(records):
    nets=[r['net_arpu_gain'] for r in records]
    return dict(mean_net=statistics.mean(nets),median_net=statistics.median(nets),
                min_net=min(nets),max_net=max(nets),positive_runs=sum(n>0 for n in nets),
                mean_seconds=statistics.mean(r['seconds'] for r in records),
                max_seconds=max(r['seconds'] for r in records))


def main():
    policies=[]
    for policy in ['template','history_only','fixed_pilots','adaptive']:
        records=[]
        for seed in range(10):
            agent=Template() if policy=='template' else Agent(policy=policy,report_path=ROOT/'reports/levra/benchmark_last_snapshot.json')
            started=time.perf_counter();result=evaluate_agent(agent,seed=seed,verbose=False)
            if result is None:raise RuntimeError(f'No result {policy}/{seed}')
            records.append(dict(seed=seed,seconds=time.perf_counter()-started,**result))
        item=dict(policy=policy,summary=summarize(records),results=records)
        policies.append(item)
        print(policy,json.dumps(item['summary']),flush=True)
    record=dict(source='Official mock',description='Same unchanged official evaluator, seeds 0–9. Noise robustness only, not hidden performance.',policies=policies)
    (ROOT/'reports/levra/comparison.json').write_text(json.dumps(clean(record),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
