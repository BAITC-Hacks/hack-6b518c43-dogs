"""Check committed/intended files without printing any potential secret value."""
import hashlib,json,re,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    suspicious=[];scanned=0
    for name in sorted(set(filter(None,names))):
        path=ROOT/name
        if not path.is_file() or path.suffix.lower() not in ['.py','.md','.json','.jsonl','.txt','.ts','.tsx','.js','.mjs','.css','.sh','.yml','.yaml','.example','.log']:continue
        text=path.read_text(errors='replace');scanned+=1
        if re.search(r'sk-(?:proj-)?[A-Za-z0-9_-]{24,}',text):suspicious.append(name)
    protected=json.loads((ROOT/'docs/ORIGINAL_MANIFEST.json').read_text())
    original_check=subprocess.run(['.venv/bin/python','tools/verify_originals.py'],cwd=ROOT,capture_output=True,text=True)
    required=['agent.py','submission.csv','requirements.txt','README.md','STATE.md','docs/ACCEPTANCE.md','docs/DEMO.md','docs/TESTING_STAGE4.md','reports/stage3/selection.json','reports/stage4/ai_integration.json','reports/stage4/browser_checks.json']
    missing=[p for p in required if not (ROOT/p).is_file()]
    actual=hashlib.sha256((ROOT/'submission.csv').read_bytes()).hexdigest()
    repro=json.loads((ROOT/'reports/stage4/verification.json').read_text())
    clean=json.loads((ROOT/'reports/stage4/clean_install.json').read_text())
    registration=json.loads((ROOT/'reports/stage3/registration.json').read_text())
    frozen={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==registration['sha256'][p] for p in ['tools/stage3_variants.py','tools/stage3_worlds.py','reports/stage3/baseline/agent.py','reports/stage3/baseline/submission.csv']}
    frozen['original_protocol']=hashlib.sha256((ROOT/'reports/stage3/baseline/validation_protocol.md').read_bytes()).hexdigest()==registration['sha256']['docs/STAGE3_VALIDATION_PROTOCOL.md']
    report=dict(checked_at=datetime.now(timezone.utc).isoformat(),scanned_text_files=scanned,potential_secret_files=suspicious,
        originals_verified=original_check.returncode==0,originals_output=original_check.stdout.strip(),missing_required_files=missing,
        dotenv_tracked=any(n=='.env' or (n.startswith('.env.') and n!='.env.example') for n in names),
        submission_sha256=actual,reproducibility_matches=all(p['sha256']==actual for p in repro['fresh_processes']),
        clean_install_passed=clean['passed'],clean_install_submission_matches=clean.get('submission_sha256')==actual,
        frozen_experiment_files_unchanged=frozen,
        development_outcomes=len(json.loads((ROOT/'reports/stage3/development.json').read_text())['results']),
        heldout_outcomes=len(json.loads((ROOT/'reports/stage3/heldout.json').read_text())['results']))
    report['current_verification_passed']=repro['passed']
    report['browser_checks_passed']=json.loads((ROOT/'reports/stage4/browser_checks.json').read_text())['passed']
    report['clean_install_final_delta_passed']=json.loads((ROOT/'reports/stage4/clean_install_delta.json').read_text())['passed']
    report['external_ai_initial_status']=json.loads((ROOT/'reports/stage4/ai_integration.json').read_text())['status']
    report['copy_lint_passed']=json.loads((ROOT/'reports/stage4/copy_lint.json').read_text())['passed']
    report['policy_unchanged']=hashlib.sha256((ROOT/'agent.py').read_bytes()).hexdigest()==json.loads((ROOT/'reports/stage4/baseline.json').read_text())['sha256']['agent.py']
    report['passed']=not suspicious and not missing and not report['dotenv_tracked'] and all(frozen.values()) and all(report[k] for k in ['originals_verified','reproducibility_matches','clean_install_passed','clean_install_submission_matches','current_verification_passed','copy_lint_passed','policy_unchanged','browser_checks_passed','clean_install_final_delta_passed'])
    (ROOT/'reports/stage4/release_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
