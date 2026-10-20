"""Official non-generative provider probes. Never reads credential/config files."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from .platforms import resolve_command, spawn, stop_tree

STATES = ('NOT_INSTALLED', 'INSTALLED', 'AUTHENTICATED', 'READY', 'UNAVAILABLE', 'UNKNOWN')
SPECS = {
    'codex': {'roles': ['plan', 'implement', 'review'], 'auth': ['login', 'status'],
              'login': 'codex login', 'client': 'codex', 'auto': False},
    'claude': {'roles': ['plan', 'implement', 'review'], 'auth': ['auth', 'status'],
               'login': 'claude auth login', 'client': 'claude', 'auto': False},
    'copilot': {'roles': ['plan', 'review'], 'auth': None,
                'login': 'copilot login (or /login inside CLI)', 'client': 'copilot', 'auto': True},
    'antigravity': {'roles': ['plan', 'review'], 'auth': None,
                    'login': 'Open agy and follow its official sign-in flow', 'client': 'agy', 'auto': False},
}


def validate_entry(name, entry):
    if name not in SPECS:
        raise ValueError('No supported execution adapter for ' + name)
    if type(entry.get('enabled', True)) is not bool:
        raise ValueError('enabled must be boolean')
    roles = entry.get('roles', [])
    if not isinstance(roles, list) or not roles or set(roles) - set(SPECS[name]['roles']):
        raise ValueError('Unsupported role for ' + name)
    model_arguments(name, entry)


def model_arguments(name, entry):
    policy = entry.get('model_policy', 'MANUAL' if entry.get('model') else 'INHERIT')
    if not isinstance(policy, str):
        raise ValueError('Model policy must be text')
    policy = policy.upper()
    if policy == 'INHERIT':
        return []
    if policy == 'AUTO':
        if SPECS.get(name, {}).get('auto'):
            return ['--model', 'auto']
        if entry.get('model_fallback') == 'INHERIT':
            return []
        raise ValueError(name + ' has no verified AUTO policy; explicitly choose INHERIT fallback')
    if policy != 'MANUAL':
        raise ValueError('Model policy must be INHERIT, AUTO or MANUAL')
    model = entry.get('model')
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}', model):
        raise ValueError('Invalid model id')
    # Legacy entries with model but no policy remain compatible. New manual choices
    # must be verified against a provider-reported catalog, never a hardcoded list.
    if entry.get('model_policy') and model not in entry.get('model_catalog', []):
        if entry.get('model_fallback') == 'INHERIT':
            return []
        raise ValueError('Model is not in the provider-reported catalog; choose INHERIT or refresh catalog')
    return ['--model', model]


def common_candidates(name):
    spec = SPECS[name]
    found = shutil.which(spec['client'])
    values = [[found]] if found else []
    if os.name == 'nt':
        local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
        roaming = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        program = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
        relative = [roaming / 'npm' / (spec['client'] + '.cmd'),
                    local / 'Microsoft/WinGet/Links' / (spec['client'] + '.exe')]
        if name == 'claude':
            relative += [Path.home() / '.local/bin/claude.exe']
        if name == 'antigravity':
            relative += [local / 'agy/bin/agy.exe', program / 'Google/antigravity-cli/agy.exe']
        values.extend([str(p)] for p in relative if p.is_file())
    return values


def probe(command, timeout=8):
    """Bounded output; discard raw diagnostics which may contain account identifiers."""
    with tempfile.TemporaryDirectory(prefix='ma-probe-') as cwd, tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = spawn(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_tree(process)
            raise ValueError('Provider status probe timed out')
        out.seek(0); err.seek(0)
        return process.returncode, (out.read(65536) + err.read(65536)).decode('utf-8', errors='replace')


def execution_command(name, entry):
    """Use the same bounded executable candidates for discovery and execution."""
    if entry.get('command') and entry['command'] != [SPECS[name]['client']]:
        # A custom/pinned command must never silently become another installation.
        return resolve_command(entry['command'])
    commands = [entry['command']] if entry.get('command') else []
    for command in commands + common_candidates(name):
        try:
            return resolve_command(command)
        except (OSError, ValueError):
            continue
    raise FileNotFoundError(name + ' CLI is not installed/on PATH')


def discover_agent(name, entry, check=False, runner=None):
    if name not in SPECS:
        raise ValueError('Unknown agent')
    runner = runner or probe
    result = {'agent': name, 'state': 'NOT_INSTALLED', 'enabled': entry.get('enabled', True),
              'roles': entry.get('roles', []), 'version': 'Unknown', 'authentication': 'UNKNOWN',
              'model_policy': entry.get('model_policy', 'MANUAL' if entry.get('model') else 'INHERIT'),
              'configured_model': entry.get('model') or 'Provider Default',
              'actual_model': 'Unknown', 'login_hint': SPECS[name]['login'],
              'adapter_protocol_detected': False, 'status_checked': check,
              'live_verified': False, 'model_catalog': [], 'quota_calls': 0,
              'ide_installed': bool(shutil.which('antigravity') or shutil.which('agy-ide')) if name == 'antigravity' else None}
    try:
        resolved = execution_command(name, entry)
    except (OSError, ValueError):
        return result
    result.update(state='INSTALLED', command=resolved)
    if not check:
        return result
    try:
        code, text = runner(resolved + ['--version'])
        if code:
            return dict(result, state='UNAVAILABLE', reason='Version probe failed')
        version = re.search(r'\b\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9.-]+)?', text)
        result['version'] = version.group() if version else 'Unknown'
        code, help_text = runner(resolved + ['--help'])
        result['adapter_protocol_detected'] = code == 0 and ('--output-format' in help_text if name != 'codex' else 'exec' in help_text)
        # Only parse explicitly advertised choices, not arbitrary help text.
        match = re.search(r'--model[^\n]*\[choices:\s*([^\]]+)\]', help_text)
        if match:
            result['model_catalog'] = re.findall(r'[\"\x27]([\w./:-]+)[\"\x27]', match[1])
        auth = SPECS[name]['auth']
        if auth:
            code, text = runner(resolved + auth)
            if name == 'claude':
                try:
                    authenticated = json.loads(text).get('loggedIn') is True
                except (ValueError, AttributeError):
                    authenticated = False
                    result['state'] = 'UNKNOWN'
            else:
                authenticated = code == 0
            if authenticated:
                result['authentication'] = 'AUTHENTICATED'
                result['state'] = 'READY' if result['adapter_protocol_detected'] else 'AUTHENTICATED'
            elif code == 1:
                result['authentication'] = 'NOT_AUTHENTICATED'
            else:
                result['state'] = 'UNKNOWN'
        else:
            result['state'] = 'UNKNOWN'
            result['reason'] = 'No verified noninteractive auth-status probe; no model call made'
    except (OSError, ValueError, subprocess.SubprocessError):
        result.update(state='UNAVAILABLE', reason='Non-generative status probe failed or timed out')
    return result


def record_live_success(home, name, entry):
    """Record actual adapter success, separate from credentials and operator claims."""
    from .confirmations import fingerprint
    from .settings import atomic_json
    from .platforms import FileLock
    path = Path(home) / 'agent-live-observations.json'
    with FileLock(Path(home) / 'agent-live-observations.lock'):
        if path.is_symlink():
            raise ValueError('Refusing symlink readiness evidence')
        values = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        row = discover_agent(name, entry)
        values[name] = {'source': 'cli_response', 'fingerprint': fingerprint(row), 'succeeded_at': time.time()}
        atomic_json(path, values, backup=False)


def discover(config, check=False, runner=None, home=None):
    rows = [discover_agent(name, config['providers'].get(name, {}), check, runner) for name in SPECS]
    if home is not None:
        from .confirmations import apply
        rows = apply(rows, home)
        from .confirmations import fingerprint
        from .store import Store
        path = Path(home) / 'agent-live-observations.json'
        observations = {}
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 65536:
            try:
                observations = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(observations, dict): observations = {}
            except (OSError, ValueError):
                pass
        health = {h['provider']: h for h in Store(home).all('SELECT * FROM health')}
        for row in rows:
            observed = observations.get(row['agent'], {})
            when = observed.get('succeeded_at', 0) if isinstance(observed, dict) else 0
            if (isinstance(observed, dict) and observed.get('source') == 'cli_response'
                    and type(when) in (int, float) and 0 < when <= time.time()
                    and row['state'] not in {'NOT_INSTALLED', 'UNAVAILABLE'}
                    and row['authentication'] != 'NOT_AUTHENTICATED'
                    and (not check or row['adapter_protocol_detected'])
                    and observed.get('fingerprint') == fingerprint(row)):
                row.update(state='READY', live_verified=True, readiness_source='cli_response', last_success_at=when)
                row.pop('reason', None)
            cooldown = health.get(row['agent'], {})
            if cooldown.get('until', 0) > time.time():
                row.update(state='UNAVAILABLE', cooldown_until=cooldown['until'],
                           reason='Đang chờ ' + cooldown['reason'].split(':', 1)[0])
    return rows


def model_info(config, name, home):
    if name not in SPECS:
        raise ValueError('Unknown agent')
    entry = config['providers'][name]
    catalog = entry.get('model_catalog', [])
    cache = Path(home) / 'agent-registry.json'
    if cache.exists():
        rows = json.loads(cache.read_text(encoding='utf-8'))
        catalog = next((r.get('model_catalog', []) for r in rows if r.get('agent') == name), catalog)
    policy = entry.get('model_policy', 'MANUAL' if entry.get('model') else 'INHERIT')
    return {'agent': name, 'policy': policy, 'configured_model': entry.get('model') if policy == 'MANUAL' else 'Provider Default',
            'actual_model': 'Unknown (recorded per attempt only when provider reports it)',
            'catalog': catalog, 'auto_supported': SPECS[name]['auto'],
            'note': 'No catalog means MANUAL cannot be verified; use INHERIT or an explicit INHERIT fallback.'}
