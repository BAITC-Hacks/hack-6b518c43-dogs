"""Evaluate the ORIGINAL participant template, never the team's replacement Agent.
This is an offline test driver, not part of the submitted agent's execution.
"""
from __future__ import annotations
import contextlib, importlib.metadata, io, json, statistics, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent_template import Agent
from local_eval import evaluate_agent

def main():
    results=[]
    for seed in [42,*range(10)]:
        capture=io.StringIO();started=time.perf_counter()
        with contextlib.redirect_stdout(capture):
            result=evaluate_agent(Agent(),seed=seed,verbose=False)
        if result is None:raise RuntimeError(f'No result for seed {seed}')
        results.append(dict(seed=seed,seconds=time.perf_counter()-started,**result))
    nets=[r['net_arpu_gain'] for r in results if r['seed']!=42]
    record={'scope':'ORIGINAL agent_template.py on PROVIDED mock; not LEVRA and not hidden evaluation',
        'python':sys.version,'dependencies':{p:importlib.metadata.version(p) for p in ('numpy','pandas')},
        'ten_seed_summary':{'seeds':list(range(10)),'mean_net':statistics.mean(nets),'median_net':statistics.median(nets),'min_net':min(nets),'max_net':max(nets),'positive_runs':sum(n>0 for n in nets)},'results':results}
    (ROOT/'reports/baseline_benchmark.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(record['ten_seed_summary'],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
