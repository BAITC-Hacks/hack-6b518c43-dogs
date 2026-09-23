"""One public, offline verification path. Never reads environment/scorer internals."""
import argparse,csv,hashlib,io,json,os,re,statistics,subprocess,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='reports/stage4/verification.json')
    args=parser.parse_args();destination=ROOT/args.output;destination.parent.mkdir(parents=True,exist_ok=True)
    report=dict(started_at=datetime.now(timezone.utc).isoformat(),checks=[],passed=False,
                source='Unmodified official public scripts',network_disabled=True)
    env={k:v for k,v in os.environ.items() if not k.startswith('OPENAI_')}
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='beeagent-offline-') as directory:
        Path(directory,'sitecustomize.py').write_text(
            'import socket\n'
            'def denied(*args, **kwargs): raise RuntimeError("Network disabled for contest verification")\n'
            'socket.socket.connect=denied\nsocket.socket.connect_ex=denied\nsocket.create_connection=denied\n')
        env['PYTHONPATH']=directory+os.pathsep+str(ROOT)
        def run(command,label,override=None,timeout=240):
            now=time.perf_counter()
            result=subprocess.run([sys.executable,*command],cwd=ROOT,env={**env,**(override or {})},
                                  capture_output=True,text=True,timeout=timeout)
            log=destination.parent/(label+'.log');log.write_text(result.stdout+result.stderr)
            report['checks'].append(dict(name=label,seconds=time.perf_counter()-now,exit_code=result.returncode,log=str(log.relative_to(ROOT))))
            destination.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            if result.returncode:raise ValueError(label+' failed; see '+str(log))
            print('OK '+label,flush=True)
            return result.stdout
        try:
            run(['tools/verify_originals.py'],'originals')
            run(['-c','import agent; assert callable(agent.Agent().act)'],'agent_import')
            one=run(['local_eval.py'],'local_eval')
            assert 'Статус: PASS' in one and 'отброшена' not in one
            contacts=int(re.search(r'контактов:\s*([\d,]+)',one)[1].replace(',',''))
            cost=int(re.search(r'Затраты на коммуникацию:\s*([\d,]+)',one)[1].replace(',',''))
            pilots=int(re.search(r'Пилотов проведено:\s*(\d+)',one)[1])
            assert contacts<=15000 and cost<=100000 and 0<pilots<=20
            report['official_resources']=dict(contacts=contacts,cost=cost,pilots=pilots,within_case_limits=True)
            report['official_seed42_net_rounded']=int(re.search(r'ЧИСТЫЙ РЕЗУЛЬТАТ \(net\):\s*([\d,]+)',one)[1].replace(',',''))
            ten=run(['local_eval.py','--runs','10'],'local_eval_10',timeout=300)
            outcomes=[dict(seed=int(s),net_rounded=int(n.replace(',',''))) for s,n in re.findall(r'seed\s+(\d+):\s*чистый результат\s+(-?[\d,]+)',ten)]
            assert len(outcomes)==10 and {r['seed'] for r in outcomes}==set(range(10))
            values=[r['net_rounded'] for r in outcomes]
            report['stability']=dict(outcomes=outcomes,median=statistics.median(values),minimum=min(values),
                                     maximum=max(values),positive=sum(x>0 for x in values),precision='Rounded official console values')
            samples=[]
            for hashseed,key in [('11',''),('937','offline-test-not-a-real-key')]:
                run(['make_submission.py'],'submission_'+hashseed,dict(PYTHONHASHSEED=hashseed,OPENAI_API_KEY=key))
                content=(ROOT/'submission.csv').read_bytes();rows=list(csv.DictReader(io.StringIO(content.decode())))
                samples.append(dict(hash_seed=hashseed,dummy_api_key_present=bool(key),sha256=hashlib.sha256(content).hexdigest(),content=content,rows=rows))
            assert samples[0]['content']==samples[1]['content'] and samples[0]['rows']==samples[1]['rows']
            rows=samples[0]['rows'];assert 1<=len(rows)<=10
            with (ROOT/'data/dict_tariff.csv').open() as f:tariffs={r['tariff_plan_code'] for r in csv.DictReader(f)}
            allowed={'push','sms','digital_ads','call'}
            required={'campaign_name','target_tariff','channel'}
            optional={'filter_arpu_segment','filter_data_segment','filter_call_segment','filter_current_tariff'}
            for r in rows:
                assert required<=r.keys() and set(r)<=required|optional
                assert r['target_tariff'] in tariffs and r['channel'] in allowed
                assert all(t in tariffs for t in r.get('filter_current_tariff','').split(';') if t)
            report.update(submission_sha256=samples[0]['sha256'],campaign_count=len(rows),byte_identical=True,content_identical=True,
                          fresh_processes=[{k:v for k,v in s.items() if k not in ['content','rows']} for s in samples],
                          no_api_dependency=True,valid_tariffs_channels=True)
            baseline=ROOT/'reports/stage4/baseline.json'
            if baseline.exists():
                expected=json.loads(baseline.read_text())['sha256']
                report['stage3_policy_unchanged']=hashlib.sha256((ROOT/'agent.py').read_bytes()).hexdigest()==expected['agent.py']
                report['stage3_submission_unchanged']=report['submission_sha256']==expected['submission.csv']
            run(['tools/verify_originals.py'],'originals_after')
            report['passed']=True
        except Exception as error:report['error']=str(error)
        report['seconds']=time.perf_counter()-started
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['passed']:print('FAIL: '+report.get('error','unknown'));raise SystemExit(1)
    print('PASS: seed 42 '+str(report['official_seed42_net_rounded'])+'; 10 seeds median '+str(report['stability']['median'])+
          ', min '+str(report['stability']['minimum'])+', positive '+str(report['stability']['positive'])+'/10')
    print('Submission: '+str(report['campaign_count'])+' valid campaigns, identical fresh-process bytes; network blocked.')
    print('SHA256 '+report['submission_sha256']+'\nReport: '+str(destination))
if __name__=='__main__':main()
