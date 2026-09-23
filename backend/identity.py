"""Provenance checks: measurements belong to exact plans and execution inputs."""
import hashlib,json
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

@lru_cache(maxsize=1)
def _runtime_identity():
    files=['customer_profile.csv','data/dict_tariff.csv','data/change_tariff.csv']
    from agent import ALGORITHM_VERSION
    return dict(algorithm_version=ALGORITHM_VERSION,
        engine_sha256=hashlib.sha256((ROOT/'agent.py').read_bytes()).hexdigest(),
        data_fingerprint=digest({name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}))

def runtime_identity():
    return dict(_runtime_identity())

def binding(record,plan_id,plan):
    return dict(run_id=record['run_id'],plan_id=plan_id,**record.get('identity',{}),
        snapshot_id=record['knowledge']['snapshot_id'],plan_sha256=digest(plan))

def compatible(record):
    return record.get('identity')==runtime_identity()

def verified_measurement(record,plan_id,plan):
    if not compatible(record):return None
    if plan_id!=record['run_id'] or record.get('measurement_binding')!=binding(record,plan_id,plan):return None
    return record.get('official')
