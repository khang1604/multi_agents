"""V2 commands reuse the existing Hub, Store, Engine and stdio server."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from .api import Hub
from .config import ROOT
from .settings import application_home, update_provider, effective_config, atomic_json, ensure_idle
from .registry import SPECS, discover
from .project_context import initialize, get_context, unregister, is_removed
from .service import start_daemon, stop_daemon, daemon_status
from .presentation import green, red, yellow, cyan, dim, bold, use_color


def output(value, json_mode=False):
    """Render bounded text or explicit JSON output for a CLI command."""
    from .presentation import compact
    print(json.dumps(value, ensure_ascii=False, indent=2) if json_mode else compact(value))


def agent_reason(row):
    """Explain only verified discovery facts, without echoing probe output."""
    if not row.get('enabled'):
        return 'Disabled in configuration'
    state = row.get('state', 'UNKNOWN')
    if state == 'NOT_INSTALLED':
        if row.get('agent') == 'copilot':
            return 'CLI missing; Chat available'
        return 'IDE found; CLI/PATH missing' if row.get('ide_installed') else 'CLI/PATH not found'
    if state == 'UNAVAILABLE':
        if row.get('cooldown_until'):
            return row.get('reason', 'In cooldown')
        return 'Version check failed' if row.get('reason') == 'Version probe failed' else 'CLI failed or timed out'
    if row.get('authentication') == 'NOT_AUTHENTICATED':
        return 'Not authenticated'
    if row.get('operator_confirmed'):
        return 'Operator confirmed AI use'
    if state == 'READY':
        return 'AI execution verified' if row.get('live_verified') else 'Ready; AI not tested'
    if state == 'AUTHENTICATED':
        return 'Adapter not detected'
    if state == 'INSTALLED' and row.get('authentication') == 'UNKNOWN' and not row.get('reason'):
        return 'Not checked: --check'
    return 'Authentication unverified'


def agent_table(rows):
    """Bounded terminal summary; the registry and JSON retain full diagnostics."""
    widths = (11, 3, 15, 7, 7, 26)

    def line(values):
        """Format one sanitized bounded row of the agent status table."""
        cells = []
        for value, width in zip(values, widths):
            clean = ''.join(c for c in str(value) if c.isprintable())
            if len(clean) > width:
                clean = clean[:width - 3] + '...'
            cells.append(clean.ljust(width))
        return '  '.join(cells).rstrip()

    header = line(('AGENT CLI', 'ON', 'STATE', 'AUTH', 'POLICY', 'REASON'))
    result = [bold(header)]
    for row in rows:
        auth_val = {'AUTHENTICATED': 'OK', 'NOT_AUTHENTICATED': 'NO'}.get(row.get('authentication'), 'UNKNOWN')
        plain_row = line((row['agent'], 'ON' if row.get('enabled') else 'OFF',
                          row.get('state', 'UNKNOWN'), auth_val, row.get('model_policy', 'INHERIT'), agent_reason(row)))
        if use_color():
            agent_col = cyan(row['agent'].ljust(widths[0]))
            on_val = ('ON' if row.get('enabled') else 'OFF').ljust(widths[1])
            on_col = green(on_val) if row.get('enabled') else dim(on_val)
            state_val = row.get('state', 'UNKNOWN').ljust(widths[2])
            state_col = green(state_val) if row.get('state') == 'READY' else red(state_val) if row.get('state') == 'NOT_INSTALLED' else yellow(state_val)
            auth_str = auth_val.ljust(widths[3])
            auth_col = green(auth_str) if auth_val == 'OK' else red(auth_str) if auth_val == 'NO' else yellow(auth_str)
            policy_col = row.get('model_policy', 'INHERIT').ljust(widths[4])
            reason_col = dim(agent_reason(row).ljust(widths[5]))
            result.append(f'{agent_col}  {on_col}  {state_col}  {auth_col}  {policy_col}  {reason_col}'.rstrip())
        else:
            result.append(plain_row)
    return '\n'.join(result)


def parser():
    """Build the command parser and supported operator options."""
    p = argparse.ArgumentParser(prog='ma', description='Multi Agents — terminal-first local orchestrator')
    p.add_argument('--home', default=str(application_home()), help='External local data home')
    sub = p.add_subparsers(dest='command')
    init = sub.add_parser('init', help='Initialize the current approved Git project; no source writes or AI')
    init.add_argument('path', nargs='?', default='.')
    init.add_argument('--name')
    verify = init.add_mutually_exclusive_group()
    verify.add_argument('--verify', help='JSON executable argument arrays')
    verify.add_argument('--verify-command', nargs=argparse.REMAINDER,
                        help='One verification command and its arguments; place this option last')
    init.add_argument('--refresh', action='store_true', help='Refresh changed local context; init is already idempotent')
    init.add_argument('--replace-verify', action='store_true', help='Explicitly replace the stored verifier, with backup; omitted command triggers detection')
    init.add_argument('--register-only', action='store_true', help='Register/refresh without interactive scope or baseline test; no ready claim')
    init.add_argument('--prepare', action='store_true', help='Confirm scope and run baseline checks; requires interactive terminal')
    setup = sub.add_parser('setup')
    setup.add_argument('view', nargs='?', choices=['interface'], help='Optional VS Code extension UI only; omit for cross-client terminal setup')
    setup.add_argument('--check', dest='check', action='store_true', default=True, help='Official version/auth probes (default); no model calls')
    setup.add_argument('--offline', dest='check', action='store_false', help='Resolve paths only; leave version/auth unknown')
    setup.add_argument('--advanced', action='store_true', help='Detailed model/provider/role setup')
    setup.add_argument('--plan', action='store_true', help='Read one-page setup choices without writes')
    setup.add_argument('--apply-options', help='Explicit JSON selections from the local setup UI')
    authentication = setup.add_mutually_exclusive_group()
    authentication.add_argument('--login', choices=SPECS, help='Open official interactive login; never reads auth files')
    authentication.add_argument('--logout', choices=SPECS, help='Open official sign-out; never edits auth files')
    setup.add_argument('--json', action='store_true')
    doc = sub.add_parser('doctor'); doc.add_argument('--offline', action='store_true')
    agents = sub.add_parser('agents'); ac = agents.add_subparsers(dest='action', required=True)
    ls = ac.add_parser('list'); ls.add_argument('--check', action='store_true')
    ls.add_argument('--json', action='store_true', help='Full registry details instead of the compact table')
    for action in ('enable', 'disable'):
        ap = ac.add_parser(action); ap.add_argument('agent', choices=SPECS); ap.add_argument('--project')
    models = ac.add_parser('models'); models.add_argument('agent', nargs='?', choices=SPECS)
    confirm = ac.add_parser('confirm'); confirm.add_argument('agent', choices=SPECS)
    choice = confirm.add_mutually_exclusive_group(required=True)
    choice.add_argument('--worked', action='store_true', help='Record readiness after your successful manual AI reply; no model call')
    choice.add_argument('--revoke', action='store_true', help='Remove your earlier confirmation')
    model = ac.add_parser('model'); model.add_argument('agent', choices=SPECS)
    model.add_argument('policy', choices=['INHERIT', 'AUTO', 'MANUAL']); model.add_argument('--model')
    model.add_argument('--fallback', choices=['INHERIT']); model.add_argument('--project')
    ac.add_parser('configure')
    rst = ac.add_parser('reset', help='Clear cooldown and health errors for one or all agents')
    rst.add_argument('agent', nargs='?', choices=SPECS)
    cfg = sub.add_parser('config'); cfg.add_argument('--allow-mcp-config', choices=['true', 'false'])
    cfg.add_argument('--default-client', choices=['antigravity', 'vscode', 'codex', 'copilot', 'claude', 'none'])
    project = sub.add_parser('projects'); pc = project.add_subparsers(dest='action', required=True)
    pc.add_parser('list')
    remove = pc.add_parser('remove'); remove.add_argument('project')
    context = sub.add_parser('context'); context.add_argument('project', nargs='?')
    run = sub.add_parser('run'); run.add_argument('request', nargs='+', help='Objective, or PROJECT OBJECTIVE with --project omitted')
    run.add_argument('--project'); run.add_argument('--mode', choices=['auto', 'small', 'standard', 'complex'], default='auto')
    run.add_argument('--max-calls', type=int); run.add_argument('--request-key')
    execution = run.add_mutually_exclusive_group()
    execution.add_argument('--no-start', action='store_true')
    execution.add_argument('--watch', action='store_true', help='Follow this workflow and display its final agent response; Ctrl+C stops watching only')
    accept = sub.add_parser('accept', help='Apply completed changes to project files; no commit')
    accept.add_argument('workflow_id', nargs='?')
    accept.add_argument('--file', action='append', dest='files', help='Accept only this delivery file; repeat for several files')
    accept.add_argument('--project', help='Require workflow to belong to this project')
    review = sub.add_parser('review', help='Read verified before/after snapshots; no model call')
    review.add_argument('workflow_id', nargs='?'); review.add_argument('--project')
    auto = sub.add_parser('auto-accept', help='Choose whether completed changes are applied automatically')
    auto.add_argument('value', choices=['on', 'off', 'status'])
    handoff = sub.add_parser('handoff', help='Read the saved handoff or explicitly allow one rejected next approach')
    handoff.add_argument('workflow_id', nargs='?')
    handoff.add_argument('--allow-approach'); handoff.add_argument('--reason')
    status = sub.add_parser('status'); status.add_argument('workflow_id', nargs='?'); status.add_argument('--watch', action='store_true'); status.add_argument('--json', action='store_true')
    for name in ('logs', 'diff', 'cancel', 'retry'):
        ap = sub.add_parser(name); ap.add_argument('workflow_id', nargs='?')
        if name == 'retry':
            ap.add_argument('--extra-calls', type=int, default=0)
            ap.add_argument('--at', help='Resume at ISO time with timezone, e.g. 2026-10-25T13:20:17+07:00')
            ap.add_argument('--request-key', help='Deduplicate a scheduled retry and its call grant')
            watch_group = ap.add_mutually_exclusive_group()
            watch_group.add_argument('--watch', action='store_true', help='Follow the retried workflow')
            watch_group.add_argument('--no-watch', action='store_true', help='Do not follow the retried workflow')
    for name in ('start', 'stop', 'restart'):
        sub.add_parser(name)
    op = sub.add_parser('open', help='Open the active workflow workspace or a specific file in your editor')
    op.add_argument('file', nargs='?', help='Relative file path to open (e.g. public/app.js); omit to open workspace root')
    op.add_argument('--workflow', dest='workflow_id', help='Workflow ID (defaults to latest for current project)')
    wake = sub.add_parser('wake', help='Check due queue without AI; optionally install Windows user watchdog')
    wake.add_argument('--install', action='store_true')
    wake.add_argument('--apply', action='store_true')
    mcp = sub.add_parser('mcp'); mcp.add_argument('--client', default='unknown')
    sub.add_parser('mcp-config')
    integration = sub.add_parser('integrations'); ic = integration.add_subparsers(dest='action', required=True)
    for name in ('command', 'install', 'remove'):
        ap = ic.add_parser(name); ap.add_argument('client', choices=['antigravity', 'vscode', 'codex', 'copilot', 'claude'])
        if name == 'install': ap.add_argument('--apply', action='store_true')
    chat = ic.add_parser('chat'); chat.add_argument('--apply', action='store_true', help='Install the owned @hub participant in VS Code')
    sub.add_parser('install-command')
    sub.add_parser('uninstall')
    update = sub.add_parser('update'); update.add_argument('--apply', action='store_true')
    migrate = sub.add_parser('migrate'); migrate.add_argument('--from', dest='source', required=True)
    demo = sub.add_parser('demo'); demo.add_argument('--simulate', action='store_true', required=True)
    def json_options(current):
        """Add explicit JSON-output options to applicable subcommands."""
        children = [action for action in current._actions if isinstance(action, argparse._SubParsersAction)]
        if children:
            for action in children:
                for child in action.choices.values():
                    json_options(child)
        elif '--json' not in current._option_string_actions:
            if current.prog.split()[-1] not in {'setup', 'configure', 'mcp', 'mcp-config'}:
                current.add_argument('--json', action='store_true', help='Full structured output')
    json_options(p)
    return p


def current_project(hub):
    """Resolve the registered project matching the current approved Git directory."""
    from .discovery import repository_root
    import os
    root = repository_root(Path.cwd())
    for row in hub.store.all('SELECT * FROM projects'):
        if os.path.normcase(str(Path(row['path']).resolve())) == os.path.normcase(str(root)) and not is_removed(hub.store.home, row['id']):
            return row['name']
    raise ValueError('Run ma init in this approved project first')


def latest(hub, workflow_id=None):
    """Select the latest saved workflow for the requested project."""
    if workflow_id:
        return workflow_id
    try:
        row = hub.store.project(current_project(hub))
        result = hub.store.one('SELECT id FROM workflows WHERE project_id=? ORDER BY updated DESC LIMIT 1', (row['id'],))
        if result:
            return result['id']
    except ValueError:
        pass
    result = hub.store.one('SELECT id FROM workflows ORDER BY updated DESC LIMIT 1')
    if not result:
        raise ValueError('No workflow recorded yet')
    return result['id']


def watch_workflow(hub, workflow_id, watch=False, json_mode=False, interactive_accept=False):
    """Render changed persisted state and the final answer without redispatching work."""
    from .monitor import ProgressView, render
    progress = ProgressView() if watch else None
    previous = None
    state = None
    try:
        while True:
            state = hub.status(workflow_id)
            signature = json.dumps(state, sort_keys=True, ensure_ascii=False)
            if signature != previous:
                if json_mode:
                    output(state, True)
                else:
                    message = progress.render(state) if progress else render(state)
                    if message:
                        print(message, flush=True)
                previous = signature
            if not watch or state['status'] in {'completed', 'blocked', 'cancelled', 'needs_review'}:
                break
            time.sleep(2)
        can_accept = False
        if watch and not json_mode and state and interactive_accept and sys.stdin.isatty():
            if state['status'] == 'completed':
                can_accept = True
            elif state['status'] == 'needs_review':
                evidence = state.get('verification') or {}
                if isinstance(evidence, str):
                    try: evidence = json.loads(evidence)
                    except (ValueError, TypeError): evidence = {}
                can_accept = bool(evidence.get('checks') and all(c.get('exit_code') == 0 for c in evidence['checks']))
        if can_accept:
            acceptance = state.get('acceptance', {})
            if acceptance.get('status') != 'accepted':
                changes = state.get('file_changes', {}).get('stats', [])
                num_files = len(changes) if changes else 0
                objective = state.get('objective', '')
                is_vn = bool(re.search(r'[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]', objective, re.I))
                if is_vn:
                    raw_prompt = f'\nÁp dụng {num_files} file đã thay đổi vào dự án ngay bây giờ? [Y/n]: ' if num_files else '\nÁp dụng các thay đổi vào dự án ngay bây giờ? [Y/n]: '
                else:
                    raw_prompt = f'\nApply {num_files} changed file(s) to project now? [Y/n]: ' if num_files else '\nApply changes to project now? [Y/n]: '
                prompt_msg = bold(yellow(raw_prompt))
                try:
                    answer = input(prompt_msg).strip().lower()
                    if answer in {'', 'y', 'yes'}:
                        if state['status'] == 'needs_review':
                            from .retention import archive_completed
                            hub.store.update(workflow_id, status='completed')
                            flow = hub.store.workflow(workflow_id)
                            if not flow.get('delivery'):
                                archive_completed(hub.store, flow, hub.config['retention'])
                        from .acceptance import accept
                        result = accept(hub.store, workflow_id)
                        applied = result.get('applied') or result.get('files', [])
                        success_msg = f'Đã áp dụng {len(applied)} file vào dự án thành công.' if is_vn else f'Applied {len(applied)} file(s) to project successfully.'
                        print(green(success_msg))
                    else:
                        retain_msg = f'Đã giữ lại các thay đổi. Chạy "ma accept" khi bạn sẵn sàng.' if is_vn else f'Changes retained. Run ma accept {workflow_id} when ready.'
                        print(dim(retain_msg))
                except (EOFError, KeyboardInterrupt):
                    pass
    except KeyboardInterrupt:
        print('Monitor closed; workflow continues independently.')


def open_in_editor(target):
    """Open a file or directory in VS Code / IDE or default system viewer."""
    import shutil
    target_str = str(target)
    code_bin = shutil.which('code') or shutil.which('cursor')
    if code_bin:
        try:
            subprocess.Popen([code_bin, target_str], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return 'editor'
        except OSError:
            pass
    if os.name == 'nt' and hasattr(os, 'startfile'):
        try:
            os.startfile(target_str)
            return 'startfile'
        except OSError:
            pass
    return 'path_only'


def menu(hub):
    """Run the interactive terminal menu without using a model for supervision."""
    while True:
        print('\nMULTI AGENTS — 1 Agents  2 Initialize here  3 Dispatch  4 Status  5 Configure  6 Setup  0 Exit')
        choice = input('Choose: ').strip()
        if choice == '0': return
        try:
            if choice == '1': print(agent_table(discover(hub.config, home=hub.store.home)))
            elif choice == '2': output(initialize(hub, Path.cwd()))
            elif choice == '3':
                project = current_project(hub)
                objective = input('Task: ').strip()
                output(hub.start(project, objective, uuid.uuid4().hex))
            elif choice == '4': output(hub.store.all('SELECT id,status,phase,leader,calls,max_calls FROM workflows ORDER BY updated DESC LIMIT 20'))
            elif choice in {'5', '6'}:
                from .wizard import run
                run(hub)
        except (ValueError, OSError) as error:
            print('Multi Agents:', error)


def normalize_argv(argv):
    """Prepend 'run' when a task objective is passed directly without a subcommand."""
    tokens = list(sys.argv[1:] if argv is None else argv)
    if not tokens:
        return tokens
    known = {'init', 'setup', 'doctor', 'agents', 'config', 'projects', 'context',
             'run', 'accept', 'review', 'auto-accept', 'handoff', 'status', 'logs',
             'diff', 'cancel', 'retry', 'start', 'stop', 'restart', 'open', 'wake', 'mcp',
             'mcp-config', 'integrations', 'chat', 'install-command', 'uninstall',
             'update', 'migrate', 'demo'}
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token == '--home':
            idx += 2
            continue
        if token.startswith('-'):
            idx += 1
            continue
        if token not in known:
            return tokens[:idx] + ['run'] + tokens[idx:]
        break
    return tokens


def main(argv=None):
    """Dispatch parsed CLI requests through the shared Hub and settings services."""
    norm_argv = normalize_argv(argv)
    args = parser().parse_args(norm_argv)
    def show(value):
        """Render a command result using the selected output mode."""
        output(value, getattr(args, 'json', False))
    if args.command == 'migrate':
        from .lifecycle import migrate_legacy
        show(migrate_legacy(args.source, args.home)); return
    if args.command == 'init':
        from .discovery import repository_root
        from .project_context import outside_repository
        outside_repository(args.home, repository_root(args.path))
    hub = Hub(args.home)
    command = args.command
    if command is None:
        if not sys.stdin.isatty():
            parser().print_help(); return
        menu(hub)
    elif command == 'init':
        checks = json.loads(args.verify) if args.verify else None
        if args.verify_command is not None:
            if not args.verify_command:
                raise ValueError('Provide an executable and its arguments after --verify-command')
            checks = [args.verify_command]
        interactive = sys.stdin.isatty() and sys.stdout.isatty() and not getattr(args, 'json', False) and not args.register_only
        if args.prepare and not interactive:
            raise ValueError('--prepare needs an interactive terminal for project scope confirmation')
        if interactive:
            from .readiness import initialize_interactive
            show(initialize_interactive(hub, args.path, args.name, checks, args.replace_verify))
        else:
            show(initialize(hub, args.path, args.name, checks, args.replace_verify))
    elif command == 'setup':
        from . import quick_setup
        if args.view:
            if args.plan or args.apply_options or args.login or args.logout or args.advanced or not args.check:
                raise ValueError('Use ma setup interface without terminal setup options')
            show(quick_setup.open_interface(hub))
        elif args.plan:
            show(quick_setup.plan(hub, args.check))
        elif args.apply_options:
            choices = json.loads(args.apply_options)
            if set(choices) != {'providers', 'actions'}:
                raise ValueError('Invalid setup options')
            show(quick_setup.apply(hub, choices['providers'], choices['actions']))
        elif args.login:
            if not sys.stdin.isatty():
                raise ValueError('Open official login in an interactive terminal')
            show(quick_setup.login(hub, args.login))
        elif args.logout:
            if not sys.stdin.isatty():
                raise ValueError('Open official sign-out in an interactive terminal')
            show(quick_setup.logout(hub, args.logout))
        elif args.advanced:
            from .wizard import run
            run(hub, args.check)
        else:
            quick_setup.terminal(hub, args.check)
    elif command == 'doctor':
        import shutil
        show({'python': sys.version.split()[0], 'git': shutil.which('git'), 'home': str(hub.store.home),
                'daemon': daemon_status(hub.store.home), 'agents': discover(hub.config, not args.offline, home=hub.store.home),
                'note': 'Auth status is not proof of quota or live execution. No IDE credential scraping.'})
    elif command == 'agents':
        if args.action == 'configure':
            from .wizard import run
            run(hub)
        elif args.action == 'list':
            rows = discover(hub.config, args.check, home=hub.store.home)
            if args.check: atomic_json(hub.store.home / 'agent-registry.json', rows)
            if args.json: show(rows)
            else: print(agent_table(rows))
        elif args.action == 'confirm':
            from .confirmations import confirm
            show(confirm(hub, args.agent, args.worked, args.revoke))
        elif args.action in {'enable', 'disable'}:
            show(update_provider(hub, args.agent, {'enabled': args.action == 'enable'}, args.project))
        elif args.action == 'models':
            from .registry import model_info
            show({n: model_info(hub.config, n, hub.store.home) for n in hub.config['providers'] if not args.agent or n == args.agent})
        elif args.action == 'model':
            changes = {'model_policy': args.policy, 'model': args.model, 'model_fallback': args.fallback}
            cache = hub.store.home / 'agent-registry.json'
            if cache.exists():
                rows = json.loads(cache.read_text(encoding='utf-8'))
                changes['model_catalog'] = next((r['model_catalog'] for r in rows if r['agent'] == args.agent), [])
            show(update_provider(hub, args.agent, changes, args.project))
        elif args.action == 'reset':
            with hub.store.connection() as db:
                if args.agent:
                    db.execute("UPDATE health SET until=0, reason='' WHERE provider=?", (args.agent,))
                else:
                    db.execute("UPDATE health SET until=0, reason=''")
            show({'status': 'ok', 'message': f"Reset health status for {args.agent or 'all providers'}"})
    elif command == 'config':
        if args.allow_mcp_config is not None or args.default_client is not None:
            from .platforms import FileLock
            with FileLock(hub.store.home / 'settings.lock'):
                ensure_idle(hub.store)
                if args.allow_mcp_config is not None:
                    hub.config.setdefault('permissions', {})['mcp_config_write'] = args.allow_mcp_config == 'true'
                if args.default_client is not None:
                    hub.config['default_client'] = None if args.default_client == 'none' else args.default_client
                atomic_json(hub.store.home / 'config.json', hub.config)
        show({'home': str(hub.store.home), 'security': hub.config['security'], 'auto': hub.config['auto'],
                'permissions': hub.config.get('permissions', {}), 'default_client': hub.config.get('default_client'),
                'note': 'Provider login credentials remain with each official CLI.'})
    elif command == 'projects':
        if args.action == 'remove': show(unregister(hub, args.project))
        else: show([p for p in hub.store.all('SELECT * FROM projects') if not is_removed(hub.store.home, p['id'])])
    elif command == 'context': show(get_context(hub, args.project or current_project(hub)))
    elif command == 'run':
        if args.project:
            project, objective = args.project, ' '.join(args.request)
        elif len(args.request) == 2 and hub.store.one('SELECT id FROM projects WHERE name=? OR id=?', (args.request[0], args.request[0])):
            project, objective = args.request
        else:
            project, objective = current_project(hub), ' '.join(args.request)
        flow = hub.start(project, objective, args.request_key or uuid.uuid4().hex, args.max_calls, args.mode, launch=not args.no_start)
        should_watch = args.watch or (sys.stdout.isatty() and not getattr(args, 'json', False) and not args.no_start)
        if should_watch:
            watch_workflow(hub, flow['id'], watch=True, json_mode=args.json, interactive_accept=sys.stdin.isatty())
        else:
            show(flow)
    elif command == 'status':
        if not args.workflow_id and not hub.store.one('SELECT id FROM workflows LIMIT 1'):
            show({'daemon': daemon_status(hub.store.home), 'workflows': []}); return
        watch_workflow(hub, latest(hub, args.workflow_id), args.watch, args.json, interactive_accept=sys.stdin.isatty())
    elif command in {'accept', 'review'}:
        from .acceptance import accept, preview
        workflow_id = latest(hub, args.workflow_id)
        flow = hub.store.workflow(workflow_id)
        if args.project and hub.store.project(args.project)['id'] != flow['project_id']:
            raise ValueError('Workflow belongs to another project')
        if flow['status'] in {'needs_review', 'completed'}:
            evidence = json.loads(flow.get('verification') or '{}')
            passed = evidence.get('checks') and all(c.get('exit_code') == 0 for c in evidence['checks'])
            if passed:
                if flow['status'] != 'completed':
                    hub.store.update(workflow_id, status='completed')
                    flow = hub.store.workflow(workflow_id)
                from .retention import archive_completed
                if not flow.get('delivery'):
                    archive_completed(hub.store, flow, hub.config['retention'])
                flow = hub.store.workflow(workflow_id)
        show(preview(hub.store, workflow_id) if command == 'review' else accept(hub.store, workflow_id, files=args.files))
    elif command == 'auto-accept':
        from .acceptance import mode
        show(mode(hub.store, current_project(hub), None if args.value == 'status' else args.value == 'on'))
    elif command == 'handoff':
        row = hub.store.workflow(latest(hub, args.workflow_id))
        if args.allow_approach:
            from .handoff import allow_approach
            message = allow_approach(hub.store, row['id'], args.allow_approach, args.reason)
            print(json.dumps({'message': message}, ensure_ascii=False) if args.json else message)
        else:
            saved = json.loads(row['handoff']).get('checkpoint', {})
            if args.json:
                show(saved)
            else:
                def short(value, limit=180):
                    """Return a compact representation for the current command view."""
                    return ''.join(char if char.isprintable() else ' ' for char in value)[:limit]
                rejected = [x['approach_id'] + ': ' + x['reason'] for x in saved.get('attempts', []) if x['status'] == 'rejected']
                print('Handoff v2 | revision ' + str(saved.get('revision', 0)) + '\nNext: ' + short(saved.get('next_action', {}).get('action', 'Not recorded')) + '\nRejected (' + str(len(rejected)) + '): ' + short('; '.join(rejected) or 'None recorded'))
    elif command == 'logs':
        show(hub.store.all('SELECT provider,phase,status,artifact,error,usage FROM attempts WHERE workflow_id=? ORDER BY created',
                           (latest(hub, args.workflow_id),)))
    elif command == 'diff':
        from .workspace import diff
        row = hub.store.workflow(latest(hub, args.workflow_id))
        if row.get('delivery') and not Path(row['workspace'] or '').exists():
            import zipfile
            with zipfile.ZipFile(row['delivery']) as archive:
                changes = archive.read('changes.patch').decode('utf-8', errors='replace')
        elif row['workspace']:
            changes = diff(row['workspace'])
        else:
            raise ValueError('Workflow has no worktree/delivery yet')
        if args.json: show({'patch': changes, 'delivery': row.get('delivery')})
        else: print(changes or 'No changes.')
    elif command == 'cancel': show(hub.store.cancel(latest(hub, args.workflow_id)))
    elif command == 'retry':
        workflow_id = latest(hub, args.workflow_id)
        flow = hub.store.workflow(workflow_id)
        extra_calls = args.extra_calls
        if extra_calls == 0 and flow['phase'] != 'verify' and flow['calls'] >= flow['max_calls']:
            extra_calls = 3
        scheduled = 0
        if args.at:
            from datetime import datetime
            parsed = datetime.fromisoformat(args.at)
            if parsed.tzinfo is None:
                raise ValueError('--at requires an explicit timezone')
            scheduled = parsed.timestamp()
        result = hub.retry(workflow_id, extra_calls,
                           not_before=scheduled, request_key=args.request_key)
        should_watch = args.watch or (not getattr(args, 'no_watch', False) and sys.stdout.isatty() and not args.json and scheduled <= time.time())
        if should_watch:
            watch_workflow(hub, workflow_id, watch=True, json_mode=args.json, interactive_accept=sys.stdin.isatty())
        else:
            show(result)
    elif command == 'open':
        workflow_id = latest(hub, args.workflow_id)
        flow = hub.store.workflow(workflow_id)
        project = hub.store.project(flow['project_id'])
        ws_path = Path(flow['workspace']) if flow.get('workspace') and Path(flow['workspace']).exists() else Path(project['path'])
        target = (ws_path / args.file).resolve() if args.file else ws_path.resolve()
        opened = open_in_editor(target)
        if args.json:
            show({'target': str(target), 'workspace': str(ws_path), 'opened': opened})
        else:
            print(green('Opened: ') + cyan(target))
    elif command == 'wake':
        from .wakeup import install, wake
        show(install(hub.store.home, apply=args.apply) if args.install else wake(hub.store.home))
    elif command in {'start', 'stop', 'restart'}:
        if command == 'restart':
            stop_daemon(hub.store.home)
            deadline = time.monotonic() + 15
            while daemon_status(hub.store.home) != 'stopped':
                if time.monotonic() > deadline: raise ValueError('Daemon still stopping; no duplicate daemon started')
                time.sleep(.2)
        show(stop_daemon(hub.store.home) if command == 'stop' else start_daemon(hub.store.home))
    elif command == 'mcp':
        from .mcp import serve
        serve(hub.store.home, client=args.client)
    elif command == 'mcp-config':
        from .integrations import server
        output({'mcpServers': {'multi_agents': server(hub.store.home, 'vscode')}}, True)
    elif command == 'integrations':
        if args.action == 'chat':
            from .chat_bridge import install
            show(install(hub.store.home, args.apply))
            return
        from .integrations import install_client, remove_client, integration_plan
        show(remove_client(hub.store.home, args.client) if args.action == 'remove' else
               install_client(hub.store.home, args.client, args.apply) if args.action == 'install' else integration_plan(hub.store.home, args.client))
    elif command == 'install-command':
        from .lifecycle import install_command
        show(install_command(hub.store.home))
    elif command == 'uninstall':
        from .lifecycle import uninstall
        ensure_idle(hub.store)
        show(uninstall(hub.store.home))
    elif command == 'update':
        from .lifecycle import update_source
        show(update_source(ROOT, args.apply))
    elif command == 'demo':
        from .simulation import simulate
        show(simulate())
