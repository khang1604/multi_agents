#!/usr/bin/env python3
"""Agent Hub Private launcher. Python 3.11+; no third-party packages."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

# Direct invocation must work from any current directory without installation.
from pathlib import Path as _EntryPath
sys.path.insert(0, str(_EntryPath(__file__).resolve().parents[1]))

from agenthub.demo_fixture import write_demo
from agenthub.api import Hub
from agenthub.config import default_home, load, ROOT
from agenthub.engine import Engine
from agenthub.platforms import AlreadyRunning, resolve_command
from agenthub.service import start_daemon, stop_daemon, daemon_status
from agenthub.workspace import diff, git


def output(value):
    """Print a legacy CLI result as structured JSON."""
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parser():
    """Build the compatible legacy Hub command parser."""
    p = argparse.ArgumentParser(description='Personal multi-agent coordinator — local, durable, Auto quota mode')
    p.add_argument('--home', default=str(default_home()), help='Data/config directory; keep this on a local disk')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    sub.add_parser('doctor')
    sub.add_parser('start')
    sub.add_parser('stop')
    sub.add_parser('daemon')
    sub.add_parser('mcp')
    sub.add_parser('mcp-config')
    add = sub.add_parser('project-add')
    add.add_argument('name'); add.add_argument('path')
    add.add_argument('--verify', required=True, help='JSON array of command argument arrays; {python} is portable')
    add.add_argument('--context', default='["README.md","app","src","tests"]')
    add.add_argument('--network', action='store_true', help='Legacy flag; real workflows reject unrestricted tool network under test-only security policy')
    here = sub.add_parser('here', help='Detect the current Git project and recover progress; no AI call')
    here.add_argument('--name', help='Optional name for a new registration')
    here.add_argument('--verify', help='Explicit JSON array of test command argument arrays')
    sub.add_parser('projects')
    sub.add_parser('cleanup')
    run = sub.add_parser('run')
    run.add_argument('project'); run.add_argument('objective', nargs='?')
    run.add_argument('--task-file'); run.add_argument('--request-key')
    run.add_argument('--max-calls', type=int)
    run.add_argument('--mode', choices=['auto','small','standard','complex'], default='auto')
    run.add_argument('--handoff-file', help='JSON analysis summary, decisions and relevant file/range references')
    run.add_argument('--plan-file', help='Reuse an existing leader plan JSON instead of paying for another planner call')
    run.add_argument('--no-start', action='store_true')
    status = sub.add_parser('status')
    status.add_argument('workflow_id', nargs='?'); status.add_argument('--watch', action='store_true')
    for name in ['cancel','retry','diff','logs']:
        cmd = sub.add_parser(name); cmd.add_argument('workflow_id')
        if name == 'retry': cmd.add_argument('--extra-calls', type=int, default=0)
    recover = sub.add_parser('recover'); recover.add_argument('project')
    note = sub.add_parser('memory-note'); note.add_argument('project'); note.add_argument('name'); note.add_argument('content')
    health = sub.add_parser('health-reset'); health.add_argument('provider')
    demo = sub.add_parser('demo'); demo.add_argument('--simulate', action='store_true')
    return p


def doctor(hub):
    """Check local CLI installation/version availability without a model call."""
    providers = {}
    for name, entry in hub.config['providers'].items():
        try:
            command = resolve_command(entry['command'])
            result = subprocess.run(command + ['--version'], capture_output=True, encoding='utf-8', errors='replace', timeout=8)
            providers[name] = {'available': result.returncode == 0, 'command': command,
                               'version': (result.stdout or result.stderr).strip()[:300],
                               'authentication': 'not checked (no model/quota spent)', 'roles': entry['roles']}
        except Exception as error:
            providers[name] = {'available': False, 'reason': str(error)}
    return {'python': sys.version.split()[0], 'os': os.name, 'git': shutil.which('git'),
            'home': str(hub.store.home), 'daemon': daemon_status(hub.store.home),
            'providers': providers, 'health': hub.store.all('SELECT * FROM health'),
            'note': 'Installed does not imply logged in. Claude/Copilot/Antigravity require live validation on your machine.'}


def make_demo(hub):
    """Create and register a synthetic demo project without overwriting existing source."""
    target = hub.store.home / 'demo-source'
    if not target.exists():
        write_demo(target)
        git(target, 'init')
        git(target, 'add', '.')
        git(target, '-c', 'user.name=Agent Hub Demo', '-c', 'user.email=demo@localhost', 'commit', '-m', 'Initial demo')
    return hub.store.add_project('demo', target, [['{python}', '-m', 'unittest', 'discover', '-s', 'tests', '-v']], ['README.md','app','tests'], network=False)


def main(argv=None):
    """Dispatch legacy Hub commands through the same engine, store, and security checks."""
    args = parser().parse_args(argv)
    hub = Hub(args.home)
    if args.command == 'init':
        output({'home': str(hub.store.home), 'config': str(hub.store.home / 'config.json'), 'mode': 'Auto, bounded calls'})
    elif args.command == 'doctor': output(doctor(hub))
    elif args.command == 'project-add':
        output(hub.store.add_project(args.name, args.path, json.loads(args.verify), json.loads(args.context), args.network))
    elif args.command == 'here':
        from agenthub.discovery import identify
        output(identify(hub, Path.cwd(), args.name, json.loads(args.verify) if args.verify else None))
    elif args.command == 'projects': output(hub.store.all('SELECT * FROM projects'))
    elif args.command == 'run':
        objective = Path(args.task_file).read_text(encoding='utf-8') if args.task_file else args.objective
        if not objective:
            raise ValueError('Provide an objective or --task-file')
        plan = json.loads(Path(args.plan_file).read_text(encoding='utf-8')) if args.plan_file else None
        output(hub.start(args.project, objective, args.request_key or uuid.uuid4().hex,
                         args.max_calls, args.mode, launch=not args.no_start, prepared_plan=plan,
                         handoff=json.loads(Path(args.handoff_file).read_text(encoding='utf-8')) if args.handoff_file else None))
    elif args.command == 'status':
        while True:
            if args.workflow_id:
                row = hub.status(args.workflow_id)
                output(row)
                done = row['status'] in {'completed','blocked','cancelled','needs_review'}
            else:
                output({'daemon': daemon_status(hub.store.home), 'workflows': hub.store.all(
                    'SELECT id,status,phase,leader,complexity,calls,max_calls,next_run,summary,error FROM workflows ORDER BY updated DESC LIMIT 30')})
                done = False
            if not args.watch or done: break
            time.sleep(5)
    elif args.command == 'cancel': output(hub.store.cancel(args.workflow_id))
    elif args.command == 'retry': output(hub.retry(args.workflow_id, args.extra_calls))
    elif args.command == 'cleanup':
        from agenthub.retention import sweep
        output(sweep(hub.store,hub.config))
    elif args.command == 'recover': output(hub.recover(args.project))
    elif args.command == 'diff':
        row = hub.store.workflow(args.workflow_id)
        if row.get('delivery') and not Path(row['workspace'] or '').exists():
            with zipfile.ZipFile(row['delivery']) as archive:
                print(archive.read('changes.patch').decode('utf-8',errors='replace'))
                print('DELIVERY MANIFEST:\n'+archive.read('manifest.json').decode('utf-8'))
        elif row['workspace']:
            print(diff(row['workspace']))
        else:
            raise ValueError('Workflow has no worktree/delivery yet')
    elif args.command == 'logs':
        output(hub.store.all('SELECT provider,phase,status,artifact,error,usage FROM attempts WHERE workflow_id=? ORDER BY created', (args.workflow_id,)))
    elif args.command == 'memory-note':
        project = hub.store.project(args.project)
        hub.store.remember(project['id'], args.name, args.content)
        output({'saved': True})
    elif args.command == 'health-reset':
        if args.provider not in hub.config['providers']: raise ValueError('Unknown provider')
        hub.store.health(args.provider, 0, '')
        output({'provider': args.provider, 'cooldown_cleared': True})
    elif args.command == 'start': output(start_daemon(hub.store.home))
    elif args.command == 'stop': output(stop_daemon(hub.store.home))
    elif args.command == 'daemon':
        try: Engine(hub.store, hub.config).serve()
        except AlreadyRunning: pass
    elif args.command == 'mcp':
        from agenthub.mcp import serve
        serve(hub.store.home)
    elif args.command == 'mcp-config':
        output({'mcpServers': {'agent-hub-private': {'command': sys.executable,
                'args': [str(ROOT / 'cli/hub.py'), '--home', str(hub.store.home), 'mcp']}}})
    elif args.command == 'demo':
        if args.simulate:
            from agenthub.simulation import simulate
            output(simulate())
        else:
            output({'project': make_demo(hub), 'next': 'Run the objective in the generated demo-source/TASK.md with run demo --task-file ...'})


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print('Agent Hub: ' + str(error), file=sys.stderr)
        sys.exit(1)
