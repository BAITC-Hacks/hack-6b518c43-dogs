"""Local-only API and static UI. Official scoring is delegated unchanged to local_eval."""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
import mimetypes
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

RUNS = ROOT / 'reports/runs'
RUNS.mkdir(parents=True, exist_ok=True)
JOBS = {}
LOCK = threading.Lock()


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
    return json.loads(path.read_text())


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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def respond(self, data, status=200):
        payload=json.dumps(clean(data),ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)

    def do_GET(self):
        try:
            path=self.path.split('?')[0]
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
        except Exception as error:self.respond({'error':str(error)},500)

    def do_POST(self):
        try:
            # Same-origin local tool: reject remote browser writes, no permissive CORS.
            origin=self.headers.get('Origin')
            if origin and origin not in [f'http://{self.headers.get("Host")}']:
                return self.respond({'error':'Origin rejected'},403)
            size=int(self.headers.get('Content-Length',0))
            if size>200000:raise ValueError('Слишком большой запрос')
            body=json.loads(self.rfile.read(size) or b'{}')
            path=self.path.split('?')[0]
            if path=='/api/runs':
                seed=body.get('seed',42)
                if not isinstance(seed,int) or seed<0 or seed>2**32-1:raise ValueError('Seed должен быть целым неотрицательным числом')
                with LOCK:
                    if any(j['status']=='running' for j in JOBS.values()):return self.respond({'error':'Исследование уже выполняется'},409)
                    run_id=str(uuid.uuid4());JOBS[run_id]={'run_id':run_id,'status':'running','source':'Official mock','seed':seed}
                threading.Thread(target=execute,args=(run_id,seed),daemon=True).start()
                return self.respond(JOBS[run_id],202)
            parts=path.strip('/').split('/')
            if len(parts)!=4 or parts[:2]!=['api','runs'] or parts[3] not in ['replan','audit','repair']:
                return self.respond({'error':'Маршрут не найден'},404)
            record=load_run(parts[2]);engine=restore(record)
            constraints=body.get('constraints',{})
            # Engine has no env or run_pilot here: what-if cannot launch experiments.
            before=engine.snapshot()
            if parts[3]=='audit':
                return self.respond(engine.audit(body.get('plan',record['plan']),constraints))
            old_plan=body.get('plan',record['plan'])
            plan=engine.solve(constraints)
            bundle=plan_bundle(engine,plan,constraints)
            bundle.update(source='Forecast/what-if',snapshot_id=before['snapshot_id'],new_pilots=0,
                          prior_forecast=engine.forecast(record['plan']),
                          delta={k:bundle['forecast'][k]-record['forecast'][k] for k in ['net','cost','contacts','estimated_unique']})
            if parts[3]=='repair':bundle['before_audit']=engine.audit(old_plan,constraints)
            if engine.snapshot()!=before:raise RuntimeError('What-if changed knowledge')
            scenario_dir=RUNS/'scenarios';scenario_dir.mkdir(exist_ok=True)
            save(scenario_dir/(parts[2]+'-'+str(uuid.uuid4())+'.json'),bundle)
            return self.respond(bundle)
        except FileNotFoundError as error:self.respond({'error':str(error)},404)
        except (ValueError,KeyError,TypeError) as error:self.respond({'error':str(error)},400)
        except Exception as error:self.respond({'error':str(error)},500)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'LEVRA: http://127.0.0.1:{args.port}',flush=True)
    server.serve_forever()

if __name__=='__main__':main()
