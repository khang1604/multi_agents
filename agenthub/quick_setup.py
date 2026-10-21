"""One-page setup choices; no model calls, credentials, or security attestations."""
import os
import subprocess
import sys

from .registry import SPECS, discover, execution_command
from .settings import ensure_idle


def open_interface(hub, runner=None):
    """Open only the fixed setup URI; never apply choices or install implicitly."""
    import json
    import shutil
    from .chat_bridge import EXTENSION_ID, code_command
    from .config import ROOT
    if os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot open operator setup')
    executable = shutil.which('code')
    if not executable:
        raise ValueError('VS Code CLI not found; add its bin directory to PATH, then retry ma setup interface')
    record = hub.store.home / 'integrations/vscode-chat.json'
    if not record.is_file():
        raise ValueError('Run ma setup first and select VS Code @hub; then retry ma setup interface')
    owned = json.loads(record.read_text(encoding='utf-8'))
    version = json.loads((ROOT / 'integrations/vscode-chat/package.json').read_text(encoding='utf-8'))['version']
    if owned.get('source') != str(ROOT) or owned.get('python') != sys.executable:
        raise ValueError('VS Code Hub uses another source/interpreter; use its matching ma command')
    if owned.get('version') != version:
        raise ValueError('Update the owned VS Code @hub extension through ma setup, reload VS Code, then retry')
    prefix, environment = code_command(executable)
    runner = runner or subprocess.run
    listed = runner(prefix + ['--list-extensions', '--show-versions'], capture_output=True,
                    encoding='utf-8', errors='replace', timeout=40, env=environment)
    if listed.returncode or (EXTENSION_ID + '@' + version).lower() not in listed.stdout.lower().splitlines():
        raise ValueError('Hub extension missing/outdated in the default VS Code profile; run ma setup and select VS Code @hub')
    result = runner(prefix + ['--open-url', '--reuse-window', 'vscode://' + EXTENSION_ID + '/setup'],
                    capture_output=True, encoding='utf-8', errors='replace', timeout=40, env=environment)
    if result.returncode:
        raise ValueError('VS Code could not open setup; use Ctrl+Shift+P → Multi Agents: Setup nhanh')
    return {'status': 'Setup request sent to VS Code; select choices and click Áp dụng.',
            'note': 'If not visible, reload VS Code and use Ctrl+Shift+P → Multi Agents: Setup nhanh. No settings applied.'}


def plan(hub, check=True):
    import shutil
    if sys.version_info < (3, 11) or not shutil.which('git'):
        raise ValueError('Python >=3.11 and Git are required')
    rows = discover(hub.config, check=check, home=hub.store.home)
    return {'agents': [{key: row.get(key) for key in ('agent', 'enabled', 'state', 'authentication', 'version', 'reason')}
                       for row in rows], 'policy': 'INHERIT', 'security_changed': False,
            'actions': {'launcher': (hub.store.home / 'runtime/installation.json').exists(),
                        'chat': (hub.store.home / 'integrations/vscode-chat.json').exists(),
                        'mcp': (hub.store.home / 'integrations/vscode.json').exists(), 'wake': False}}


def login(hub, provider, runner=None):
    if os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot open operator login')
    if provider not in SPECS:
        raise ValueError('Unknown provider')
    ensure_idle(hub.store)
    args = {'codex': ['login'], 'claude': ['auth', 'login'], 'copilot': ['login'], 'antigravity': []}[provider]
    result = (runner or subprocess.run)(execution_command(provider, hub.config['providers'][provider]) + args)
    return {'provider': provider, 'login_exit': result.returncode, 'authentication': 'UNKNOWN',
            'note': 'Official login finished; use Check again. Exit 0 does not certify authentication or quota.'}


def apply(hub, providers, actions):
    if os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot apply global setup')
    if (not isinstance(providers, list) or not providers or any(name not in SPECS for name in providers)
            or not isinstance(actions, dict) or set(actions) - {'launcher', 'chat', 'mcp', 'wake'}
            or any(type(value) is not bool for value in actions.values())):
        raise ValueError('Invalid quick setup selection')
    if actions.get('wake') and os.name != 'nt':
        raise ValueError('Automatic Windows queue wake is not available on this platform')
    ensure_idle(hub.store)
    from .wizard import configure, run
    def perform(current):
        result = configure(current, providers, {name: {'model_policy': 'INHERIT', 'model': None, 'model_fallback': None}
                                                for name in providers})
        if actions.get('launcher'):
            from .lifecycle import install_command
            result['launcher'] = install_command(current.store.home)
        if actions.get('mcp'):
            from .integrations import install_client
            result['mcp'] = install_client(current.store.home, 'vscode', apply=True)
        if actions.get('chat'):
            from .chat_bridge import install
            result['chat'] = install(current.store.home, apply=True)
        if actions.get('wake'):
            from .wakeup import install
            result['wake'] = install(current.store.home, apply=True)
        result['model_policy'] = 'INHERIT'
        result['next'] = 'cd <approved project>; ma init; @hub PROMPT'
        return result
    return run(hub, check=False, action=perform)


def terminal(hub, check=True):
    from .wizard import checkbox, login_selected
    print('MULTI AGENTS — SETUP NHANH | Enter áp dụng các mục đã tick; Esc hủy.')
    print('Model: INHERIT cho tất cả; giữ vai trò phù hợp. Tùy chỉnh: ma setup --advanced')
    value = plan(hub, check)
    for row in value['agents']:
        print(row['agent'], row['state'], row['authentication'])
    actions = {'Cài lệnh ma': 'launcher', 'Kết nối VS Code @hub': 'chat', 'Kết nối VS Code MCP': 'mcp'}
    if os.name == 'nt':
        actions['Đánh thức hàng đợi tự động'] = 'wake'
    selected = [name for name, entry in hub.config['providers'].items() if entry.get('enabled')]
    selected += [label for label, key in actions.items() if value['actions'].get(key)]
    chosen = checkbox(list(SPECS) + list(actions), selected)
    result = apply(hub, [name for name in SPECS if name in chosen], {key: label in chosen for label, key in actions.items()})
    from .presentation import compact
    print(compact(result))
    if check:
        login_selected(hub, [name for name in SPECS if name in chosen])
    print('Setup xong. Tiếp theo: cd project; ma init; @hub PROMPT')
