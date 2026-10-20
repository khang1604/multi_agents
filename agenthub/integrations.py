"""One stdio orchestrator, explicit external client configuration, no credential output."""
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
from datetime import datetime, timezone

from .settings import atomic_json

CLIENTS = ('antigravity', 'vscode', 'codex', 'copilot', 'claude')


def server(home, client):
    if client not in CLIENTS:
        raise ValueError('Unsupported client; use ma run from Terminal')
    return {'command': sys.executable, 'args': [str(Path(__file__).resolve().parents[1] / 'ma.py'),
            '--home', str(Path(home).resolve()), 'mcp', '--client', client]}


def client_target(client):
    home = Path.home()
    if os.name == 'nt':
        code_base = Path(os.environ.get('APPDATA', home / 'AppData/Roaming'))
    elif sys.platform == 'darwin':
        code_base = home / 'Library/Application Support'
    else:
        code_base = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    paths = {'antigravity': home / '.gemini/config/mcp_config.json',
             'copilot': Path(os.environ.get('COPILOT_HOME', home / '.copilot')) / 'mcp-config.json',
             'claude': home / '.claude.json',
             'vscode': code_base / 'Code/User/mcp.json'}
    if client not in paths:
        raise ValueError('Codex uses its official CLI: ma integrations command codex')
    return paths[client]


def integration_plan(home, client):
    entry = server(home, client)
    if client == 'codex':
        return {'client': client, 'command': ['codex', 'mcp', 'add', 'multi_agents', '--', entry['command'], *entry['args']],
                'status': 'official CLI command; not executed', 'live_verified': False}
    return {'client': client, 'path': str(client_target(client)), 'entry': entry,
            'client_detected': bool(shutil.which({'antigravity': 'antigravity', 'vscode': 'code', 'claude': 'claude', 'copilot': 'copilot'}[client])),
            'status': 'preview; explicit --apply required; client detection is not MCP verification', 'live_verified': False}


def install_client(home, client, apply=False, target=None, runner=None):
    plan = integration_plan(home, client)
    if not apply:
        return plan
    if client == 'codex':
        return install_codex(home, runner=runner)
    path = Path(target) if target else client_target(client)
    if path.is_symlink():
        raise ValueError('Refusing symlink client config')
    # This is an explicitly selected official configuration file, never auth storage.
    raw = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    value = json.loads(raw) if raw.strip() else {}
    if not isinstance(value, dict):
        raise ValueError('Client config must be a JSON object; existing file preserved')
    key = 'servers' if client == 'vscode' else 'mcpServers'
    entries = value.setdefault(key, {})
    if not isinstance(entries, dict):
        raise ValueError('Client server list must be a JSON object; existing file preserved')
    desired = server(home, client)
    if client == 'vscode':
        desired = {'type': 'stdio', **desired}
    existing = entries.get('multi_agents')
    if existing is not None and existing != desired:
        raise ValueError('Client server multi_agents already exists with different settings; not overwritten')
    if existing == desired:
        return {'client': client, 'status': 'already configured', 'path': str(path), 'live_verified': False}
    entries['multi_agents'] = desired
    backup = atomic_json(path, value)
    # Record only our entry for safe future removal; never copy sibling credentials.
    atomic_json(Path(home) / 'integrations' / (client + '.json'),
                {'client': client, 'path': str(path), 'key': key, 'entry': desired})
    return {'client': client, 'status': 'configured; refresh client and verify tools',
            'path': str(path), 'backup': backup, 'live_verified': False}


def remove_client(home, client):
    record = Path(home) / 'integrations' / (client + '.json')
    if not record.exists():
        return {'client': client, 'status': 'not owned; unchanged'}
    owned = json.loads(record.read_text(encoding='utf-8'))
    if client == 'codex':
        from .registry import probe
        from .platforms import resolve_command
        prefix = resolve_command(['codex'])
        code, text = probe(prefix + ['mcp', 'get', 'multi_agents', '--json'])
        if code:
            return {'client': client, 'status': 'owned server no longer registered'}
        current = json.loads(text)
        transport = current.get('transport', current)
        if transport.get('command') != owned['entry']['command'] or transport.get('args') != owned['entry']['args']:
            raise ValueError('Codex MCP entry changed; not removed')
        code, _ = probe(prefix + ['mcp', 'remove', 'multi_agents'])
        if code: raise ValueError('Codex MCP removal failed; inspect official CLI locally')
        record.unlink()
        return {'client': client, 'status': 'removed owned entry only'}
    path = Path(owned['path'])
    if path.is_symlink():
        raise ValueError('Refusing symlink client config')
    value = json.loads(path.read_text(encoding='utf-8'))
    entries = value.get(owned['key'], {})
    if entries.get('multi_agents') != owned['entry']:
        raise ValueError('Owned MCP entry changed; preserving user configuration')
    del entries['multi_agents']
    backup = atomic_json(path, value)
    record.unlink()
    return {'client': client, 'status': 'removed owned entry only', 'backup': backup}


def install_codex(home, runner=None):
    from .platforms import resolve_command
    from .registry import probe
    runner = runner or probe
    prefix = resolve_command(['codex'])
    record = Path(home) / 'integrations/codex.json'
    entry = server(home, 'codex')
    code, text = runner(prefix + ['mcp', 'get', 'multi_agents', '--json'])
    if code == 0:
        current = json.loads(text)
        transport = current.get('transport', current)
        if transport.get('command') == entry['command'] and transport.get('args') == entry['args']:
            return {'client': 'codex', 'status': 'already configured', 'live_verified': False}
        raise ValueError('Codex server multi_agents already exists; not overwritten')
    # Back up the official config without parsing its non-MCP settings.
    config = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'config.toml'
    backup = None
    if config.is_symlink(): raise ValueError('Refusing symlink Codex config')
    if config.exists():
        backup = config.with_name(config.name + '.backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        shutil.copy2(config, backup)
    try:
        code, _ = runner(prefix + ['mcp', 'add', 'multi_agents', '--', entry['command'], *entry['args']])
        if code: raise ValueError('Official Codex MCP registration failed')
        atomic_json(record, {'client': 'codex', 'path': str(config), 'entry': entry})
    except BaseException:
        if backup: shutil.copy2(backup, config)
        raise
    return {'client': 'codex', 'status': 'configured via official CLI; refresh client',
            'backup': str(backup) if backup else None, 'live_verified': False}
