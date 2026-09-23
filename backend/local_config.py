"""User-initiated local credential setup. Never returns or logs the credential."""
import os
import re
from pathlib import Path
from dotenv import dotenv_values


def configure_mini(root, key):
    if not isinstance(key,str) or not re.fullmatch(r'sk-[A-Za-z0-9_-]{16,500}',key):
        raise ValueError('Вставьте полный OpenAI API-ключ без пробелов.')
    path=Path(root)/'.env'
    if path.is_symlink():raise ValueError('Нельзя записать настройки в ссылку.')
    existing=dotenv_values(path) if path.exists() else {}
    # Preserve unrelated settings; changing credentials must not reset spend.
    existing.update(OPENAI_API_KEY=key,OPENAI_MODEL='gpt-5.4-mini')
    existing.setdefault('BEEAGENT_AI_BUDGET_USD','3')
    existing.setdefault('BEEAGENT_AI_MAX_CALLS','100')
    for name in list(existing):
        if name.startswith('BEEAGENT_') and name.endswith('_USD_PER_MILLION'):
            del existing[name]  # Mini uses its verified built-in rates.
    def quoted(value):
        return "'"+str(value or '').replace('\\','\\\\').replace("'","\\'")+"'"
    content=''.join(name+'='+quoted(value)+'\n' for name,value in existing.items())
    # Owner-only temporary file, atomic replacement, no key in its filename.
    import tempfile
    descriptor,temporary=tempfile.mkstemp(prefix='.beeagent-config-',dir=root)
    try:
        with os.fdopen(descriptor,'w') as stream:stream.write(content)
        os.chmod(temporary,0o600);os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    os.environ.update({name:str(value or '') for name,value in existing.items()})
    for name in list(os.environ):
        if name.startswith('BEEAGENT_') and name.endswith('_USD_PER_MILLION'):os.environ.pop(name,None)
