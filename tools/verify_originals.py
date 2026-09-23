"""Verify organizer-provided file bytes against the starter manifest."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    manifest=json.loads((ROOT/'docs/ORIGINAL_MANIFEST.json').read_text(encoding='utf-8'))
    failures=[]
    for relative,expected in manifest.items():
        path=ROOT/relative
        if not path.is_file():failures.append(f'MISSING: {relative}');continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:failures.append(f'CHANGED: {relative}')
    if failures:raise SystemExit('\n'.join(failures))
    print(f'OK: {len(manifest)} organizer-provided files unchanged. agent.py is intentionally editable.')
if __name__=='__main__':main()
