"""Real HTTP integration, no external AI calls and no fake UI data."""
import csv
import hashlib
import io
import json
import time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8765'
def request(path,body=None,expected=200,extra_headers=None):
    req=Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type':'application/json',**(extra_headers or {})})
    try:
        with urlopen(req,timeout=60) as response:status=response.status;value=json.load(response)
    except HTTPError as error:status=error.code;value=json.load(error)
    assert status==expected,(status,value)
    return value
def main():
    runs=request('/api/runs');run=request('/api/runs/'+runs[0]['run_id']);rid=run['run_id']
    baseline=request(f'/api/runs/{rid}/plans/{rid}')
    record=ROOT/'reports/runs'/f'{rid}.json';before=hashlib.sha256(record.read_bytes()).hexdigest()
    status=request('/api/assistant/status');calls=status['calls']
    assert not status['available'],'This no-API test expects no local API key'
    result=request('/api/assistant',dict(run_id=rid,base_plan_id=rid,prompt='Сократи бюджет на 30%, исключи звонки, максимум пять'),202)
    for _ in range(80):
        job=request('/api/assistant/jobs/'+result['job_id'])
        if job['status']=='completed':break
        time.sleep(.1)
    assert job['result']['reason']=='missing_key'
    assert request('/api/assistant/status')['calls']==calls
    limits={**baseline['forecast']['constraints'],'budget':baseline['forecast']['constraints']['budget']*.7,
        'channels':[ch for ch in baseline['forecast']['constraints']['channels'] if ch!='call'],'max_campaigns':5}
    proposal=request(f'/api/runs/{rid}/replan',dict(base_plan_id=rid,constraints=limits))
    unchanged=request('/api/runs/'+rid)
    assert unchanged['active_bundle']['plan_id']==run['active_bundle']['plan_id']
    assert baseline['measurement'] is not None and not baseline['archived']
    assert baseline['measurement_binding']['run_id']==rid
    assert proposal['identity']==baseline['identity']
    second=request(f'/api/runs/{rid}/replan',dict(base_plan_id=rid,constraints=limits))
    assert second['plan']==proposal['plan'] and second['forecast']==proposal['forecast']
    assert proposal['measurement'] is None and proposal['new_pilots']==0
    assert proposal['forecast']['constraints']['budget']==70000
    assert proposal['forecast']['cost']>=run['knowledge_summary']['spent_budget']
    comparison=request(f'/api/runs/{rid}/compare',dict(base_plan_id=rid,proposed_plan_id=proposal['plan_id']))
    assert comparison['delta']['net']==proposal['forecast']['net']-baseline['forecast']['net']
    applied=request(f'/api/runs/{rid}/apply',dict(plan_id=proposal['plan_id'],expected_active_plan_id=run['active_bundle']['plan_id']))
    assert applied['plan_id']==proposal['plan_id']
    assert request('/api/runs/'+rid)['active_bundle']['plan_id']==proposal['plan_id']
    request(f'/api/runs/{rid}/apply',dict(plan_id=rid,expected_active_plan_id=rid),400)
    saved=request(f'/api/runs/{rid}/save',dict(plan_id=proposal['plan_id']));assert saved['saved']
    with urlopen(BASE+f'/api/runs/{rid}/plans/{proposal["plan_id"]}/export') as response:csv_bytes=response.read()
    rows=list(csv.DictReader(io.StringIO(csv_bytes.decode())))
    assert len(rows)==len(proposal['plan'])
    for row,campaign in zip(rows,proposal['plan']):
        assert all(row[k]==str(campaign.get(k,'')) for k in row)
    request(f'/api/runs/{rid}/replan',dict(base_plan_id=rid,constraints={'budget':1}),400)
    request('/api/assistant',dict(run_id=rid,base_plan_id=rid,prompt='x'*2001),400)
    request('/api/assistant',dict(run_id=rid,base_plan_id=rid,prompt='x',api_key='not-a-key'),400)
    request('/api/runs',{'seed':42},403,{'Origin':'https://example.invalid'})
    request('/api/runs',None,403,{'Host':'untrusted.example'})
    request(f'/api/runs/{rid}/apply',dict(plan_id=rid,expected_active_plan_id=proposal['plan_id']))
    assert before==hashlib.sha256(record.read_bytes()).hexdigest()
    report=dict(source='Реальная локальная HTTP-проверка',external_ai_tested=False,run_id=rid,
        proposal_id=proposal['plan_id'],new_pilots=0,original_unchanged=True,export_rows=len(rows),
        forecast=proposal['forecast']['net'],measured_result=None,ai_calls_added=0,
        checks=['Привязка измерения к версии и данным','Повтор пересчёта от той же базы без накопления сокращения','Отсутствующий ключ','Ручной пересчёт','Отдельное предложение','База сравнения','Явное применение',
            'Сохранение и восстановление версии','Отклонение устаревшего применения','CSV соответствует версии',
            'Потраченные ресурсы сохранены','Лимит ниже потраченного отклонён','Чужой Origin и Host отклонены','Размер и поля запроса проверены'])
    (ROOT/'reports/stage3/api_stage3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
