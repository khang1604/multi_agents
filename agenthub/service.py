import json
import subprocess
import sys
import threading
from pathlib import Path

from .config import ROOT
from .platforms import FileLock, AlreadyRunning, spawn


def daemon_status(home):
    """Read daemon liveness without spawning a model or duplicating the service."""
    try:
        with FileLock(Path(home) / 'daemon.lock'):
            return 'stopped'
    except AlreadyRunning:
        return 'running'


def start_daemon(home):
    """Start the detached shared daemon only when it is not already running."""
    home = Path(home).resolve()
    if daemon_status(home) == 'running':
        return {'status': 'running'}
    home.mkdir(parents=True, exist_ok=True)
    (home / 'stop').unlink(missing_ok=True)
    with (home / 'daemon.log').open('ab') as log:
        process = spawn([sys.executable, str(ROOT / 'cli/hub.py'), '--home', str(home), 'daemon'],
                        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    # Reap the child if this caller remains open; it still survives this caller exiting.
    threading.Thread(target=process.wait, daemon=True).start()
    return {'status': 'starting', 'pid': process.pid, 'log': str(home / 'daemon.log')}


def stop_daemon(home):
    """Request shutdown of the owned daemon while retaining workflow state."""
    (Path(home) / 'stop').touch()
    return {'status': 'stop_requested', 'note': 'Current step stops at its next cancellation check; checkpoints remain.'}
