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


def _agent_submenu(hub, providers):
    """Sub-menu for enabling/disabling agents or triggering login."""
    from .presentation import bold, cyan, green, yellow, dim
    while True:
        print()
        print(bold('--- AGENTS & ROLES CONFIGURATION ---'))
        for idx, name in enumerate(providers, 1):
            enabled = hub.config['providers'].get(name, {}).get('enabled', False)
            status = green('[Enabled]') if enabled else dim('[Disabled]')
            roles = ', '.join(hub.config['providers'].get(name, {}).get('roles', []))
            print(f"  {idx}. {cyan(name):<15} {status}  Roles: {roles}")
        print()
        print("Enter agent number (1-4) to toggle, or press Enter to return.")
        try:
            val = input('Choice: ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not val:
            break
        if val.isdigit() and 1 <= int(val) <= len(providers):
            target = providers[int(val) - 1]
            cur = hub.config['providers'].get(target, {}).get('enabled', False)
            hub.config['providers'][target]['enabled'] = not cur
            state_str = 'enabled' if not cur else 'disabled'
            print(green(f"Agent '{target}' is now {state_str}."))
        else:
            print(yellow('Invalid choice.'))


def _limits_submenu(hub):
    """Sub-menu for task safety budget."""
    from .presentation import bold, green, yellow
    while True:
        std_budget = hub.config.get('auto', {}).get('standard', {})
        max_calls = std_budget.get('max_calls', 6)
        max_repairs = std_budget.get('max_repairs', 3)
        print()
        print(bold('--- ACCEPTANCE & SAFETY LIMITS ---'))
        print(f"  1. Standard Task Max Calls:   {max_calls}")
        print(f"  2. Max Verification Repairs:  {max_repairs}")
        print(f"  3. Acceptance Mode:           Interactive Diff Preview & Confirmation [Y/n]")
        print()
        print("Enter 1 or 2 to adjust, or press Enter to return.")
        try:
            val = input('Choice: ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not val:
            break
        if val == '1':
            try:
                new_val = input(f'Enter max calls (current: {max_calls}): ').strip()
                if new_val.isdigit() and int(new_val) > 0:
                    hub.config['auto']['standard']['max_calls'] = int(new_val)
                    print(green(f"Updated standard max calls to {new_val}."))
            except (EOFError, KeyboardInterrupt):
                break
        elif val == '2':
            try:
                new_val = input(f'Enter max repairs (current: {max_repairs}): ').strip()
                if new_val.isdigit() and int(new_val) >= 0:
                    hub.config['auto']['standard']['max_repairs'] = int(new_val)
                    print(green(f"Updated max repairs to {new_val}."))
            except (EOFError, KeyboardInterrupt):
                break
        else:
            print(yellow('Invalid choice.'))


def _integrations_submenu(hub, actions_enabled):
    """Sub-menu for tool and IDE integrations."""
    from .presentation import bold, green, yellow, dim
    from .integrations import CLIENTS
    while True:
        print()
        print(bold('--- IDE & TOOL INTEGRATIONS ---'))
        for idx, client in enumerate(CLIENTS, 1):
            key = 'mcp:' + client
            status = green('[Enabled]') if actions_enabled.get(key) else dim('[Disabled]')
            print(f"  {idx}. Connect {client.capitalize()} MCP {status}")
        print()
        print("Enter number to toggle MCP integration, or press Enter to return.")
        try:
            val = input('Choice: ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not val:
            break
        if val.isdigit() and 1 <= int(val) <= len(CLIENTS):
            client = CLIENTS[int(val) - 1]
            key = 'mcp:' + client
            actions_enabled[key] = not actions_enabled.get(key, False)
            state_str = 'enabled' if actions_enabled[key] else 'disabled'
            print(green(f"MCP client '{client}' is now {state_str}."))
        else:
            print(yellow('Invalid choice.'))


def terminal(hub, check=True):
    """Run the clean interactive dashboard menu for Multi Agents configuration."""
    from .presentation import green, cyan, yellow, dim, bold
    from .integrations import CLIENTS
    from .lifecycle import install_command

    providers = list(SPECS)
    actions_enabled = {'launcher': True}
    for client in CLIENTS:
        actions_enabled['mcp:' + client] = False
    actions_enabled['chat'] = False

    while True:
        enabled_list = [p for p in providers if hub.config['providers'].get(p, {}).get('enabled')]
        leader_str = ', '.join(hub.config.get('leader_priority', []))
        worker_str = ', '.join(hub.config.get('worker_priority', []))
        reviewer_str = ', '.join(hub.config.get('reviewer_priority', []))
        auto_budgets = hub.config.get('auto', {})
        std_budget = auto_budgets.get('standard', {})
        max_calls = std_budget.get('max_calls', 6)
        max_repairs = std_budget.get('max_repairs', 3)
        launcher_installed = (hub.store.home / 'runtime/bin/ma').exists() or (hub.store.home / 'runtime/bin/ma.cmd').exists()

        print()
        print(bold('================================================================================'))
        print(bold('                    MULTI AGENTS — CONFIGURATION DASHBOARD                      '))
        print(bold('================================================================================'))
        print(cyan('[1] Agents & Roles'))
        print(f"    • Lead Analyst:   {leader_str}")
        print(f"    • Active Workers: {worker_str}")
        print(f"    • Reviewers:      {reviewer_str}")
        print(f"    • Enabled Agents: {', '.join(enabled_list) if enabled_list else 'none'}")
        print()
        print(cyan('[2] Acceptance & Safety Limits'))
        print(f"    • Acceptance Mode: Interactive Diff preview & [Y/n] confirmation")
        print(f"    • Budget Limits:   Standard task max calls: {max_calls} / repairs: {max_repairs}")
        print(f"    • Workspace Mode:  Isolated worktrees & shadow repo support enabled")
        print()
        print(cyan('[3] IDE & Tool Integrations'))
        print(f"    • Command Launcher (ma): {'Installed' if launcher_installed else 'Will be installed'}")
        print(f"    • Available MCP:         VS Code, Claude, Codex, Copilot")
        print(f"    • VS Code @hub:          Available")
        print()
        print(green('[0] Save & Finish') + dim(' (Press Enter to apply recommended settings)'))
        print(bold('================================================================================'))

        if not sys.stdin.isatty():
            choice = '0'
        else:
            try:
                choice = input('Select option [0-3] (Default: 0): ').strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

        if choice in ('0', ''):
            active_providers = [p for p in providers if hub.config['providers'].get(p, {}).get('enabled')]
            if not active_providers:
                active_providers = list(SPECS)
                for p in active_providers:
                    hub.config['providers'][p]['enabled'] = True
            apply(hub, active_providers, actions_enabled)
            try:
                install_command(hub.store.home)
            except Exception:
                pass
            print()
            print(green('✔ Setup completed successfully!'))
            print(green('✔ All settings applied. You can now run \'ma "<prompt>"\' in any project directory.'))
            print()
            break
        elif choice == '1':
            _agent_submenu(hub, providers)
        elif choice == '2':
            _limits_submenu(hub)
        elif choice == '3':
            _integrations_submenu(hub, actions_enabled)
        else:
            print(yellow('Please enter a valid option (0-3).'))
