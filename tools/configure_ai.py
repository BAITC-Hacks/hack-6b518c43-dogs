"""Interactive local-only setup. Input is hidden; credentials never enter shell history."""
import getpass,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    path=ROOT/'.env'
    if path.exists():raise SystemExit('Local .env already exists; edit it locally to preserve your configuration.')
    key=getpass.getpass('New reviewer OpenAI API key (hidden; never paste it in chat): ').strip()
    if not key or '\n' in key or '\r' in key:raise SystemExit('No valid local key supplied.')
    config='OPENAI_API_KEY='+key+'\nOPENAI_MODEL=gpt-6-sol\nBEEAGENT_AI_BUDGET_USD=3\nBEEAGENT_AI_MAX_CALLS=100\n'
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as file:file.write(config)
    print('Local configuration saved with owner-only permissions. Restart ./run.sh. No API call was made.')
if __name__=='__main__':main()
