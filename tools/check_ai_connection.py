"""Safe local configuration check. External calls require --paid-smoke explicitly.

Use the running app's HTTP endpoints, immutable plans and persistent spending ledger.
Never read conversation credentials or print environment values.
"""
import argparse,json,os,sys,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
PROMPTS=[
    'Сократи бюджет на 30%, исключи звонки и оставь максимум пять кампаний',
    'Почему для выбранной кампании используется SMS, а не звонок?',
    'Какие решения в плане опираются на наиболее слабые данные?',
    'От исходного лимита оставь семь десятых, убери телефонные контакты и выбери не более пяти кампаний.',
    'Объясни, почему выбранному сегменту отправляем сообщение вместо того, чтобы позвонить.',
    'Где в этом плане больше всего непроверенных предположений и какой выбор стоит перепроверить?']

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--paid-smoke',action='store_true')
    parser.add_argument('--url',default='http://127.0.0.1:8765');parser.add_argument('--run-id')
    parser.add_argument('--output',default=str(ROOT/'reports/stage3/ai_integration.json'));args=parser.parse_args()
    if urlparse(args.url).hostname not in ['127.0.0.1','localhost']:raise SystemExit('Only the local BeeAgent server is accepted.')
    report=dict(checked_at=datetime.now(timezone.utc).isoformat(),model=os.getenv('OPENAI_MODEL','gpt-6-sol'),
        local_key_configured=bool(os.getenv('OPENAI_API_KEY','').strip()),paid_smoke_requested=args.paid_smoke,
        network_call=False,additional_estimated_budget_usd=3,actions=[],status='not_run')
    def api(path,body=None):
        request=Request(args.url+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=60) as response:return json.load(response)
    try:
        status=api('/api/assistant/status');report['server_status']=status
        if not args.paid_smoke:report['blocker']=('New local OPENAI_API_KEY is absent; no external call. After local setup use --paid-smoke explicitly.' if not status.get('key_configured') else 'Server model/pricing/limit configuration is invalid; no external call.') if not status['available'] else 'Paid smoke requires explicit --paid-smoke; configuration check made no OpenAI request.'
        elif not status['available']:report['blocker']='New local OPENAI_API_KEY is not configured in the running server.' if not status.get('key_configured') else 'Server model/pricing/limit configuration is invalid.'
        else:
            # Existing ledger is not reset. Cumulative limit <= existing spend + $3.
            if status['limit_usd']-status['estimated_usd']>3.000001:
                raise ValueError('Set server BEEAGENT_AI_BUDGET_USD to at most existing estimated_usd + 3, then restart; preserve ledger.')
            runs=api('/api/runs');rid=args.run_id or (runs[0]['run_id'] if runs else None)
            if not rid:raise ValueError('Create a measured plan in the app first.')
            original=api('/api/runs/'+rid);base=original['plan_id']
            if original.get('archived'):raise ValueError('Create a current-version plan before the AI smoke.')
            index=next((i for i,c in enumerate(original['plan']) if c['channel']=='sms'),0)
            before_active=original['active_bundle']['plan_id']
            for prompt_number,prompt in enumerate(PROMPTS):
                started=time.perf_counter();job=api('/api/assistant',dict(run_id=rid,base_plan_id=base,prompt=prompt,campaign_index=index))
                while True:
                    data=api('/api/assistant/jobs/'+job['job_id'])
                    if data['status']!='running':break
                    time.sleep(.4)
                result=data['result'];proposal=result.get('proposal')
                required_tool=['propose_scenario','get_campaign_evidence','get_plan_summary'][prompt_number%3]
                validation_errors=[]
                if result['status']=='completed' and required_tool not in [t['tool'] for t in result.get('tool_trace',[])]:
                    validation_errors.append('Required real tool was not executed: '+required_tool)
                if result['status']=='completed' and required_tool=='propose_scenario' and not proposal:
                    validation_errors.append('No scenario version was created')
                report['actions'].append(dict(prompt=prompt,run_id=rid,base_plan_id=base,status=result['status'],
                    reason=result.get('reason'),network_call=result.get('network_call',False),network_attempts=result.get('network_attempts',0),cached=result.get('cached',False),
                    tool_trace=result.get('tool_trace',[]),usage=result.get('usage'),seconds=time.perf_counter()-started,
                    required_tool=required_tool,validation_errors=validation_errors,
                    proposed_plan_id=proposal['plan_id'] if proposal else None,
                    proposed_constraints=proposal['forecast']['constraints'] if proposal else None))
                report['network_call']|=result.get('network_call',False)
                current=api('/api/runs/'+rid)
                assert current['plan']==original['plan'] and current['pilots']==original['pilots']
                assert current['active_bundle']['plan_id']==before_active
                if proposal:
                    assert proposal['new_pilots']==0 and proposal['measurement'] is None
                    assert proposal['forecast']['constraints']['budget']==original['forecast']['constraints']['budget']*.7
                    assert 'call' not in proposal['forecast']['constraints']['channels']
                    assert proposal['forecast']['constraints']['max_campaigns']==5
                if result.get('reason') in ['authentication','permission','model_unavailable','spend_limit']:break
            report['after']=api('/api/assistant/status')
            report['status']='passed' if len(report['actions'])==6 and all(a['status']=='completed' and not a['validation_errors'] for a in report['actions']) else 'incomplete'
            report['explicit_application']='Not automatic: proposals remain pending for the UI apply button.'
    except Exception as error:
        report['status']='not_run' if not report['network_call'] else 'incomplete'
        # Do not include raw HTTP/SDK errors or credentials in reports.
        report['blocker']=str(error) if type(error) is ValueError else type(error).__name__
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and json.loads(path.read_text()).get('network_call'):
        path=path.with_name(path.stem+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+path.suffix)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
