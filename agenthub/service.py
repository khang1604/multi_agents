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


def daemon_version():
    """Compute a deterministic digest of the active runtime modules."""
    import hashlib
    digest = hashlib.sha256()
    for folder in (ROOT / 'agenthub', ROOT / 'cli'):
        for path in sorted(folder.glob('*.py')):
            digest.update(path.name.encode('utf-8'))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def start_daemon(home):
    """Start the detached shared daemon, restarting an idle daemon if runtime code changed."""
    import time
    home = Path(home).resolve()
    version_file = home / 'daemon.version'
    current_version = daemon_version()
    if daemon_status(home) == 'running':
        running_version = version_file.read_text(encoding='utf-8').strip() if version_file.exists() else ''
        if running_version == current_version:
            return {'status': 'running'}
        stop_daemon(home)
        deadline = time.monotonic() + 8
        while daemon_status(home) == 'running' and time.monotonic() < deadline:
            time.sleep(0.15)
        if daemon_status(home) == 'running':
            return {'status': 'running'}
    home.mkdir(parents=True, exist_ok=True)
    (home / 'stop').unlink(missing_ok=True)
    version_file.write_text(current_version, encoding='utf-8')
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
