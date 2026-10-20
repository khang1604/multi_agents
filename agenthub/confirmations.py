"""Operator readiness reports, separate from automatic authentication evidence."""
import hashlib
import json
import math
from pathlib import Path
import time

from .platforms import FileLock
from .settings import atomic_json, ensure_idle

def fingerprint(row):
    command = row.get('command', [])
    executable = Path(command[0]) if command else None
    stat = executable.stat() if executable and executable.is_file() else None
    facts = [command, [stat.st_size, stat.st_mtime_ns] if stat else None,
             row.get('model_policy'), row.get('configured_model')]
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()


def read(home):
    path = Path(home) / 'agent-confirmations.json'
    if path.is_symlink():
        raise ValueError('Refusing symlink operator confirmations')
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    return value if isinstance(value, dict) else {}


def apply(rows, home, now=None):
    records = read(home)
    now = time.time() if now is None else now
    for row in rows:
        record = records.get(row['agent'])
        if not isinstance(record, dict) or record.get('source') != 'operator':
            continue
        start, end = record.get('confirmed_at'), record.get('expires_at')
        if type(start) not in (int, float) or not math.isfinite(start) or start > now:
            continue
        # Respect an existing expiring record until the operator confirms anew.
        if end is not None and (type(end) not in (int, float) or not math.isfinite(end) or now >= end):
            continue
        if row['state'] in {'NOT_INSTALLED', 'UNAVAILABLE'} or row.get('authentication') == 'NOT_AUTHENTICATED':
            continue
        if row.get('reason') and row['state'] != 'UNKNOWN':
            continue
        if record.get('fingerprint') != fingerprint(row):
            continue
        # A checked CLI that no longer exposes the adapter cannot inherit old evidence.
        if row.get('status_checked') and not row.get('adapter_protocol_detected'):
            continue
        row.update(operator_confirmed=True, confirmation_source='operator',
                   confirmed_at=start, confirmation_expires_at=end)
        row['state'] = 'READY'
        # Authentication and live_verified deliberately retain their probed values.
    return rows


def confirm(hub, name, worked=False, revoke=False, runner=None):
    from .registry import SPECS, discover_agent
    if name not in SPECS:
        raise ValueError('Unknown agent')
    if worked == revoke:
        raise ValueError('Choose --worked after a successful manual AI reply, or --revoke')
    with FileLock(hub.store.home / 'settings.lock'):
        ensure_idle(hub.store)
        records = read(hub.store.home)
        if revoke:
            records.pop(name, None)
        else:
            config = json.loads((hub.store.home / 'config.json').read_text(encoding='utf-8'))
            row = discover_agent(name, config['providers'][name], check=True, runner=runner)
            if row['state'] in {'NOT_INSTALLED', 'UNAVAILABLE'} or row.get('authentication') == 'NOT_AUTHENTICATED' or not row['adapter_protocol_detected']:
                raise ValueError('CLI/protocol check failed; manual report was not recorded')
            now = time.time()
            records[name] = {'source': 'operator', 'confirmed_at': now,
                             'fingerprint': fingerprint(row)}
        atomic_json(hub.store.home / 'agent-confirmations.json', records)
    return {'agent': name, 'status': 'confirmation revoked' if revoke else 'READY',
            'source': 'operator', 'model_calls': 0}
