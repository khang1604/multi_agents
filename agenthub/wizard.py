"""Standard-library terminal checkbox and transactional setup configuration."""
import json
import os
from pathlib import Path
import sys

from .registry import discover, validate_entry, SPECS
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


def choose_policy(config, selected, results, ask, write, label='All selected agents'):
    """Choose one policy for a group; validate before proceeding, not at final save."""
    while True:
        choice = ask(label + ' model policy [KEEP/INHERIT/AUTO/MANUAL] (Enter=KEEP): ').strip().upper() or 'KEEP'
        if choice == 'KEEP':
            return {}
        if choice not in {'INHERIT', 'AUTO', 'MANUAL'}:
            write('Choose KEEP, INHERIT, AUTO or MANUAL. No settings have been saved.')
            continue
        policies = {name: {'model_policy': choice, 'model': None, 'model_fallback': None} for name in selected}
        if choice == 'AUTO':
            unsupported = [name for name in selected if not SPECS[name]['auto']]
            if unsupported:
                write('Native AUTO is unavailable for: ' + ', '.join(unsupported))
                if ask('Allow Provider Default (INHERIT) fallback for all of them? [y/N]: ').strip().lower() not in {'y', 'yes'}:
                    write('AUTO was not applied. Choose another common policy or explicitly allow fallback.')
                    continue
                for name in unsupported:
                    policies[name]['model_fallback'] = 'INHERIT'
        if choice == 'MANUAL':
            model = ask('Shared model id (must be supported by every selected agent): ').strip()
            for name in selected:
                catalog = next((row.get('model_catalog', []) for row in results if row['agent'] == name), [])
                policies[name].update(model=model, model_catalog=catalog)
        errors = []
        for name in selected:
            try:
                validate_entry(name, {**config['providers'][name], **policies[name]})
            except ValueError as error:
                errors.append(name + ': ' + str(error))
        if errors:
            write('\n'.join(errors))
            write('Common policy was not applied. Use INHERIT, or keep current settings and customize individual agents.')
            continue
        return policies


def collect_preferences(config, selected, results, ask=None, write=print):
    ask = ask or input
    names = sorted(selected)
    if not names:
        return {}
    write('Choose the model policy ONCE for all selected agents: ' + ', '.join(names))
    write('INHERIT uses each CLI default; it does not force the same model id across providers.')
    policies = choose_policy(config, names, results, ask, write)
    for name in names:
        write(name + ' roles: ' + ', '.join(config['providers'][name]['roles']) + ' (kept automatically)')
    if ask('Advanced: customize individual agents/model policies/roles? [y/N]: ').strip().lower() not in {'y', 'yes'}:
        return policies
    for name in names:
        if ask('Customize ' + name + '? [y/N]: ').strip().lower() not in {'y', 'yes'}:
            continue
        current = {'providers': {name: {**config['providers'][name], **policies.get(name, {})}}}
        override = choose_policy(current, [name], results, ask, write, label=name)
        if override:
            policies.setdefault(name, {}).update(override[name])
        allowed = SPECS[name]['roles']
        while True:
            roles = ask(name + ' roles [' + ','.join(allowed) + '] (nhan Enter de giu nguyen): ').strip().lower()
            if roles in {'', 'keep', 'default', 'blank keeps current', 'giữ nguyên', 'giu nguyen'}:
                break
            values = list(dict.fromkeys(s.strip() for s in roles.split(',')))
            if not values or set(values) - set(allowed):
                write('Invalid roles. Allowed: ' + ', '.join(allowed) + '. Press Enter to keep current roles.')
                continue
            policies.setdefault(name, {})['roles'] = values
            break
    return policies


