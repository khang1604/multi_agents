"""V2 commands reuse the existing Hub, Store, Engine and stdio server."""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

from .api import Hub
from .config import ROOT
from .settings import application_home, update_provider, effective_config, atomic_json, ensure_idle
from .registry import SPECS, discover
from .project_context import initialize, get_context, unregister, is_removed
from .service import start_daemon, stop_daemon, daemon_status


def output(value, json_mode=False):
    from .presentation import compact
    print(json.dumps(value, ensure_ascii=False, indent=2) if json_mode else compact(value))


def agent_reason(row):
    """Explain only verified discovery facts, without echoing probe output."""
    if not row.get('enabled'):
        return 'Đã tắt trong cấu hình'
    state = row.get('state', 'UNKNOWN')
    if state == 'NOT_INSTALLED':
        if row.get('agent') == 'copilot':
            return 'Thiếu CLI; Chat vẫn dùng'
        return 'Có IDE, thiếu CLI/PATH' if row.get('ide_installed') else 'Không tìm thấy CLI/PATH'
    if state == 'UNAVAILABLE':
        if row.get('cooldown_until'):
            return row.get('reason', 'Đang cooldown')
        return 'Lỗi kiểm tra phiên bản' if row.get('reason') == 'Version probe failed' else 'CLI lỗi hoặc timeout'
    if row.get('authentication') == 'NOT_AUTHENTICATED':
        return 'Chưa đăng nhập'
    if row.get('operator_confirmed'):
        return 'Bạn xác nhận chạy AI'
    if state == 'READY':
        return 'Đã xác minh chạy AI' if row.get('live_verified') else 'Sẵn sàng; chưa thử AI'
    if state == 'AUTHENTICATED':
        return 'Chưa nhận diện adapter'
    if state == 'INSTALLED' and row.get('authentication') == 'UNKNOWN' and not row.get('reason'):
        return 'Chưa kiểm tra: --check'
    return 'Chưa xác minh đăng nhập'


def agent_table(rows):
    """Bounded terminal summary; the registry and JSON retain full diagnostics."""
    widths = (11, 3, 15, 7, 7, 26)

    def line(values):
        cells = []
        for value, width in zip(values, widths):
            clean = ''.join(c for c in str(value) if c.isprintable())
            if len(clean) > width:
                clean = clean[:width - 3] + '...'
            cells.append(clean.ljust(width))
        return '  '.join(cells).rstrip()

    result = [line(('AGENT CLI', 'ON', 'STATE', 'AUTH', 'POLICY', 'LÝ DO'))]
    for row in rows:
        auth = {'AUTHENTICATED': 'OK', 'NOT_AUTHENTICATED': 'NO'}.get(row.get('authentication'), 'UNKNOWN')
        result.append(line((row['agent'], 'ON' if row.get('enabled') else 'OFF',
                            row.get('state', 'UNKNOWN'), auth, row.get('model_policy', 'INHERIT'), agent_reason(row))))
    return '\n'.join(result)


def parser():
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
    setup.add_argument('--check', dest='check', action='store_true', default=True, help='Official version/auth probes (default); no model calls')
    setup.add_argument('--offline', dest='check', action='store_false', help='Resolve paths only; leave version/auth unknown')
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
    cfg = sub.add_parser('config'); cfg.add_argument('--allow-mcp-config', choices=['true', 'false'])
    cfg.add_argument('--default-client', choices=['antigravity', 'vscode', 'codex', 'copilot', 'claude', 'none'])
    project = sub.add_parser('projects'); pc = project.add_subparsers(dest='action', required=True)
    pc.add_parser('list')
    remove = pc.add_parser('remove'); remove.add_argument('project')
    context = sub.add_parser('context'); context.add_argument('project', nargs='?')
    run = sub.add_parser('run'); run.add_argument('request', nargs='+', help='Objective, or PROJECT OBJECTIVE with --project omitted')
    run.add_argument('--project'); run.add_argument('--mode', choices=['auto', 'small', 'standard', 'complex'], default='auto')
    run.add_argument('--max-calls', type=int); run.add_argument('--request-key'); run.add_argument('--no-start', action='store_true')
    status = sub.add_parser('status'); status.add_argument('workflow_id', nargs='?'); status.add_argument('--watch', action='store_true'); status.add_argument('--json', action='store_true')
    for name in ('logs', 'diff', 'cancel', 'retry'):
        ap = sub.add_parser(name); ap.add_argument('workflow_id', nargs='?')
        if name == 'retry':
            ap.add_argument('--extra-calls', type=int, default=0)
            ap.add_argument('--at', help='Resume at ISO time with timezone, e.g. 2026-10-25T13:20:17+07:00')
            ap.add_argument('--request-key', help='Deduplicate a scheduled retry and its call grant')
    for name in ('start', 'stop', 'restart'):
        sub.add_parser(name)
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
    from .discovery import repository_root
    import os
    root = repository_root(Path.cwd())
    for row in hub.store.all('SELECT * FROM projects'):
        if os.path.normcase(str(Path(row['path']).resolve())) == os.path.normcase(str(root)) and not is_removed(hub.store.home, row['id']):
            return row['name']
    raise ValueError('Run ma init in this approved project first')


def latest(hub, workflow_id=None):
    if workflow_id:
        return workflow_id
    try:
        row = hub.store.project(current_project(hub))
        result = hub.store.one('SELECT id FROM workflows WHERE project_id=? ORDER BY updated DESC LIMIT 1', (row['id'],))
    except ValueError:
        result = hub.store.one('SELECT id FROM workflows ORDER BY updated DESC LIMIT 1')
    if not result:
        raise ValueError('No workflow recorded yet')
    return result['id']


def menu(hub):
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


def main(argv=None):
    args = parser().parse_args(argv)
    def show(value):
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
        from .wizard import run
        run(hub, args.check)
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
        show(hub.start(project, objective, args.request_key or uuid.uuid4().hex, args.max_calls, args.mode, launch=not args.no_start))
    elif command == 'status':
        if not args.workflow_id and not hub.store.one('SELECT id FROM workflows LIMIT 1'):
            show({'daemon': daemon_status(hub.store.home), 'workflows': []}); return
        from .monitor import render
        workflow_id = latest(hub, args.workflow_id)
        previous = None
        try:
            while True:
                state = hub.status(workflow_id)
                signature = json.dumps(state, sort_keys=True, ensure_ascii=False)
                if signature != previous:
                    if args.json: show(state)
                    else: print(render(state), flush=True)
                    previous = signature
                if not args.watch or state['status'] in {'completed', 'blocked', 'cancelled', 'needs_review'}: break
                time.sleep(2)
        except KeyboardInterrupt:
            print('Monitor closed; workflow continues independently.')
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
        scheduled = 0
        if args.at:
            from datetime import datetime
            parsed = datetime.fromisoformat(args.at)
            if parsed.tzinfo is None:
                raise ValueError('--at requires an explicit timezone')
            scheduled = parsed.timestamp()
        show(hub.retry(latest(hub, args.workflow_id), args.extra_calls,
                       not_before=scheduled, request_key=args.request_key))
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
