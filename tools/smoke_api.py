"""Integration checks against the running local app; no browser mocking."""
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8765'

def request(path,body=None,expected=200):
    data=None if body is None else json.dumps(body).encode()
    req=Request(BASE+path,data=data,headers={'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=90) as response:
            status=response.status;value=json.load(response)
    except HTTPError as error:
        status=error.code;value=json.load(error)
    assert status==expected,(status,value)
    return value

job=request('/api/runs',{'seed':42},202)
for _ in range(300):
    result=request('/api/runs/'+job['run_id'])
    if result['status']=='completed':break
    assert result['status']=='running',result
    time.sleep(.2)
else:raise AssertionError('Run did not complete')
run_id=result['run_id'];path=ROOT/'reports/runs'/f'{run_id}.json'
before=hashlib.sha256(path.read_bytes()).hexdigest()
spent=result['knowledge_summary']['spent_budget'];contacts=result['knowledge_summary']['spent_contacts']
constraints=dict(budget=max(spent,35000),channels=['push','sms'],max_campaigns=4)
scenario=request(f'/api/runs/{run_id}/replan',{'constraints':constraints})
assert scenario['new_pilots']==0
assert scenario['snapshot_id']==result['knowledge_summary']['snapshot_id']
assert scenario['forecast']['cost']<=constraints['budget']
assert scenario['forecast']['cost']>=spent
assert scenario['forecast']['contacts']>=contacts
assert 1<=len(scenario['plan'])<=4
assert all(c['channel'] in constraints['channels'] for c in scenario['plan'])
invalid=request(f'/api/runs/{run_id}/replan',{'constraints':dict(budget=spent-1)},400)
invalid_channels=request(f'/api/runs/{run_id}/replan',{'constraints':dict(channels=[])},400)
bad=result['plan']+[result['plan'][0],dict(result['plan'][0],channel='not-a-channel')]
audit=request(f'/api/runs/{run_id}/audit',{'plan':bad,'constraints':constraints})
assert not audit['valid']
repair=request(f'/api/runs/{run_id}/repair',{'plan':bad,'constraints':constraints})
assert repair['audit']['valid'];assert repair['new_pilots']==0
assert repair['plan']==scenario['plan']
assert before==hashlib.sha256(path.read_bytes()).hexdigest()
report=dict(source='Local API integration',run_id=run_id,official=result['official'],snapshot_id=scenario['snapshot_id'],
            new_pilots_in_what_if=0,snapshot_file_unchanged=True,
            checks=['real run','replay','passports','sunk costs','channel and campaign constraints','below-spent budget rejected',
                    'empty channels rejected','bad plan detected','same-solver repair','no knowledge mutation'],
            scenario_delta=scenario['delta'],audit_before=len(audit['findings']),audit_after=len(repair['audit']['findings']))
(ROOT/'reports/levra/api_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
