"""Local-only API and static UI. Official scoring is delegated unchanged to local_eval."""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
import mimetypes
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from agent import Agent, Engine
from local_eval import evaluate_agent
from dotenv import load_dotenv
load_dotenv(ROOT/'.env', override=False)
from backend.plans import PlanService
from backend.assistant import Assistant

RUNS = Path(os.getenv('BEEAGENT_STORAGE_DIR',str(ROOT/'reports/runs'))).resolve()
RUNS.mkdir(parents=True, exist_ok=True)
JOBS = {}
LOCK = threading.Lock()
AI_JOBS = {}


def clean(value):
    if isinstance(value, dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):return [clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):return None
    if hasattr(value, 'item'):return clean(value.item())
    return value


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(clean(data), ensure_ascii=False, indent=2))
    temporary.replace(path)


def safe_id(value):
    if not value or any(ch not in '0123456789abcdef-' for ch in value):
        raise ValueError('Некорректный ID запуска')
    return value


def load_run(run_id):
    path = RUNS / (safe_id(run_id) + '.json')
    if not path.exists():raise FileNotFoundError('Запуск не найден')
    record=json.loads(path.read_text())
    # Legacy display identifiers are migrated in memory, preserving stored evidence.
    for i,campaign in enumerate(record['plan']):campaign['campaign_name']=f'BeeAgent_{i+1:02d}'
    for i,detail in enumerate(record['forecast']['details']):detail['campaign']['campaign_name']=f'BeeAgent_{i+1:02d}'
    return record


def restore(record):
    return Engine.from_snapshot(pd.read_csv(ROOT/'customer_profile.csv'), pd.read_csv(ROOT/'data/dict_tariff.csv'), record['knowledge'])


def plan_bundle(engine, plan, constraints=None):
    forecast = engine.forecast(plan, constraints)
    cautious = engine.forecast(plan, constraints, risk=1.0)
    return dict(plan=plan, forecast=forecast, cautious_net=cautious['net'],
                audit=engine.audit(plan, constraints), passports=engine.passports(plan, constraints))


def execute(run_id, seed):
    started = time.perf_counter()
    try:
        agent = Agent(report_path=RUNS/(run_id+'.knowledge.json'))
        result = evaluate_agent(agent, seed=seed, verbose=False)
        if result is None:raise RuntimeError('Официальный оценщик не вернул результат')
        record = dict(run_id=run_id, seed=seed, source='Official mock', status='completed',
                      created_at=datetime.now(timezone.utc).isoformat(), seconds=time.perf_counter()-started,
                      official=clean(result), knowledge=agent.snapshot,
                      **plan_bundle(agent.engine, agent.plan))
        save(RUNS/(run_id+'.json'),record)
        with LOCK:JOBS[run_id] = {'status':'completed','run_id':run_id}
    except Exception as error:
        with LOCK:JOBS[run_id] = {'status':'failed','run_id':run_id,'error':str(error)}


def summary(record):
    return {k:record.get(k) for k in ['run_id','seed','source','status','created_at','seconds','official']}


def tariff_lookup(codes):
    frame=pd.read_csv(ROOT/'data/dict_tariff.csv')
    return clean(frame[frame.tariff_plan_code.isin(codes)].to_dict('records'))

PLANS=PlanService(RUNS,load_run,restore,plan_bundle,save,tariff_lookup)
ASSISTANT=Assistant(PLANS,RUNS/'assistant.sqlite3')

