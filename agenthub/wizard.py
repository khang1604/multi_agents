"""Standard-library terminal checkbox and transactional setup configuration."""
import json
import os
from pathlib import Path
import sys

from .registry import discover, validate_entry
from .settings import atomic_json, ensure_idle


def checkbox(items, selected, read=None, write=print):
    selected = set(selected)
    if read is None and os.name == 'nt' and sys.stdin.isatty():
        import msvcrt
        read = msvcrt.getwch
    if read is not None:
        cursor = 0
        while True:
            write('\n' + '\n'.join(('> ' if i == cursor else '  ') + ('[x] ' if n in selected else '[ ] ') + n for i, n in enumerate(items)))
            write('Up/Down (or j/k): move; Space: toggle; Enter: confirm; Esc: cancel')
            key = read()
            if key in ('\x00', '\xe0'):
                key = {'H': 'k', 'P': 'j'}.get(read(), '')
            if key in ('\r', '\n'):
                return selected
            if key in ('\x1b', '\x03'):
                raise KeyboardInterrupt
            if key == ' ':
                selected.symmetric_difference_update({items[cursor]})
            elif key in ('j', 'k'):
                cursor = (cursor + (1 if key == 'j' else -1)) % len(items)
    write('Basic terminal fallback: enter comma-separated agent names; blank preserves selection.')
    value = input(', '.join(items) + ': ').strip()
    chosen = {s.strip() for s in value.split(',')} if value else selected
    if chosen - set(items):
        raise ValueError('Unknown agent selection')
    return chosen


def configure(hub, selected, policies=None):
    from copy import deepcopy
    from .platforms import FileLock
    with FileLock(hub.store.home / 'settings.lock'):
        ensure_idle(hub.store)
        value = json.loads((hub.store.home / 'config.json').read_text(encoding='utf-8'))
        if set(selected) - set(value['providers']):
            raise ValueError('Unknown selected provider')
        for name, entry in value['providers'].items():
            entry['enabled'] = name in selected
            if policies and name in policies:
                entry.update(policies[name])
            validate_entry(name, entry)
        backup = atomic_json(hub.store.home / 'config.json', value)
        hub.config = value
    return {'selected': sorted(selected), 'backup': backup,
            'coding_agent_configured': any(e['enabled'] and 'implement' in e['roles'] for e in value['providers'].values()),
            'security_changed': False}


def _run(hub, check=True):
    print('MULTI AGENTS — TERMINAL SETUP (no provider install/login or model call)')
    print('Python:', sys.version.split()[0], 'Home:', hub.store.home)
    import shutil
    if sys.version_info < (3, 11) or not shutil.which('git'):
        raise ValueError('Python >=3.11 and Git are required')
    results = discover(hub.config, check=check)
    for item in results:
        print(item['agent'], item['state'], item['version'], item['authentication'], 'roles=' + ','.join(item['roles']))
    selected = checkbox(list(hub.config['providers']),
                        [n for n, e in hub.config['providers'].items() if e.get('enabled')])
    policies = {}
    for name in sorted(selected):
        current = hub.config['providers'][name]
        choice = input(name + ' model policy [keep/INHERIT/AUTO/MANUAL]: ').strip().upper()
        if choice and choice != 'KEEP':
            entry = {'model_policy': choice}
            if choice == 'MANUAL':
                entry['model'] = input('Model id (must be in provider-reported catalog): ').strip()
                entry['model_catalog'] = next(r['model_catalog'] for r in results if r['agent'] == name)
            if choice == 'AUTO' and name != 'copilot':
                if input('AUTO unavailable. Allow INHERIT fallback? [y/N]: ').lower() == 'y':
                    entry['model_fallback'] = 'INHERIT'
            policies[name] = entry
        roles = input(name + ' roles (comma-separated, blank keeps current): ').strip()
        if roles:
            policies.setdefault(name, {})['roles'] = [s.strip() for s in roles.split(',')]
    print(json.dumps(configure(hub, selected, policies), ensure_ascii=False, indent=2))
    if os.name == 'nt' and input('Install owned ma launcher in user PATH? [y/N]: ').lower() == 'y':
        from .lifecycle import install_command
        print(install_command(hub.store.home))
    from .integrations import CLIENTS, install_client, integration_plan
    client = input('MCP client (' + ','.join(CLIENTS) + '; blank skips): ').strip()
    if client:
        print(json.dumps(integration_plan(hub.store.home, client), ensure_ascii=False, indent=2))
        if input('Apply this external client configuration with backup? [y/N]: ').lower() == 'y':
            print(install_client(hub.store.home, client, apply=True))
    print('Setup complete. No security flags changed. Next: cd <approved project>; ma init; ma')


def run(hub, check=True):
    """Roll back owned setup changes on failure; keep backups and all user data."""
    from .integrations import CLIENTS, remove_client
    from .lifecycle import uninstall
    from .config import load
    ensure_idle(hub.store)
    config_path = hub.store.home / 'config.json'
    before = json.loads(config_path.read_text(encoding='utf-8'))
    launcher_existed = (hub.store.home / 'runtime/installation.json').exists()
    integrations = {c: (hub.store.home / 'integrations' / (c + '.json')).exists() for c in CLIENTS}
    try:
        _run(hub, check)
    except BaseException:
        for client, existed in integrations.items():
            if not existed and (hub.store.home / 'integrations' / (client + '.json')).exists():
                try: remove_client(hub.store.home, client)
                except (ValueError, OSError): print('Rollback needs manual review for client:', client)
        if not launcher_existed and (hub.store.home / 'runtime/installation.json').exists():
            try: uninstall(hub.store.home)
            except (ValueError, OSError): print('Rollback needs manual review for owned launcher; data retained.')
        # All wizard config edits are operator choices, never security attestations.
        atomic_json(config_path, before)
        hub.config = load(hub.store.home)
        print('Setup did not complete. Prior Hub configuration restored; backups retained.')
        raise