def login_selected(hub, selected, ask=None, write=print, runner=None, discoverer=None):
    """Interactive official login only; never inspect auth files or infer success from exit 0."""
    import subprocess
    from .registry import discover_agent, execution_command
    ask = ask or input
    runner = runner or subprocess.run
    discoverer = discoverer or discover_agent
    names = sorted(selected)
    commands = {'codex': ['login'], 'claude': ['auth', 'login'], 'copilot': ['login'], 'antigravity': []}
    while names:
        rows = [discoverer(name, hub.config['providers'][name], check=True) for name in names]
        if all(row.get('authentication') == 'AUTHENTICATED' for row in rows):
            write('Các CLI đã chọn đều có xác nhận đăng nhập từ provider.')
            return rows
        for number, row in enumerate(rows, 1):
            auth = row.get('authentication', 'UNKNOWN')
            label = 'Đã đăng nhập' if auth == 'AUTHENTICATED' else 'Chưa đăng nhập' if auth == 'NOT_AUTHENTICATED' else 'Chưa xác minh đăng nhập'
            if row['state'] == 'NOT_INSTALLED':
                label = 'Chưa cài CLI/PATH'
            write(f'{number}. {row["agent"]} CLI: {label}')
        write('CLI chưa có probe auth giữ UNKNOWN; mở login không tự chứng minh còn quota.')
        choice = ask('Chọn số để đăng nhập tại đây; 0 tiếp tục setup: ').strip()
        if choice == '0':
            return rows
        if not choice.isdigit() or not 1 <= int(choice) <= len(names):
            write('Chọn đúng số trong danh sách hoặc 0.')
            continue
        row = rows[int(choice) - 1]
        if row['state'] == 'NOT_INSTALLED':
            write('Cài CLI chính thức trước; setup không tự cài provider.')
            continue
        name = row['agent']
        write('Mở đăng nhập chính thức của ' + name + '; hoàn tất rồi thoát CLI để quay lại setup. Không gửi token cho Hub.')
        try:
            # Inherit the human terminal for browser/device flow. No capture, shell or credentials.
            result = runner(execution_command(name, hub.config['providers'][name]) + commands[name])
            if result.returncode:
                write('Login chưa hoàn tất; kiểm tra thông báo của CLI. Cấu hình và sandbox được giữ nguyên.')
        except (OSError, subprocess.SubprocessError):
            write('Không mở được login CLI; kiểm tra cài đặt/PATH.')
    return []


def _run(hub, check=True):
    print('MULTI AGENTS — TERMINAL SETUP (official CLI login menu; no model calls)')
    print('Python:', sys.version.split()[0], 'Home:', hub.store.home)
    import shutil
    if sys.version_info < (3, 11) or not shutil.which('git'):
        raise ValueError('Python >=3.11 and Git are required')
    results = discover(hub.config, check=check, home=hub.store.home)
    for item in results:
        print(item['agent'], item['state'], item['version'], item['authentication'], 'roles=' + ','.join(item['roles']))
    selected = checkbox(list(hub.config['providers']),
                        [n for n, e in hub.config['providers'].items() if e.get('enabled')])
    if check:
        results = login_selected(hub, selected)
    policies = collect_preferences(hub.config, selected, results)
    from .presentation import compact
    print(compact(configure(hub, selected, policies)))
    install_queue_wake = False
    launcher_question = ('Install owned ma launcher and automatic queue wake? [y/N]: ' if os.name == 'nt'
                         else 'Install owned ma launcher (no shell profile changes)? [y/N]: ')
    if input(launcher_question).strip().lower() in {'y', 'yes'}:
        from .lifecycle import install_command
        print(compact(install_command(hub.store.home)))
        install_queue_wake = os.name == 'nt'
    from .integrations import CLIENTS, install_client, integration_plan
    client = input('MCP client (' + ','.join(CLIENTS) + '; blank skips): ').strip()
    if client:
        print(compact(integration_plan(hub.store.home, client)))
        if input('Apply this external client configuration with backup? [y/N]: ').lower() == 'y':
            print(compact(install_client(hub.store.home, client, apply=True)))
    if input('Install @hub directly in VS Code Copilot Chat (no intermediary model)? [y/N]: ').strip().lower() in {'y', 'yes'}:
        from .chat_bridge import install
        print(compact(install(hub.store.home, apply=True)))
    if install_queue_wake:
        from .wakeup import install as install_wakeup
        print(compact(install_wakeup(hub.store.home, apply=True)))
    print('Setup complete. Next: cd <approved project>; ma init; then Copilot Chat: @hub PROMPT')


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
