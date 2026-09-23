"""Run the unmodified submission script in two genuinely fresh processes."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
results=[]
for seed,key in [('11',False),('937',True)]:
    env=dict(os.environ,PYTHONHASHSEED=seed)
    env.pop('OPENAI_API_KEY',None)
    if key:env['OPENAI_API_KEY']='offline-test-not-a-real-key'
    run=subprocess.run([sys.executable,'make_submission.py'],cwd=ROOT,env=env,capture_output=True,text=True,check=True,timeout=240)
    content=(ROOT/'submission.csv').read_bytes()
    results.append(dict(python_hash_seed=seed,api_key_present=key,sha256=hashlib.sha256(content).hexdigest(),bytes=len(content),stdout=run.stdout))
assert results[0]['sha256']==results[1]['sha256'],'Submission bytes differ across processes'
record=dict(identical=True,processes=results,command=f'{sys.executable} make_submission.py',scope='Fresh processes, seed 42, with/without a dummy API key; no network required')
(ROOT/'reports/levra/reproducibility.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print(json.dumps(record,ensure_ascii=False,indent=2))
