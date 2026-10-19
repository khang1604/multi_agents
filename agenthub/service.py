import json
import subprocess
import sys
import threading
from pathlib import Path

from .config import ROOT
from .platforms import FileLock, AlreadyRunning, spawn


def daemon_status(home):
    try:
        with FileLock(Path(home) / 'daemon.lock'):
            return 'stopped'
    except AlreadyRunning:
        return 'running'


def start_daemon(home):
    home = Path(home).resolve()
    if daemon_status(home) == 'running':
        return {'status': 'running'}
    home.mkdir(parents=True, exist_ok=True)
    (home / 'stop').unlink(missing_ok=True)
    with (home / 'daemon.log').open('ab') as log:
        process = spawn([sys.executable, str(ROOT / 'hub.py'), '--home', str(home), 'daemon'],
                        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    # Reap the child if this caller remains open; it still survives this caller exiting.
    threading.Thread(target=process.wait, daemon=True).start()
    return {'status': 'starting', 'pid': process.pid, 'log': str(home / 'daemon.log')}


def stop_daemon(home):
    (Path(home) / 'stop').touch()
    return {'status': 'stop_requested', 'note': 'Current step stops at its next cancellation check; checkpoints remain.'}
