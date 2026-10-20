"""Non-generative queue watchdog; never grants calls or changes provider health."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .config import ROOT
from .service import daemon_status, start_daemon
from .settings import atomic_json
from .store import Store


def wake(home):
    store = Store(home)
    if daemon_status(home) == 'running':
        return {'status': 'running', 'ai_calls': 0}
    due = store.one("SELECT id FROM workflows WHERE (status IN ('queued','waiting') AND next_run <= ?) OR status IN ('running','recovering') LIMIT 1", (time.time(),))
    if not due:
        return {'status': 'idle', 'ai_calls': 0}
    return {**start_daemon(home), 'ai_calls': 0}


def install(home, apply=False, runner=None):
    if os.name != 'nt':
        return {'status': 'not installed; run ma start using your Linux user service', 'ai_calls': 0}
    home = Path(home).resolve()
    executable = Path(sys.executable).with_name('pythonw.exe')
    if not executable.is_file():
        raise ValueError('pythonw.exe is required for a hidden Windows wake task')
    name = 'MultiAgents-Wake-' + hashlib.sha256(str(home).encode()).hexdigest()[:12]
    entry = {'task': name, 'python': str(executable), 'source': str(ROOT), 'home': str(home)}
    record = home / 'integrations/wakeup.json'
    if not apply:
        return {'status': 'preview', **entry, 'interval_minutes': 5, 'ai_calls': 0}
    if record.is_symlink():
        raise ValueError('Refusing symlink wake registration')
    if record.exists() and json.loads(record.read_text(encoding='utf-8')) != entry:
        raise ValueError('Wake registration changed; existing task preserved')
    runner = runner or subprocess.run
    args = ['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(ROOT / 'scripts/install-wakeup.ps1'),
            '-TaskName', name, '-PythonPath', str(executable), '-SourcePath', str(ROOT), '-HubHome', str(home)]
    if record.exists():
        args.append('-Owned')
    result = runner(args, capture_output=True, encoding='utf-8', errors='replace', timeout=30)
    if result.returncode:
        raise ValueError('Windows wake registration failed; no credentials requested or security fallback applied')
    atomic_json(record, entry)
    return {'status': 'installed; user task checks queue every 5 minutes while logged in', 'task': name, 'ai_calls': 0}
