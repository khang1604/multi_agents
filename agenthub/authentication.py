"""Non-generative auth status and short-lived, account-free Hub evidence."""
import json
import math
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time

from .platforms import FileLock, spawn, stop_tree
from .settings import atomic_json

COPILOT_STATUS_ARGS = ['--headless', '--no-auto-update', '--log-level', 'none', '--stdio']
AUTH_TTL = 300


def copilot_status(command, timeout=8):
    """Use the official SDK's auth.getStatus RPC, never create/send a session.

    The CLI owns authentication. Only its boolean status crosses this boundary;
    account details, stderr, and unknown protocol fields are discarded.
    """
    received = queue.Queue(maxsize=1)
    with tempfile.TemporaryDirectory(prefix='ma-auth-') as cwd:
        process = spawn(command + COPILOT_STATUS_ARGS, cwd=cwd, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        def exchange():
            """Send only auth.getStatus and reduce a bounded stdio reply to a boolean."""
            try:
                request = json.dumps({'jsonrpc': '2.0', 'id': 'ma-auth',
                                      'method': 'auth.getStatus', 'params': {}}).encode('utf-8')
                process.stdin.write(('Content-Length: ' + str(len(request)) + '\r\n\r\n').encode('ascii') + request)
                process.stdin.flush()
                remaining = 65536
                while remaining > 0:
                    line = process.stdout.readline(min(remaining, 4096) + 1)
                    remaining -= len(line)
                    if not line or len(line) > 4096 or remaining <= 0:
                        break
                    if not line.lower().startswith(b'content-length:'):
                        continue
                    size = int(line.split(b':', 1)[1].strip())
                    if not 0 < size <= remaining:
                        break
                    # Bound extra headers as well as the payload.
                    while True:
                        header = process.stdout.readline(min(remaining, 4096) + 1)
                        remaining -= len(header)
                        if not header or remaining <= 0 or len(header) > 4096:
                            raise ValueError('Invalid auth response')
                        if header in (b'\r\n', b'\n'):
                            break
                    payload = bytearray()
                    while len(payload) < size:
                        chunk = process.stdout.read(size - len(payload))
                        if not chunk:
                            raise ValueError('Incomplete auth response')
                        payload.extend(chunk)
                    remaining -= size
                    reply = json.loads(payload)
                    if not isinstance(reply, dict) or reply.get('id') != 'ma-auth':
                        continue
                    result = reply.get('result')
                    value = result.get('isAuthenticated') if isinstance(result, dict) and 'error' not in reply else None
                    received.put(value if type(value) is bool else None)
                    return
            except (OSError, ValueError, TypeError):
                pass
            received.put(None)

        reader = threading.Thread(target=exchange, daemon=True)
        reader.start()
        try:
            try:
                return received.get(timeout=timeout)
            except queue.Empty:
                return None
        finally:
            if not stop_tree(process):
                raise ValueError('Auth status process could not be stopped')
            reader.join(timeout=1)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()


def _read(path):
    """Read bounded Hub-owned authentication evidence while rejecting symlinks and malformed data."""
    if path.is_symlink():
        raise ValueError('Refusing symlink authentication evidence')
    if not path.exists() or path.stat().st_size > 65536:
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def apply_status(rows, home, checked, now=None):
    """Cache only explicit official auth evidence, keyed by executable/model."""
    from .confirmations import fingerprint
    now = time.time() if now is None else now
    path = Path(home) / 'agent-auth-status.json'
    with FileLock(Path(home) / 'agent-auth-status.lock'):
        values = _read(path)
        for row in rows:
            name = row['agent']
            if checked:
                values.pop(name, None)
                if row['authentication'] in {'AUTHENTICATED', 'NOT_AUTHENTICATED'}:
                    values[name] = {'authentication': row['authentication'], 'checked_at': now,
                                    'fingerprint': fingerprint(row),
                                    'adapter_protocol_detected': bool(row.get('adapter_protocol_detected'))}
                    row['authentication_checked_at'] = now
            else:
                item = values.get(name, {})
                when = item.get('checked_at') if isinstance(item, dict) else None
                if (type(when) in (int, float) and math.isfinite(when) and 0 <= now - when < AUTH_TTL
                        and item.get('fingerprint') == fingerprint(row)
                        and row['state'] not in {'NOT_INSTALLED', 'UNAVAILABLE'}
                        and item.get('authentication') in {'AUTHENTICATED', 'NOT_AUTHENTICATED'}):
                    row.update(authentication=item['authentication'], authentication_checked_at=when,
                               authentication_source='cached_official_probe')
                    if item['authentication'] == 'AUTHENTICATED':
                        row['state'] = 'READY' if item.get('adapter_protocol_detected') else 'AUTHENTICATED'
        if checked:
            atomic_json(path, values, backup=False)
    return rows


def forget_status(home, name):
    """Remove Hub-owned readiness evidence when an operator attempts sign-out."""
    for filename, lockname in [('agent-auth-status.json', 'agent-auth-status.lock'),
                               ('agent-live-observations.json', 'agent-live-observations.lock'),
                               ('agent-confirmations.json', 'settings.lock')]:
        path = Path(home) / filename
        with FileLock(Path(home) / lockname):
            values = _read(path)
            if name in values:
                values.pop(name)
                atomic_json(path, values, backup=False)
