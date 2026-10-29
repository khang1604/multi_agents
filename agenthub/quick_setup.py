"""One-page setup choices; no model calls, credentials, or security attestations."""
import os
import subprocess
import sys

from .registry import SPECS, discover, discover_agent, execution_command
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
        raise ValueError('VS Code CLI not found. ma setup interface is VS Code-only; use ma setup in any terminal for other clients.')
    record = hub.store.home / 'integrations/vscode-chat.json'
    if not record.is_file():
        raise ValueError('Run ma setup first and select VS Code @hub; then retry ma setup interface')
    owned = json.loads(record.read_text(encoding='utf-8'))
    version = json.loads((ROOT / 'integrations/vscode-chat/package.json').read_text(encoding='utf-8'))['version']
    if owned.get('source') != str(ROOT) or owned.get('python') != sys.executable:
        raise ValueError('VS Code Hub uses another source/interpreter; use its matching ma command')
    if owned.get('version') != version:
        raise ValueError('Update the owned VS Code @hub extension through ma setup, reload VS Code, then retry. '
                         'For Antigravity, Codex, Claude or Copilot CLI, use ma setup in the terminal instead.')
    prefix, environment = code_command(executable)
    runner = runner or subprocess.run
    listed = runner(prefix + ['--list-extensions', '--show-versions'], capture_output=True,
                    encoding='utf-8', errors='replace', timeout=40, env=environment)
    if listed.returncode or (EXTENSION_ID + '@' + version).lower() not in listed.stdout.lower().splitlines():
        raise ValueError('Hub extension missing/outdated in the default VS Code profile; run ma setup and select VS Code @hub')
    result = runner(prefix + ['--open-url', '--reuse-window', 'vscode://' + EXTENSION_ID + '/setup'],
                    capture_output=True, encoding='utf-8', errors='replace', timeout=40, env=environment)
    if result.returncode:
        raise ValueError('VS Code could not open setup; use Ctrl+Shift+P → Multi Agents: Quick Setup')
    return {'status': 'Setup request sent to VS Code; select choices and click Apply.',
            'note': 'If not visible, reload VS Code and use Ctrl+Shift+P → Multi Agents: Quick Setup. No settings applied.'}


def plan(hub, check=True):
    """Scan CLI status and describe current setup choices without applying integrations."""
    import shutil
    if sys.version_info < (3, 11) or not shutil.which('git'):
        raise ValueError('Python >=3.11 and Git are required')
    rows = discover(hub.config, check=check, home=hub.store.home)
    return {'agents': [{key: row.get(key) for key in ('agent', 'enabled', 'state', 'authentication', 'version', 'reason',
                          'authentication_checked_at', 'operator_confirmed', 'live_verified')}
                       for row in rows], 'policy': 'INHERIT', 'security_changed': False,
            'actions': {'launcher': (hub.store.home / 'runtime/installation.json').exists(),
                        'chat': (hub.store.home / 'integrations/vscode-chat.json').exists(),
                        'mcp': (hub.store.home / 'integrations/vscode.json').exists(), 'wake': False}}


def login(hub, provider, runner=None, status_runner=None):
    """Reuse verified authentication or open the selected official interactive login flow."""
    if os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot open operator login')
    if provider not in SPECS:
        raise ValueError('Unknown provider')
    ensure_idle(hub.store)
    if runner is None or status_runner is not None:
        status = discover_agent(provider, hub.config['providers'][provider], check=True, runner=status_runner)
        if status['authentication'] == 'AUTHENTICATED':
            return {'provider': provider, 'authentication': 'AUTHENTICATED', 'login_skipped': True,
                    'note': 'Already authenticated; no login process was opened.'}
    args = {'codex': ['login'], 'claude': ['auth', 'login'], 'copilot': ['login'], 'antigravity': []}[provider]
    import tempfile
    with tempfile.TemporaryDirectory(prefix='ma-login-') as cwd:
        result = (runner or subprocess.run)(execution_command(provider, hub.config['providers'][provider]) + args, **({'cwd': cwd} if runner is None else {}))
    return {'provider': provider, 'login_exit': result.returncode, 'authentication': 'UNKNOWN',
            'note': 'Official login finished; use Check again. Exit 0 does not certify authentication or quota.'}


