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
    """Build a pinned local stdio server definition for a supported client."""
    if client not in CLIENTS:
        raise ValueError('Unsupported client; use ma run from Terminal')
    return {'command': sys.executable, 'args': [str(Path(__file__).resolve().parents[1] / 'cli/ma.py'),
            '--home', str(Path(home).resolve()), 'mcp', '--client', client]}


def client_target(client):
    """Resolve the documented per-user configuration path for a supported MCP client."""
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
    """Describe an optional client integration without writing its settings."""
    entry = server(home, client)
    if client == 'codex':
        return {'client': client, 'command': ['codex', 'mcp', 'add', 'multi_agents', '--', entry['command'], *entry['args']],
                'status': 'official CLI command; not executed', 'live_verified': False}
    return {'client': client, 'path': str(client_target(client)), 'entry': entry,
            'client_detected': bool(shutil.which({'antigravity': 'antigravity', 'vscode': 'code', 'claude': 'claude', 'copilot': 'copilot'}[client])),
            'status': 'preview; explicit --apply required; client detection is not MCP verification', 'live_verified': False}


def install_client(home, client, apply=False, target=None, runner=None):
    """Explicitly merge an owned MCP entry with backups while preserving unrelated settings."""
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
        # Only migrate the exact former layout, never an edited or foreign entry.
        record = Path(home) / 'integrations' / (client + '.json')
        legacy = {**desired, 'args': list(desired['args'])}
        legacy['args'][0] = str(Path(__file__).resolve().parents[1] / 'ma.py')
        owned = {}
        if record.is_file() and not record.is_symlink():
            try:
                owned = json.loads(record.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                pass
        if (not isinstance(owned, dict) or owned.get('client') != client
                or owned.get('path') != str(path) or owned.get('key') != key
                or owned.get('entry') != existing or existing != legacy):
            raise ValueError('Client server multi_agents already exists with different settings; not overwritten. '
                             'Select only the intended MCP client in ma setup; review conflicting settings manually.')
    if existing == desired:
        return {'client': client, 'status': 'already configured', 'path': str(path), 'live_verified': False}
    entries['multi_agents'] = desired
    backup = atomic_json(path, value)
    # Record only our entry for safe future removal; never copy sibling credentials.
    try:
        atomic_json(Path(home) / 'integrations' / (client + '.json'),
                    {'client': client, 'path': str(path), 'key': key, 'entry': desired})
    except BaseException:
        # Do not leave a migrated entry behind with stale ownership metadata.
        if backup:
            shutil.copy2(backup, path)
        else:
            path.unlink(missing_ok=True)
        raise
    return {'client': client, 'status': 'configured; refresh client and verify tools',
            'path': str(path), 'backup': backup, 'live_verified': False}


def remove_client(home, client):
    """Remove only an unchanged owned MCP entry and retain unrelated configuration."""
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
    """Use the official Codex MCP command with ownership checks and configuration backups."""
    from .platforms import resolve_command
    from .registry import probe
    runner = runner or probe
    prefix = resolve_command(['codex'])
    record = Path(home) / 'integrations/codex.json'
    entry = server(home, 'codex')
    config = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'config.toml'
    upgrading = False
    code, text = runner(prefix + ['mcp', 'get', 'multi_agents', '--json'])
    if code == 0:
        current = json.loads(text)
        transport = current.get('transport', current)
        if transport.get('command') == entry['command'] and transport.get('args') == entry['args']:
            return {'client': 'codex', 'status': 'already configured', 'live_verified': False}
        legacy = {**entry, 'args': list(entry['args'])}
        legacy['args'][0] = str(Path(__file__).resolve().parents[1] / 'ma.py')
        owned = {}
        if record.is_file() and not record.is_symlink():
            try:
                owned = json.loads(record.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                pass
        if (not isinstance(owned, dict) or owned.get('client') != 'codex'
                or owned.get('path') != str(config) or owned.get('entry') != legacy
                or transport.get('command') != legacy['command'] or transport.get('args') != legacy['args']
                or transport.get('type', 'stdio') != 'stdio'
                or any(value not in (None, {}, [], '') for key, value in transport.items()
                       if key not in {'type', 'command', 'args'})
                or current.get('enabled') is False
                or not config.is_file()):
            raise ValueError('Codex server multi_agents already exists; not overwritten')
        upgrading = True
    # Back up the official config without parsing its non-MCP settings.
    backup = None
    if config.is_symlink(): raise ValueError('Refusing symlink Codex config')
    if config.exists():
        backup = config.with_name(config.name + '.backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        shutil.copy2(config, backup)
    try:
        if upgrading:
            code, _ = runner(prefix + ['mcp', 'remove', 'multi_agents'])
            if code: raise ValueError('Official Codex MCP upgrade removal failed; prior config restored')
        code, _ = runner(prefix + ['mcp', 'add', 'multi_agents', '--', entry['command'], *entry['args']])
        if code: raise ValueError('Official Codex MCP registration failed')
        atomic_json(record, {'client': 'codex', 'path': str(config), 'entry': entry})
    except BaseException:
        if backup: shutil.copy2(backup, config)
        raise
    return {'client': 'codex', 'status': 'configured via official CLI; refresh client',
            'backup': str(backup) if backup else None, 'live_verified': False}
