"""Install an isolated copy with empty package caches and no credentials.

Explicit invocation downloads pinned dependencies from PyPI/npm; never invokes OpenAI.
"""
import hashlib,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    report={'scope':'Fresh Python venv and npm ci, empty HOME/cache, copied current source, no API key','checks':[]}
    root=Path(tempfile.mkdtemp(prefix='beeagent-clean-'));app=root/'app';app.mkdir();(root/'home').mkdir()
    report['temporary_directory']=str(root)
    files=['agent.py','agent_template.py','environment.py','mock_environment.py','scoring_core.py','local_eval.py','make_submission.py','customer_profile.csv','tariff_dictionary.csv','feature_dictionary.csv','requirements.txt','requirements-server.txt','run.sh']
    for name in files:shutil.copy2(ROOT/name,app/name)
    for name in ['backend','data','frontend','tests']:
        shutil.copytree(ROOT/name,app/name,ignore=shutil.ignore_patterns('__pycache__','node_modules','dist','.env*'))
    (app/'docs').mkdir();shutil.copy2(ROOT/'docs/ORIGINAL_MANIFEST.json',app/'docs/ORIGINAL_MANIFEST.json')
    # Verifier also protects organizer docs: include exactly the manifest's paths.
    manifest=json.loads((ROOT/'docs/ORIGINAL_MANIFEST.json').read_text())
    paths=manifest.get('files',manifest)
    for name in paths:
        src=ROOT/name
        if src.is_file():dst=app/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    (app/'tools').mkdir();shutil.copy2(ROOT/'tools/verify_originals.py',app/'tools/verify_originals.py')
    env={k:v for k,v in os.environ.items() if not k.startswith(('OPENAI','BEEAGENT','PYTHON','PIP','NPM','npm_'))}
    env.update(HOME=str(root/'home'),PIP_CONFIG_FILE=os.devnull,PIP_NO_CACHE_DIR='1',PYTHONNOUSERSITE='1',npm_config_cache=str(root/'npm-cache'))
    def run(command,label,timeout=240):
        start=time.perf_counter();result=subprocess.run(command,cwd=app,env=env,capture_output=True,text=True,timeout=timeout)
        report['checks'].append(dict(label=label,exit_code=result.returncode,seconds=time.perf_counter()-start,output=result.stdout[-5000:]+result.stderr[-2000:]))
        (ROOT/'reports/stage3/clean_install.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(label,result.returncode,flush=True)
        if result.returncode:raise RuntimeError(label+' failed')
    try:
        run([sys.executable,'-m','venv',str(app/'.venv')],'create venv')
        python=str(app/'.venv/bin/python')
        run([python,'-m','pip','install','--no-cache-dir','--index-url','https://pypi.org/simple','-r','requirements.txt','-r','requirements-server.txt'],'install Python from registry')
        run(['npm','ci','--prefix','frontend','--no-audit','--no-fund'],'npm clean install')
        run(['npm','--prefix','frontend','run','build'],'frontend build')
        run([python,'local_eval.py'],'official evaluation')
        run([python,'make_submission.py'],'submission')
        report['submission_sha256']=hashlib.sha256((app/'submission.csv').read_bytes()).hexdigest()
        assert report['submission_sha256']==hashlib.sha256((ROOT/'submission.csv').read_bytes()).hexdigest()
        run([python,'tools/verify_originals.py'],'originals')
        run([python,'-m','unittest','discover','-s','tests','-v'],'unit tests without key')
        # Real local HTTP on the clean installation: no inherited storage/credentials.
        server=subprocess.Popen([python,'-m','backend.server','--port','8767'],cwd=app,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            from urllib.request import Request,urlopen
            def api(path,body=None):
                with urlopen(Request('http://127.0.0.1:8767'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=30) as response:return json.load(response)
            for _ in range(100):
                try:status=api('/api/assistant/status');break
                except OSError:time.sleep(.1)
            assert not status['available'] and status['calls']==0
            rid=api('/api/runs',{'seed':42})['run_id']
            for _ in range(240):
                current=api('/api/runs/'+rid)
                if current['status']=='completed':break
                if current['status']=='failed':raise RuntimeError('clean run failed')
                time.sleep(.1)
            assert current['measurement'] is not None
            variant=api('/api/runs/'+rid+'/replan',{'base_plan_id':rid,'constraints':{'budget':70000,'channels':['push','sms','digital_ads'],'max_campaigns':5}})
            assert variant['measurement'] is None and variant['new_pilots']==0
            assert api('/api/runs/'+rid)['active_bundle']['plan_id']==rid
            report['clean_http']=dict(original_measured=True,variant_unmeasured=True,no_new_pilots=True,no_implicit_apply=True,ai_available=False,ai_calls=0)
        finally:server.terminate();server.wait(timeout=10)
        report['passed']=True
    except Exception as error:report.update(passed=False,error=type(error).__name__+': '+str(error))
    (ROOT/'reports/stage3/clean_install.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))
if __name__=='__main__':main()