def execute_ai(job_id,body,cancel):
    try:
        result=ASSISTANT.ask(body['run_id'],body['base_plan_id'],body['prompt'],body.get('campaign_index',0),cancel)
    except (KeyError,ValueError,TypeError):result={'status':'unavailable','message':'Проверьте выбранный план и запрос.'}
    except Exception:result={'status':'unavailable','message':'AI-ассистент временно недоступен. Изменить условия можно вручную'}
    with LOCK:AI_JOBS[job_id]['result']=result;AI_JOBS[job_id]['status']='completed'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def respond(self, data, status=200):
        payload=json.dumps(clean(data),ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)

    def do_GET(self):
        try:
            if not self.valid_host():return self.respond({'error':'Недопустимый адрес'},403)
            path=self.path.split('?')[0]
            if path=='/api/assistant/status':return self.respond(ASSISTANT.status())
            if path.startswith('/api/assistant/jobs/'):
                with LOCK:job=AI_JOBS.get(safe_id(path.rsplit('/',1)[1]))
                if not job:raise FileNotFoundError('Запрос не найден')
                return self.respond({k:v for k,v in job.items() if k!='cancel'})
            parts=path.strip('/').split('/')
            if len(parts) in [5,6] and parts[:2]==['api','runs'] and parts[3]=='plans':
                plan=PLANS.get(parts[2],parts[4])
                if len(parts)==6 and parts[5]=='export':
                    payload=PLANS.export(parts[2],parts[4])
                    self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8')
                    self.send_header('Content-Disposition',f'attachment; filename="beeagent-{plan["plan_id"]}.csv"')
                    self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return
                return self.respond(plan)
            if path=='/api/runs':
                records=[]
                for file in RUNS.glob('*.json'):
                    if file.name.endswith('.knowledge.json'):continue
                    records.append(summary(json.loads(file.read_text())))
                return self.respond(sorted(records,key=lambda x:x['created_at'],reverse=True))
            if path=='/api/benchmarks':
                file=ROOT/'reports/levra/comparison.json'
                return self.respond(json.loads(file.read_text()) if file.exists() else {'status':'not_run'})
            if path.startswith('/api/runs/'):
                run_id=safe_id(path.rsplit('/',1)[1])
                with LOCK:job=JOBS.get(run_id)
                if job and job['status']!='completed':return self.respond(job)
                record=load_run(run_id)
                record['execution_mode']='replay'
                # Knowledge stays in local artifacts; UI sees evidence, not customer data.
                record['knowledge_summary']={k:record['knowledge'][k] for k in ['snapshot_id','diagnostics','stop_reason','assumptions','spent_budget','spent_contacts']}
                record['pilots']=record['knowledge']['pilots']
                record.update(plan_id=run_id,data_version=record['knowledge']['snapshot_id'],measurement=record['official'])
                record['active_bundle']=PLANS.get(run_id,PLANS.active_id(run_id))
                del record['knowledge']
                return self.respond(record)
            if path.startswith('/api/'):
                return self.respond({'error':'Маршрут не найден'},404)
            relative=path.lstrip('/') or 'index.html'
            target=(ROOT/'frontend/dist'/relative).resolve()
            if not target.is_relative_to((ROOT/'frontend/dist').resolve()):raise ValueError('Invalid path')
            if not target.is_file():target=ROOT/'frontend/dist/index.html'
            if not target.is_file():return self.respond({'error':'Сначала выполните сборку frontend'},503)
            payload=target.read_bytes()
            self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(target)[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(payload)
        except FileNotFoundError as error:self.respond({'error':str(error)},404)
        except (ValueError,KeyError,TypeError) as error:self.respond({'error':str(error)},400)
        except Exception:self.respond({'error':'Не удалось обработать запрос'},500)

    def valid_host(self):
        return self.headers.get('Host') in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']

    def do_POST(self):
        try:
            if not self.valid_host():return self.respond({'error':'Недопустимый адрес'},403)
            # Same-origin local tool: reject remote browser writes, no permissive CORS.
            origin=self.headers.get('Origin')
            if origin and origin not in [f'http://{self.headers.get("Host")}']:
                return self.respond({'error':'Origin rejected'},403)
            size=int(self.headers.get('Content-Length',0))
            if size>200000:raise ValueError('Слишком большой запрос')
            body=json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(body,dict):raise ValueError('Ожидался объект запроса')
            path=self.path.split('?')[0]
            if path=='/api/assistant':
                if set(body)-{'run_id','base_plan_id','prompt','campaign_index'}:raise ValueError('Неизвестное поле запроса')
                safe_id(body.get('base_plan_id'))
                PLANS.get(body.get('run_id'),body.get('base_plan_id'))
                prompt=body.get('prompt')
                if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=2000:raise ValueError('Запрос должен содержать от 1 до 2000 символов')
                with LOCK:
                    if any(j['status']=='running' for j in AI_JOBS.values()):return self.respond({'error':'Запрос ассистенту уже выполняется'},409)
                    for key in list(AI_JOBS)[:-99]:del AI_JOBS[key]
                    job_id=str(uuid.uuid4());cancel=threading.Event()
                    AI_JOBS[job_id]={'job_id':job_id,'status':'running','cancel':cancel}
                threading.Thread(target=execute_ai,args=(job_id,body,cancel),daemon=True).start()
                return self.respond({'job_id':job_id,'status':'running'},202)
            if path.startswith('/api/assistant/jobs/') and path.endswith('/cancel'):
                job_id=safe_id(path.split('/')[-2])
                with LOCK:
                    if job_id not in AI_JOBS:raise ValueError('Запрос не найден')
                    AI_JOBS[job_id]['cancel'].set()
                return self.respond({'status':'cancelling'})
            if path=='/api/runs':
                seed=body.get('seed',42)
                if type(seed)!=int or seed<0 or seed>2**32-1:raise ValueError('Номер прогона должен быть целым неотрицательным числом')
                with LOCK:
                    if any(j['status']=='running' for j in JOBS.values()):return self.respond({'error':'Исследование уже выполняется'},409)
                    run_id=str(uuid.uuid4());JOBS[run_id]={'run_id':run_id,'status':'running','source':'Official mock','seed':seed}
                threading.Thread(target=execute,args=(run_id,seed),daemon=True).start()
                return self.respond(JOBS[run_id],202)
            parts=path.strip('/').split('/')
            if len(parts)!=4 or parts[:2]!=['api','runs'] or parts[3] not in ['replan','audit','repair','apply','save','compare']:
                return self.respond({'error':'Маршрут не найден'},404)
            if parts[3]=='apply':
                with LOCK:result=PLANS.apply(parts[2],body['plan_id'],body['expected_active_plan_id'])
                return self.respond(result)
            if parts[3]=='save':
                bundle=PLANS.get(parts[2],body['plan_id'])
                save(RUNS/'plans'/(bundle['plan_id']+'.saved.json'),bundle)
                return self.respond({'saved':True,'plan_id':bundle['plan_id']})
            if parts[3]=='compare':return self.respond(PLANS.compare(parts[2],body['base_plan_id'],body['proposed_plan_id']))
            record=load_run(parts[2]);engine=restore(record)
            constraints=body.get('constraints',{})
            edited=body.get('plan',record['plan'])
            if not isinstance(edited,list) or len(edited)>50 or any(not isinstance(c,dict) for c in edited):
                raise ValueError('План должен быть списком правил кампаний, не более 50 строк для проверки')
            if parts[3]=='audit':
                return self.respond(engine.audit(edited,constraints))
            bundle=PLANS.propose(parts[2],body.get('base_plan_id',parts[2]),constraints,
                edited if parts[3]=='repair' else None)
            return self.respond(bundle)
        except FileNotFoundError as error:self.respond({'error':str(error)},404)
        except (ValueError,KeyError,TypeError) as error:self.respond({'error':str(error)},400)
        except Exception:self.respond({'error':'Не удалось обработать запрос'},500)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'BeeAgent: http://127.0.0.1:{args.port}',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