def logout(hub, provider, runner=None):
    """Operator-only official sign-out; never edit provider credential files."""
    import tempfile
    from .authentication import forget_status
    if os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot sign out providers')
    if provider not in SPECS:
        raise ValueError('Unknown provider')
    ensure_idle(hub.store)
    args = {'codex': ['logout'], 'claude': ['auth', 'logout'],
            'copilot': [], 'antigravity': []}[provider]
    command = execution_command(provider, hub.config['providers'][provider]) + args
    interactive = not args
    if interactive and runner is None:
        print('In the official CLI, enter /logout to sign out, then exit the CLI. Hub will check status again.', flush=True)
    forget_status(hub.store.home, provider)
    with tempfile.TemporaryDirectory(prefix='ma-logout-') as cwd:
        result = (runner or subprocess.run)(command, **({'cwd': cwd} if runner is None else {}))
    return {'provider': provider, 'logout_exit': result.returncode, 'authentication': 'UNKNOWN',
            'interactive': interactive,
            'note': 'Sign-out process ended; check official authentication status again. Exit 0 is not proof of sign-out.'}


def apply(hub, providers, actions):
    """Apply only validated operator-selected providers and integrations with rollback support."""
    if os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot apply global setup')
    from .integrations import CLIENTS
    allowed = {'launcher', 'chat', 'mcp', 'wake'} | {'mcp:' + client for client in CLIENTS}
    if (not isinstance(providers, list) or not providers or any(name not in SPECS for name in providers)
            or not isinstance(actions, dict) or set(actions) - allowed
            or any(type(value) is not bool for value in actions.values())):
        raise ValueError('Invalid quick setup selection')
    if actions.get('wake') and os.name != 'nt':
        raise ValueError('Automatic Windows queue wake is not available on this platform')
    ensure_idle(hub.store)
    from .wizard import configure, run
    def perform(current):
        """Apply the validated setup choices through existing installation services."""
        result = configure(current, providers, {name: {'model_policy': 'INHERIT', 'model': None, 'model_fallback': None}
                                                for name in providers})
        if actions.get('launcher'):
            from .lifecycle import install_command
            result['launcher'] = install_command(current.store.home)
        if actions.get('mcp'):
            from .integrations import install_client
            result['mcp'] = install_client(current.store.home, 'vscode', apply=True)
        for client in CLIENTS:
            if actions.get('mcp:' + client) and not (client == 'vscode' and actions.get('mcp')):
                from .integrations import install_client
                result['mcp:' + client] = install_client(current.store.home, client, apply=True)
        if actions.get('chat'):
            from .chat_bridge import install
            result['chat'] = install(current.store.home, apply=True)
        if actions.get('wake'):
            from .wakeup import install
            result['wake'] = install(current.store.home, apply=True)
        result['model_policy'] = 'INHERIT'
        result['next'] = 'cd <approved project>; ma init; ma run "PROMPT" (or use your selected MCP client)'
        return result
    return run(hub, check=False, action=perform)


def terminal(hub, check=True):
    """Run the terminal Quick Setup selection flow and optional official logins."""
    from .wizard import checkbox, login_selected
    print('MULTI AGENTS — QUICK SETUP | Enter applies selected options; Esc cancels.')
    print('Model: INHERIT for all agents; preserve suitable roles. Customize: ma setup --advanced')
    value = plan(hub, check)
    for row in value['agents']:
        print(row['agent'], row['state'], row['authentication'])
    from .integrations import CLIENTS
    print('Terminal use needs no editor extension. Select MCP clients explicitly; VS Code @hub is optional.')
    actions = {'Install the ma command': 'launcher',
               **{'Connect ' + ('VS Code' if client == 'vscode' else client.capitalize()) + ' MCP': 'mcp:' + client
                  for client in CLIENTS},
               'Connect VS Code @hub (optional extension)': 'chat'}
    if os.name == 'nt':
        actions['Automatic queue wake'] = 'wake'
    selected = [name for name, entry in hub.config['providers'].items() if entry.get('enabled')]
    # Existing integrations are not consent to configure them in another editor.
    selected += [label for label, key in actions.items() if key == 'launcher' and value['actions'].get(key)]
    chosen = checkbox(list(SPECS) + list(actions), selected)
    result = apply(hub, [name for name in SPECS if name in chosen], {key: label in chosen for label, key in actions.items()})
    from .presentation import compact
    print(compact(result))
    if check:
        login_selected(hub, [name for name in SPECS if name in chosen])
    print('Setup complete. Next: cd project; ma init; ma run "PROMPT", or use your selected MCP client.')
