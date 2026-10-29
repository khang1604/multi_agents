"""Explicit one-command project preparation; all state stays outside the source."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from . import workspace as ws
from .platforms import FileLock, resolve_command, spawn, stop_tree
from .security import preflight
from .settings import atomic_json, effective_config, project_settings_path


def probe_worker(config, provider, worktree, runner=None):
    """Exercise the Windows Codex executor without a model or relaxed permissions."""
    if os.name != 'nt' or provider != 'codex':
        return {'status': 'not_available', 'ai_calls': 0}
    from .registry import execution_command
    runner = runner or subprocess.run
    command = execution_command(provider, config['providers'][provider])
    try:
        result = runner(command + ['sandbox', '-C', str(worktree), '--include-managed-config', '-P', ':workspace', '--',
                                   sys.executable, '-c', "print('HUB_SANDBOX_OK')"],
                        capture_output=True, encoding='utf-8', errors='replace', timeout=45,
                        env={**os.environ, **config.get('_execution_environment', {})})
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('Codex sandbox probe failed before AI; inspect CLI setup, then run ma init again') from error
    if result.returncode or 'HUB_SANDBOX_OK' not in result.stdout.splitlines():
        # Never echo provider output: it can contain private paths or credentials.
        diagnostic = (result.stdout or '') + '\n' + (result.stderr or '')
        if 'os error 32' in diagnostic.lower():
            reason = 'A runtime file is locked (Windows error 32). '
        else:
            reason = 'Run codex doctor --summary for diagnostics. '
        raise ValueError('Codex Windows sandbox is not working yet (probe makes no AI calls). '
                         + reason + 'If an older CLI conflicts with the desktop app, update the official Codex CLI, then run ma init again. '
                         'Hub preserves the sandbox; no model has been called.')
    return {'status': 'OK', 'ai_calls': 0}


def execution_environment(home, project_id):
    """Read only allowed project SDK directory variables from external metadata."""
    path = project_settings_path(home, project_id).parent / 'environment.json'
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if set(value) - {'ANDROID_HOME', 'ANDROID_SDK_ROOT'} or not all(
            isinstance(item, str) and Path(item).is_dir() for item in value.values()):
        raise ValueError('Invalid project SDK environment; run ma init again')
    return value


def attest(hub, root, ask=input, write=print):
    """A human input gate BEFORE reading source for interactive initialization."""
    write('Source: ' + str(root))
    answer = ask('Approve this source, synthetic data only, and no application API calls? [y/N]: ').strip().lower()
    if answer not in {'y', 'yes'}:
        raise ValueError('Source/synthetic/no-API scope not confirmed; no context read or AI calls made')
    # This is a project-scoped attestation, not a global security policy update.
    return {'source': str(root), 'synthetic_data_only': True, 'application_apis': [],
            'confirmation_source': 'operator', 'confirmed_at': time.time()}


def prepare(hub, project, scope=None, write=print):
    """Verify project prerequisites and baseline checks in an owned worktree before AI calls."""
    folder = project_settings_path(hub.store.home, project['id']).parent
    active = hub.store.one("SELECT id FROM workflows WHERE project_id=? AND status IN ('queued','running','waiting','recovering') LIMIT 1", (project['id'],))
    if active:
        raise ValueError('This project has a workflow holding a checkpoint: ' + active['id'] + '; check @hub /status first')
    if scope is not None:
        if (scope.get('source') != project['path'] or scope.get('synthetic_data_only') is not True
                or scope.get('application_apis') != [] or scope.get('confirmation_source') != 'operator'):
            raise ValueError('Invalid explicit project attestation')
        atomic_json(folder / 'scope.json', scope)
    config = effective_config(hub.config, hub.store.home, project['id'])
    preflight(config, bool(project['network']))
    commands = json.loads(project['verify'])
    if not commands:
        raise ValueError('No unique verifier found; use ma init --verify-command EXECUTABLE ARGS')
    from .project_context import validate_wrappers
    validate_wrappers(Path(project['path']), commands)
    sdk = {}
    if any('gradlew' in arg.lower() for command in commands for arg in command):
        candidate = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
        if not candidate and os.name == 'nt':
            candidate = str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Android/Sdk')
        if candidate and (Path(candidate) / 'platforms').is_dir():
            sdk = {'ANDROID_HOME': str(Path(candidate).resolve())}
            atomic_json(folder / 'environment.json', sdk)
    from .chat_bridge import check_stdio
    mcp = check_stdio(hub.store.home)
    from .policy import choose
    worker = choose(config, hub.store, 'implement', config['worker_priority'])
    if not worker:
        raise ValueError('No coding CLI available, or it is in cooldown; run ma agents list --check')
    source = Path(project['path'])
    commit = ws.git(source, 'rev-parse', 'HEAD')
    if ws.git(source, 'status', '--porcelain'):
        raise ValueError('Source has uncommitted changes; commit/stash the changes you want to use first. Init does not commit your files automatically.')
    # A dedicated baseline worktree avoids builds modifying the user's checkout.
    with FileLock(folder / 'readiness.lock'):
        worktree = folder / 'readiness' / ('baseline-' + commit[:12])
        worktree.parent.mkdir(parents=True, exist_ok=True)
        if not worktree.exists():
            ws.git(source, 'worktree', 'add', '--detach', str(worktree), commit)
        if ws.git(worktree, 'rev-parse', 'HEAD') != commit or ws.git(worktree, 'status', '--porcelain'):
            raise ValueError('Baseline worktree changed; retained for inspection, no overwrite')
        # Refresh the validated SDK environment after detection above.
        config = effective_config(hub.config, hub.store.home, project['id'])
        try:
            worker_probe = probe_worker(config, worker, worktree)
        except ValueError:
            atomic_json(folder / 'readiness.json', {'ready': False, 'commit': commit, 'checks': [],
                        'baseline_worktree': str(worktree), 'worker_probe': 'failed', 'ai_calls': 0})
            raise
        before = ws.fingerprint(worktree, hub.store)
        run = folder / 'readiness' / uuid.uuid4().hex[:12]
        run.mkdir()
        checks = []
        for index, command in enumerate(commands):
            write('Checking ' + str(index + 1) + '/' + str(len(commands)) + '...')
            args = resolve_command([sys.executable if arg == '{python}' else arg for arg in command])
            output = run / (str(index) + '.log')
            with output.open('wb') as log:
                process = spawn(args, cwd=worktree, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                env={**os.environ, **execution_environment(hub.store.home, project['id']), **sdk})
            reason = ''
            deadline = time.monotonic() + config['verify_timeout_seconds']
            try:
                while process.poll() is None:
                    if time.monotonic() > deadline or output.stat().st_size > config['max_log_bytes']:
                        reason = 'Verification timeout/output limit'
                        if not stop_tree(process):
                            raise ValueError('Baseline process may still exist; no workflow permitted')
                        break
                    time.sleep(0.1)
                checks.append({'command': command, 'exit_code': process.wait(), 'log': str(output), 'reason': reason})
            finally:
                if process.poll() is None:
                    stop_tree(process)
            if checks[-1]['exit_code'] != 0 or reason:
                break
        after = ws.fingerprint(worktree, hub.store)
        passed = len(checks) == len(commands) and all(check['exit_code'] == 0 and not check['reason'] for check in checks) and before == after
        value = {'ready': passed, 'commit': commit, 'checks': checks,
                 'fingerprint_before': before, 'fingerprint_after': after,
                 'baseline_worktree': str(worktree), 'mcp': mcp, 'ai_calls': 0, 'worker_probe': worker_probe,
                 'chat_bridge_configured': (hub.store.home / 'integrations/vscode-chat.json').is_file()}
        atomic_json(folder / 'readiness.json', value)
        if not passed:
            raise ValueError('Baseline verifier has not passed; no AI calls made. Log: ' + str(run) +
                             '. If offline Gradle dependencies are missing, prepare the cache from an approved repository, then run ma init again.')
    return value


def initialize_interactive(hub, path, name=None, verify=None, replace_verify=False, ask=input, write=print):
    """Collect project-scoped authorization and initialize baseline readiness without self-attestation."""
    from .discovery import repository_root
    from .project_context import initialize
    root = repository_root(path)
    existing = next((row for row in hub.store.all('SELECT * FROM projects')
                     if os.path.normcase(str(Path(row['path']).resolve())) == os.path.normcase(str(root))), None)
    scope_path = project_settings_path(hub.store.home, existing['id']).parent / 'scope.json' if existing else None
    scope = None if scope_path and scope_path.exists() else attest(hub, root, ask, write)
    if scope_path and scope_path.exists():
        effective_config(hub.config, hub.store.home, existing['id'])
    try:
        result = initialize(hub, root, name, verify, replace_verify)
    except ValueError as error:
        if (not existing or verify is not None or replace_verify
                or not str(error).startswith('Gradle wrapper not found inside project:')):
            raise
        from .discovery import detect_checks
        _, detected = detect_checks(root, include_untracked=True)
        if not detected:
            raise
        write('Repairing a Gradle verifier with a missing path; keeping a backup of the previous command.')
        result = initialize(hub, root, name, detected, replace_verify=True)
    result['readiness'] = prepare(hub, result['project'], scope, write)
    result['verification_executed'] = True
    return result
