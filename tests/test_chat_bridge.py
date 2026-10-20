import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from agenthub.chat_bridge import build, install, check_stdio, EXTENSION_ID
from agenthub.config import ROOT
from agenthub.settings import effective_config, atomic_json, project_settings_path
from agenthub.simulation import setup_fixture
from agenthub.readiness import attest, prepare, initialize_interactive, execution_environment
from agenthub.workspace import git


class ChatBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-chat-test-')
        self.addCleanup(self.temp.cleanup)
        self.hub, self.source, self.project = setup_fixture(self.temp.name)

    def test_vsix_is_verified_and_pins_python_source_home(self):
        package = build(self.hub.store.home)
        with zipfile.ZipFile(package) as archive:
            self.assertIsNone(archive.testzip())
            runtime = json.loads(archive.read('extension/runtime.json'))
            self.assertEqual(runtime['command'], sys.executable)
            self.assertIn(str(self.hub.store.home), runtime['args'])
            metadata = json.loads(archive.read('extension/package.json'))
            self.assertEqual(metadata['contributes']['chatParticipants'][0]['name'], 'hub')
            self.assertFalse(metadata['capabilities']['untrustedWorkspaces']['supported'])

    def test_install_checks_ownership_and_verifies_actual_listing(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            output = EXTENSION_ID + '@0.1.2\n' if len(calls) > 2 else ''
            return subprocess.CompletedProcess(command, 0, output, '')
        result = install(self.hub.store.home, True, runner=runner, command=sys.executable)
        self.assertIn('installed', result['status'])
        self.assertFalse(result['ide_chat_verified'])
        self.assertFalse(result['host_quota_independence_verified'])
        self.assertNotIn('--force', calls[1])
        other_home = Path(self.temp.name) / 'other-home'
        with self.assertRaisesRegex(ValueError, 'unowned'):
            install(other_home, True, runner=lambda *a, **k: subprocess.CompletedProcess(a, 0, EXTENSION_ID + '@0.1.0\n', ''), command=sys.executable)

    def test_stdio_check_has_no_provider_calls(self):
        result = check_stdio(self.hub.store.home)
        self.assertEqual(result['ai_calls'], 0)
        self.assertGreaterEqual(result['tools'], 18)
        self.assertEqual(self.hub.store.all('SELECT * FROM attempts'), [])

    def test_owned_chat_extension_can_upgrade_without_force_or_unowned_replacement(self):
        atomic_json(self.hub.store.home / 'integrations/vscode-chat.json',
                    {'source': str(ROOT), 'python': sys.executable, 'version': '0.1.0'})
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            version = '0.1.0' if len(calls) == 1 else '0.1.2'
            return subprocess.CompletedProcess(command, 0, EXTENSION_ID + '@' + version + '\n', '')
        install(self.hub.store.home, True, runner=runner, command=sys.executable)
        self.assertNotIn('--force', calls[1])
        atomic_json(self.hub.store.home / 'integrations/vscode-chat.json',
                    {'source': str(ROOT), 'python': sys.executable, 'version': '0.0.9'})
        with self.assertRaisesRegex(ValueError, 'changed outside'):
            install(self.hub.store.home, True, runner=runner, command=sys.executable)

    def test_partial_answer_survives_budget_exhaustion_without_artifact_reads_or_ai(self):
        from agenthub.engine import Engine
        from agenthub.adapters import Result
        from agenthub.simulation import report
        flow = self.hub.start('demo', 'Inspect synthetic features', 'saved-answer', mode='standard', launch=False)
        engine = Engine(self.hub.store, self.hub.config)
        attempt = engine._attempt(self.hub.store.workflow(flow['id']), 'copilot', 'implement', Path(self.temp.name) / 'missing-artifacts')
        value = dict(report('implement'), summary='Đã rà soát', findings=['Quiz thiếu chấm điểm'])
        engine._finish_attempt(attempt, Result(report=value))
        self.hub.store.update(flow['id'], status='blocked', calls=6, error='AI call budget exhausted')
        before = self.hub.store.all('SELECT * FROM attempts')
        brief = self.hub.brief(flow['id'])
        self.assertEqual(brief['reports'][0]['findings'], ['Quiz thiếu chấm điểm'])
        self.assertEqual(self.hub.store.all('SELECT * FROM attempts'), before)
        self.assertEqual(brief['calls'], brief['max_calls'])

    def test_numbered_login_runs_only_selected_official_command_and_rechecks(self):
        from agenthub.wizard import login_selected
        answers = iter(['bad', '1', '0'])
        calls, messages = [], []
        def discoverer(name, entry, check):
            return {'agent': name, 'state': 'UNKNOWN', 'authentication': 'UNKNOWN'}
        def runner(command):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)
        with patch('agenthub.registry.execution_command', return_value=['synthetic-copilot']):
            rows = login_selected(self.hub, {'copilot'}, lambda _: next(answers), messages.append, runner, discoverer)
        self.assertEqual(calls, [['synthetic-copilot', 'login']])
        self.assertEqual(rows[0]['authentication'], 'UNKNOWN')
        self.assertNotIn('Đã đăng nhập', '\n'.join(messages))

    def test_numbered_login_missing_cli_and_authenticated_cli_never_launch(self):
        from agenthub.wizard import login_selected
        for state, auth, answers in [('NOT_INSTALLED', 'UNKNOWN', ['1', '0']), ('READY', 'AUTHENTICATED', [])]:
            responses = iter(answers)
            def discoverer(name, entry, check):
                return {'agent': name, 'state': state, 'authentication': auth}
            rows = login_selected(self.hub, {'codex'}, lambda _: next(responses), lambda _: None,
                lambda _: self.fail('Login must not start'), discoverer)
            self.assertEqual(rows[0]['authentication'], auth)

    def test_three_agent_roles_follow_hub_pipeline_and_quota_failover(self):
        from agenthub.engine import Engine
        from agenthub.adapters import Result
        from agenthub.simulation import report
        self.hub.config['providers']['antigravity']['roles'] = ['plan']
        self.hub.config['leader_priority'] = ['antigravity', 'copilot']
        self.hub.config['worker_priority'] = ['codex']
        self.hub.config['reviewer_priority'] = ['copilot']
        seen = []
        class Fake:
            def run(inner, provider, role, context, workspace, *args):
                seen.append((provider, role))
                if role == 'implement':
                    (Path(workspace) / 'SYNTHETIC.md').write_text('synthetic\n', encoding='utf-8')
                return Result(report=report(role))
        flow = self.hub.start('demo', 'Inspect synthetic feature', 'three-agent-pipeline', mode='standard', launch=False)
        engine = Engine(self.hub.store, self.hub.config, Fake())
        for _ in range(8):
            if not engine.tick():
                break
        self.assertEqual(seen, [('antigravity', 'plan'), ('codex', 'implement'), ('copilot', 'review')])
        self.assertEqual(self.hub.status(flow['id'])['status'], 'completed')
        self.assertEqual(self.hub.status(flow['id'])['calls'], 3)

    def test_scheduled_resume_waits_survives_restart_and_grants_budget_only_once(self):
        import time
        from agenthub.api import Hub
        from agenthub.engine import Engine
        self.hub.config['security']['synthetic_data_only'] = True
        flow = self.hub.start('demo', 'Synthetic scheduled task', 'scheduled-task', mode='standard', launch=False)
        self.hub.store.update(flow['id'], status='blocked', calls=6)
        wake_at = time.time() + 5 * 86400
        args = dict(extra_calls=2, not_before=wake_at, request_key='operator-grant-two', launch=False)
        scheduled = self.hub.retry(flow['id'], **args)
        self.assertEqual((scheduled['status'], scheduled['calls'], scheduled['max_calls']), ('waiting', 6, 8))
        self.assertFalse(Engine(self.hub.store, self.hub.config).tick())
        reopened = Hub(self.hub.store.home)
        reopened.config = self.hub.config
        self.assertEqual(reopened.retry(flow['id'], **args)['max_calls'], 8)
        self.assertEqual(reopened.status(flow['id'])['next_run'], wake_at)
        with self.assertRaisesRegex(ValueError, 'different settings'):
            reopened.retry(flow['id'], **{**args, 'extra_calls': 3})
        # Wake after five days: the deliberate wait must not exhaust active-runtime age.
        with patch('agenthub.engine.time.time', return_value=wake_at + 3 * 86400), \
                patch.object(Engine, '_attempt', side_effect=RuntimeError('REACHED_PROVIDER_SELECTION')):
            engine = Engine(reopened.store, reopened.config)
            engine.tick()
        self.assertIn('REACHED_PROVIDER_SELECTION', reopened.status(flow['id'])['error'])
        self.assertEqual(reopened.status(flow['id'])['calls'], 7)

    def test_live_readiness_is_automatic_but_not_a_quota_or_changed_model_claim(self):
        import time
        from agenthub.registry import discover, record_live_success
        entry = self.hub.config['providers']['copilot']
        entry['command'] = [sys.executable]
        record_live_success(self.hub.store.home, 'copilot', entry)
        def row():
            return next(r for r in discover(self.hub.config, home=self.hub.store.home) if r['agent'] == 'copilot')
        self.assertTrue(row()['live_verified'])
        self.assertEqual(row()['state'], 'READY')
        self.assertEqual(row()['authentication'], 'UNKNOWN')
        self.hub.store.health('copilot', time.time() + 3600, 'quota: synthetic')
        self.assertEqual(row()['state'], 'UNAVAILABLE')
        self.assertIn('quota', row()['reason'])
        self.hub.store.health('copilot', 0, '')
        entry.update(model='synthetic-model-changed', model_policy='MANUAL', model_catalog=['synthetic-model-changed'])
        self.assertFalse(row()['live_verified'])

    def test_any_managed_provider_quota_wait_is_durable_without_extra_calls(self):
        import time
        from agenthub.engine import Engine
        from agenthub.adapters import Result
        from agenthub.simulation import report
        self.hub.config['leader_priority'] = ['copilot']
        flow = self.hub.start('demo', 'Synthetic quota task', 'quota-wake', mode='standard', launch=False)
        wake_at = time.time() + 5 * 86400
        self.hub.store.health('copilot', wake_at, 'quota: synthetic')
        class Fake:
            def run(inner, provider, role, *args):
                return Result(report=report(role))
        engine = Engine(self.hub.store, self.hub.config, Fake())
        engine.tick()
        waiting = self.hub.status(flow['id'])
        self.assertEqual((waiting['status'], waiting['calls'], waiting['next_run']), ('waiting', 0, wake_at))
        self.assertFalse(Engine(self.hub.store, self.hub.config, Fake()).tick())
        with patch('agenthub.engine.time.time', return_value=wake_at + 1):
            Engine(self.hub.store, self.hub.config, Fake()).tick()
        resumed = self.hub.status(flow['id'])
        self.assertEqual((resumed['calls'], resumed['max_calls'], resumed['phase']), (1, 6, 'implement'))

    def test_negative_auth_probe_overrides_previous_success(self):
        from agenthub.registry import discover, record_live_success, discover_agent
        entry = self.hub.config['providers']['copilot']
        entry['command'] = [sys.executable]
        record_live_success(self.hub.store.home, 'copilot', entry)
        real = discover_agent
        def checked(name, entry, check=False, runner=None):
            row = real(name, entry, False)
            if name == 'copilot':
                row.update(authentication='NOT_AUTHENTICATED', adapter_protocol_detected=True)
            return row
        with patch('agenthub.registry.discover_agent', side_effect=checked):
            row = next(r for r in discover(self.hub.config, True, home=self.hub.store.home) if r['agent'] == 'copilot')
        self.assertNotEqual(row['state'], 'READY')
        self.assertFalse(row['live_verified'])

    def test_watchdog_only_starts_existing_due_work_without_retry_or_budget_change(self):
        import time
        from agenthub.wakeup import wake
        flow = self.hub.start('demo', 'Synthetic queue wake', 'watchdog', mode='standard', launch=False)
        self.hub.store.update(flow['id'], status='waiting', next_run=time.time() + 5000)
        with patch('agenthub.wakeup.daemon_status', return_value='stopped'), \
                patch('agenthub.wakeup.start_daemon', return_value={'status':'starting'}) as start:
            self.assertEqual(wake(self.hub.store.home)['status'], 'idle')
            start.assert_not_called()
            self.hub.store.update(flow['id'], next_run=0)
            self.assertEqual(wake(self.hub.store.home)['status'], 'starting')
            start.assert_called_once()
        self.assertEqual(self.hub.status(flow['id'])['max_calls'], 6)
        self.assertEqual(self.hub.status(flow['id'])['calls'], 0)

    def test_windows_watchdog_install_is_scoped_hidden_and_no_force(self):
        from agenthub.wakeup import install as install_wake
        if os.name != 'nt':
            self.skipTest('Windows scheduled task packaging')
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0)
        result = install_wake(self.hub.store.home, True, runner)
        self.assertIn('installed', result['status'])
        self.assertTrue(any(arg.endswith('pythonw.exe') for arg in calls[0]))
        self.assertNotIn('-Owned', calls[0])
        install_wake(self.hub.store.home, True, runner)
        self.assertIn('-Owned', calls[1])

    def test_javascript_handler_and_transport(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node required only for extension development checks')
        result = subprocess.run([node, '--test', str(ROOT / 'tests/vscode-chat.test.js')],
            capture_output=True, encoding='utf-8', errors='replace', timeout=25,
            env={**os.environ, 'HUB_TEST_HOME': str(self.hub.store.home), 'HUB_TEST_PYTHON': sys.executable})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_refused_scope_does_not_read_or_initialize_source(self):
        with patch('agenthub.project_context.initialize') as init:
            with self.assertRaisesRegex(ValueError, 'Chưa xác nhận'):
                initialize_interactive(self.hub, self.source, ask=lambda _: 'n', write=lambda _: None)
        init.assert_not_called()

    def test_baseline_runs_in_owned_worktree_and_retains_evidence(self):
        scope = attest(self.hub, self.source, ask=lambda _: 'y', write=lambda _: None)
        original_security = dict(self.hub.config['security'])
        with patch('agenthub.readiness.probe_worker', return_value={'status': 'OK', 'ai_calls': 0}):
            value = prepare(self.hub, self.project, scope, write=lambda _: None)
        self.assertTrue(value['ready'])
        self.assertEqual(value['ai_calls'], 0)
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        self.assertNotEqual(Path(value['baseline_worktree']), self.source)
        self.assertEqual(self.hub.config['security'], original_security)
        config = effective_config(self.hub.config, self.hub.store.home, self.project['id'])
        self.assertTrue(config['security']['synthetic_data_only'])
        self.assertFalse(config['security']['require_isolation'])
        self.assertEqual(self.hub.store.all('SELECT * FROM attempts'), [])

    def test_isolation_requirement_is_never_relaxed_by_scope_confirmation(self):
        self.hub.config['security']['require_isolation'] = True
        scope = attest(self.hub, self.source, ask=lambda _: 'y', write=lambda _: None)
        with self.assertRaisesRegex(ValueError, 'requested isolation'):
            prepare(self.hub, self.project, scope, write=lambda _: None)
        self.assertFalse((self.hub.store.home / 'workspaces').exists())

    def test_failed_baseline_is_not_ready_or_ai_dispatched(self):
        with self.hub.store.connection() as db:
            db.execute('UPDATE projects SET verify=? WHERE id=?', (json.dumps([[sys.executable, '-c', 'raise SystemExit(3)']]), self.project['id']))
        project = self.hub.store.project(self.project['id'])
        scope = attest(self.hub, self.source, ask=lambda _: 'y', write=lambda _: None)
        with self.assertRaisesRegex(ValueError, 'chưa pass'):
            with patch('agenthub.readiness.probe_worker', return_value={'status': 'OK', 'ai_calls': 0}):
                prepare(self.hub, project, scope, write=lambda _: None)
        folder = project_settings_path(self.hub.store.home, project['id']).parent
        self.assertFalse(json.loads((folder / 'readiness.json').read_text())['ready'])
        self.assertEqual(self.hub.store.all('SELECT * FROM workflows'), [])

    def test_sdk_environment_rejects_arbitrary_overrides(self):
        path = project_settings_path(self.hub.store.home, self.project['id']).parent / 'environment.json'
        sdk = Path(self.temp.name) / 'synthetic-sdk'
        sdk.mkdir()
        atomic_json(path, {'ANDROID_HOME': str(sdk)})
        self.assertEqual(execution_environment(self.hub.store.home, self.project['id']), {'ANDROID_HOME': str(sdk)})
        atomic_json(path, {'PATH': str(sdk)})
        with self.assertRaisesRegex(ValueError, 'Invalid project SDK'):
            execution_environment(self.hub.store.home, self.project['id'])

    def test_launcher_retires_checkout_path_and_keeps_one_pinned_home(self):
        from agenthub.lifecycle import install_command
        unrelated = str(Path(self.temp.name) / 'other-tools')
        owned_bin = str(self.hub.store.home / 'runtime/bin')
        original = ';'.join([str(ROOT), unrelated, owned_bin])
        updates = []
        result = install_command(self.hub.store.home, get_path=lambda: original,
                                 set_path=updates.append, which=lambda _: str(ROOT / 'ma.cmd'))
        self.assertEqual(updates, [';'.join([owned_bin, unrelated])])
        self.assertEqual(result['retired_source_entries'], 1)
        record = json.loads((self.hub.store.home / 'runtime/installation.json').read_text())
        backup = json.loads(Path(record['path_backup']).read_text())
        self.assertEqual(backup['user_path'], original)
        launcher = Path(record['launcher']).read_text(encoding='utf-8')
        self.assertIn(sys.executable, launcher)
        self.assertIn('--home "' + str(self.hub.store.home) + '"', launcher)

    def test_worker_probe_reproduces_shell_failure_without_model(self):
        from agenthub.readiness import probe_worker
        if os.name != 'nt':
            self.skipTest('Windows executor probe')
        commands = []
        def runner(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 1, '', 'helper_unknown_error: setup refresh had errors')
        with self.assertRaisesRegex(ValueError, 'chưa chạy được') as failed:
            probe_worker(self.hub.config, 'codex', self.source, runner)
        self.assertIn('codex doctor --summary', str(failed.exception))
        self.assertNotIn('/setup-default-sandbox', str(failed.exception))
        self.assertIn('sandbox', commands[0])
        self.assertIn(':workspace', commands[0])
        self.assertIn('--include-managed-config', commands[0])
        self.assertNotIn('exec', commands[0])
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', commands[0])
        passed = probe_worker(self.hub.config, 'codex', self.source,
                              lambda *a, **k: subprocess.CompletedProcess(a, 0, 'HUB_SANDBOX_OK\n', ''))
        self.assertEqual(passed['status'], 'OK')

    def test_worker_probe_file_lock_reports_cause_without_raw_output(self):
        from agenthub.readiness import probe_worker
        if os.name != 'nt':
            self.skipTest('Windows executor probe')
        private = 'SYNTHETIC_PRIVATE_DIAGNOSTIC'
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, '', private + ' (os error 32)')
        with self.assertRaisesRegex(ValueError, 'Windows error 32') as failed:
            probe_worker(self.hub.config, 'codex', self.source, runner)
        self.assertNotIn(private, str(failed.exception))

    def test_worker_environment_failure_blocks_before_spending_a_call(self):
        from agenthub.engine import Engine
        from agenthub.adapters import Invoker
        self.hub.config['security']['synthetic_data_only'] = True
        flow = self.hub.start('demo', 'Fix README typo', 'bad-worker-environment', launch=False)
        with patch('agenthub.readiness.probe_worker', side_effect=ValueError('sandbox environment unavailable')):
            Engine(self.hub.store, self.hub.config, Invoker(self.hub.config)).tick()
        state = self.hub.status(flow['id'])
        self.assertEqual(state['status'], 'blocked')
        self.assertEqual(state['calls'], 0)
        self.assertEqual(state['attempts'], [])
        self.assertEqual(self.hub.store.all('SELECT * FROM health'), [])
