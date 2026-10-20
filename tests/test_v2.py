"""V2 checks use synthetic repositories, fake probes and temporary client configs only."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agenthub.config import ROOT, defaults
from agenthub.registry import discover_agent, model_arguments, validate_entry
from agenthub.settings import update_provider, effective_config, application_home
from agenthub.simulation import setup_fixture, SimulatedInvoker
from agenthub.engine import Engine
from agenthub.workspace import git
from agenthub.project_context import initialize, get_context, unregister, is_removed
from agenthub.integrations import install_client, remove_client, server
from agenthub.lifecycle import install_command, uninstall, path_entries
from agenthub.wizard import checkbox, configure


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        from agenthub.api import Hub
        from agenthub.settings import atomic_json
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hub = Hub(Path(self.temp.name) / 'home')
        self.binary = Path(self.temp.name) / 'fake.exe'
        self.binary.write_bytes(b'synthetic CLI; never executed')
        self.hub.config['providers']['antigravity']['command'] = [str(self.binary)]
        atomic_json(self.hub.store.home / 'config.json', self.hub.config)

    def runner(self, command):
        self.assertIn(command[-1], ('--version', '--help', 'status'))
        if command[-1] == 'status':
            return 0, '{"loggedIn":true}'
        return 0, '1.4.2' if command[-1] == '--version' else '--output-format json'

    def record(self):
        from agenthub.confirmations import confirm
        return confirm(self.hub, 'antigravity', worked=True, runner=self.runner)

    def row(self, check=False):
        from agenthub.registry import discover
        return next(row for row in discover(self.hub.config, check, runner=self.runner, home=self.hub.store.home) if row['agent'] == 'antigravity')

    def test_operator_report_survives_reload_without_claiming_verified_auth(self):
        from agenthub.api import Hub
        from agenthub.cli import agent_reason
        self.assertEqual(self.record()['model_calls'], 0)
        self.hub = Hub(self.hub.store.home)
        for check in (False, True):
            row = self.row(check)
            self.assertEqual(row['state'], 'READY')
            self.assertEqual(row['authentication'], 'UNKNOWN')
            self.assertFalse(row['live_verified'])
            self.assertEqual(agent_reason(row), 'Bạn xác nhận chạy AI')
        record = json.loads((self.hub.store.home / 'agent-confirmations.json').read_text())['antigravity']
        self.assertEqual(set(record), {'source', 'confirmed_at', 'fingerprint'})

    def test_revoke_removes_report_and_keeps_security_config_unchanged(self):
        from agenthub.confirmations import confirm
        before = (self.hub.store.home / 'config.json').read_bytes()
        self.record()
        confirm(self.hub, 'antigravity', revoke=True)
        self.assertEqual(self.row(True)['state'], 'UNKNOWN')
        self.assertEqual((self.hub.store.home / 'config.json').read_bytes(), before)

    def test_persistent_reports_and_legacy_expiry_or_malformed_records(self):
        from agenthub.confirmations import apply, read
        self.record()
        record = read(self.hub.store.home)['antigravity']
        row = self.row(True)
        clean = dict(row, state='UNKNOWN', operator_confirmed=False)
        self.assertEqual(apply([clean], self.hub.store.home, record['confirmed_at'] + 30 * 86400)[0]['state'], 'READY')
        clean = dict(row, state='UNKNOWN', operator_confirmed=False)
        self.assertFalse(apply([clean], self.hub.store.home, record['confirmed_at'] - 1)[0]['operator_confirmed'])
        from agenthub.settings import atomic_json
        for end in ('forever', float('nan'), record['confirmed_at'] - 1):
            atomic_json(self.hub.store.home / 'agent-confirmations.json', {'antigravity': {**record, 'expires_at': end}})
            self.assertEqual(self.row(True)['state'], 'UNKNOWN')

    def test_binary_command_or_model_change_invalidates_report(self):
        from agenthub.registry import discover
        self.record()
        self.binary.write_bytes(b'new synthetic CLI version')
        self.assertEqual(self.row(True)['state'], 'UNKNOWN')
        self.record()
        for entry in ({'model_policy': 'AUTO'}, {'command': [str(self.binary), '--fixture']}):
            config = json.loads(json.dumps(self.hub.config))
            config['providers']['antigravity'].update(entry)
            row = next(r for r in discover(config, runner=self.runner, home=self.hub.store.home) if r['agent'] == 'antigravity')
            self.assertNotEqual(row['state'], 'READY')

    def test_failed_probe_or_protocol_and_missing_cli_override_manual_report(self):
        from agenthub.confirmations import apply
        self.record()
        base = self.row(True)
        for changes in ({'state': 'NOT_INSTALLED'}, {'state': 'UNAVAILABLE'},
                        {'authentication': 'NOT_AUTHENTICATED'},
                        {'adapter_protocol_detected': False, 'version': 'Unknown'}):
            row = dict(base, state='UNKNOWN', operator_confirmed=False)
            row.update(changes)
            self.assertFalse(apply([row], self.hub.store.home)[0]['operator_confirmed'])

    def test_no_report_without_explicit_worked_flag_or_valid_protocol(self):
        from agenthub.confirmations import confirm
        with self.assertRaises(ValueError):
            confirm(self.hub, 'antigravity', runner=lambda _: self.fail('Must not probe without explicit report'))
        with self.assertRaises(ValueError):
            confirm(self.hub, 'antigravity', worked=True, runner=lambda _: (1, 'private diagnostic'))
        self.assertFalse((self.hub.store.home / 'agent-confirmations.json').exists())

    def test_cli_confirm_command_and_mcp_use_home_scoped_reports(self):
        from agenthub.cli import main
        from agenthub.registry import discover_agent
        row = discover_agent('antigravity', self.hub.config['providers']['antigravity'], True, self.runner)
        with patch('agenthub.registry.discover_agent', return_value=row), patch('sys.stdout', new_callable=io.StringIO) as stdout:
            main(['--home', str(self.hub.store.home), 'agents', 'confirm', 'antigravity', '--worked'])
        self.assertIn('READY', stdout.getvalue())
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'get_agent_status', 'arguments': {'agent': 'antigravity'}}}
        from agenthub.mcp import serve
        with patch('sys.stdin', io.StringIO(json.dumps(request) + '\n')), patch('sys.stdout', new_callable=io.StringIO) as stdout:
            serve(self.hub.store.home)
        self.assertIn('READY', stdout.getvalue())
        with tempfile.TemporaryDirectory() as other:
            from agenthub.confirmations import apply
            self.assertEqual(apply([dict(row, state='UNKNOWN')], other)[0]['state'], 'UNKNOWN')


class PresentationTests(unittest.TestCase):
    def test_verify_command_preserves_flags_and_disallows_json_combination(self):
        from agenthub.cli import parser
        command = ['cmd.exe', '/d', '/c', 'gradlew.bat', '--offline', 'testDebugUnitTest']
        args = parser().parse_args(['init', '--verify-command', *command])
        self.assertEqual(args.verify_command, command)
        with patch('sys.stderr', new_callable=io.StringIO), self.assertRaises(SystemExit):
            parser().parse_args(['init', '--verify', '[]', '--verify-command', *command])

    def test_nested_context_is_bounded_without_dumping_source_documents(self):
        from agenthub.presentation import compact
        value = {'root': 'synthetic/repo', 'documents': {'README.md': 'SOURCE MARKER'},
                 'files': [{'path': str(i)} for i in range(500)], 'security': {'synthetic_data_only': True}}
        view = compact(value)
        self.assertNotIn('SOURCE MARKER', view)
        self.assertNotIn('{', view)
        self.assertIn('500 items', view)
        self.assertIn('synthetic_data_only=yes', view)
        self.assertLessEqual(len(view.splitlines()), 9)

    def test_workflow_summary_retains_error_delivery_and_budget(self):
        from agenthub.presentation import compact
        view = compact(dict(id='fixture', phase='verify', status='blocked', leader='codex',
                            calls=2, max_calls=3, error='synthetic failure', delivery='fixture.zip',
                            events=[{'data': 'large payload'}] * 100))
        self.assertIn('2/3', view)
        self.assertIn('synthetic failure', view)
        self.assertIn('fixture.zip', view)
        self.assertNotIn('large payload', view)
        self.assertEqual(len(view.splitlines()), 5)

    def test_export_flag_available_for_noninteractive_commands(self):
        from agenthub.cli import parser
        for command in (['init'], ['doctor'], ['config'], ['context'], ['projects', 'list'],
                        ['agents', 'models'], ['run', 'fixture task'], ['logs'], ['diff'],
                        ['status'], ['cancel'], ['retry'], ['start'], ['update'],
                        ['integrations', 'command', 'vscode'], ['demo', '--simulate']):
            with self.subTest(command=command):
                self.assertTrue(parser().parse_args([*command, '--json']).json)

    def test_monitor_limits_history_and_formats_events_without_json(self):
        from agenthub.monitor import render
        state = dict(id='fixture', status='completed', phase='review', calls=2, max_calls=3,
                     repairs=0, max_repairs=3, created=0, updated=1,
                     attempts=[dict(provider='codex', status='completed', phase='plan', usage={})] * 50,
                     verification={'checks': [{'exit_code': 0, 'command': ['synthetic']}] * 50},
                     events=[dict(kind='fixture_event', data={'reason': 'synthetic'}, created=0)] * 50)
        view = render(state)
        self.assertEqual(view.count('fixture_event'), 2)
        self.assertNotIn('{', view)
        self.assertIn('50/50 passed', view)
        self.assertLessEqual(len(view.splitlines()), 11)


class AgentListTests(unittest.TestCase):
    def rows(self):
        return [dict(agent=name, enabled=name != 'claude', state='NOT_INSTALLED',
                     authentication='UNKNOWN', model_policy='INHERIT',
                     login_hint='synthetic verbose login hint', model_catalog=[], live_verified=False)
                for name in ('codex', 'claude', 'copilot', 'antigravity')]

    def test_default_is_five_lines_and_keeps_unknown_and_disabled_visible(self):
        from agenthub.cli import main
        with tempfile.TemporaryDirectory() as home, patch('agenthub.cli.discover', return_value=self.rows()) as discover, patch('sys.stdout', new_callable=io.StringIO) as stdout:
            main(['--home', home, 'agents', 'list'])
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 5)
        self.assertIn('OFF', lines[2])
        self.assertTrue(all('NOT_INSTALLED' in line and 'UNKNOWN' in line for line in lines[1:]))
        self.assertNotIn('login hint', stdout.getvalue())
        self.assertFalse(discover.call_args.args[1])

    def test_json_preserves_full_diagnostics(self):
        from agenthub.cli import main
        rows = self.rows()
        with tempfile.TemporaryDirectory() as home, patch('agenthub.cli.discover', return_value=rows), patch('sys.stdout', new_callable=io.StringIO) as stdout:
            main(['--home', home, 'agents', 'list', '--json'])
        self.assertEqual(json.loads(stdout.getvalue()), rows)

    def test_check_keeps_full_cache_with_compact_output(self):
        from agenthub.cli import main
        rows = self.rows()
        with tempfile.TemporaryDirectory() as home, patch('agenthub.cli.discover', return_value=rows) as discover, patch('sys.stdout', new_callable=io.StringIO) as stdout:
            main(['--home', home, 'agents', 'list', '--check'])
            self.assertEqual(json.loads((Path(home) / 'agent-registry.json').read_text(encoding='utf-8')), rows)
        self.assertTrue(discover.call_args.args[1])
        self.assertEqual(len(stdout.getvalue().splitlines()), 5)

    def test_provider_metadata_cannot_add_lines_or_unbounded_columns(self):
        from agenthub.cli import agent_table
        rows = self.rows()
        rows[0].update(agent='codex\n\x1b' + 'x' * 100, state='READY', authentication='AUTHENTICATED')
        rows[1]['authentication'] = 'NOT_AUTHENTICATED'
        text = agent_table(rows)
        self.assertEqual(len(text.splitlines()), 5)
        self.assertTrue(all(len(line) <= 79 for line in text.splitlines()))
        self.assertNotIn('\x1b', text)
        self.assertIn('OK', text)
        self.assertIn('NO', text)

    def test_short_reasons_distinguish_missing_disabled_auth_and_probe_limits(self):
        from agenthub.cli import agent_reason
        cases = [
            ({'enabled': False, 'state': 'READY'}, 'Đã tắt trong cấu hình'),
            ({'state': 'NOT_INSTALLED'}, 'Không tìm thấy CLI/PATH'),
            ({'state': 'NOT_INSTALLED', 'ide_installed': True}, 'Có IDE, thiếu CLI/PATH'),
            ({'state': 'INSTALLED', 'authentication': 'NOT_AUTHENTICATED'}, 'Chưa đăng nhập'),
            ({'state': 'INSTALLED', 'authentication': 'UNKNOWN'}, 'Chưa kiểm tra: --check'),
            ({'state': 'UNKNOWN'}, 'Chưa xác minh đăng nhập'),
            ({'state': 'UNKNOWN', 'reason': 'untrusted raw diagnostic'}, 'Chưa xác minh đăng nhập'),
            ({'state': 'UNAVAILABLE', 'reason': 'Version probe failed'}, 'Lỗi kiểm tra phiên bản'),
            ({'state': 'UNAVAILABLE', 'reason': 'untrusted raw diagnostic'}, 'CLI lỗi hoặc timeout'),
            ({'state': 'AUTHENTICATED'}, 'Chưa nhận diện adapter'),
            ({'state': 'READY'}, 'Sẵn sàng; chưa thử AI'),
            ({'state': 'READY', 'live_verified': True}, 'Đã xác minh chạy AI'),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                self.assertEqual(agent_reason(dict(self.rows()[0], **changes)), expected)


class RegistryTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows installation discovery')
    def test_antigravity_user_install_discovered_without_updated_path(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'agy/bin/agy.exe'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'synthetic executable marker; must never run')
            with patch.dict(os.environ, {'LOCALAPPDATA': folder, 'APPDATA': folder, 'ProgramFiles': folder}), patch('shutil.which', return_value=None):
                value = discover_agent('antigravity', {}, runner=lambda _: self.fail('No provider execution'))
            self.assertEqual(value['state'], 'INSTALLED')
            self.assertEqual(value['command'], [str(binary.resolve())])
            self.assertEqual(value['authentication'], 'UNKNOWN')
            self.assertFalse(value['live_verified'])

    def entry(self, name='codex'):
        return {**defaults()['providers'][name], 'command': [sys.executable]}

    def test_no_probe_without_explicit_check(self):
        def fail(_): self.fail('No provider may be executed')
        state = discover_agent('codex', self.entry(), runner=fail)
        self.assertEqual(state['state'], 'INSTALLED')
        self.assertEqual(state['authentication'], 'UNKNOWN')
        self.assertFalse(state['live_verified'])

    def test_missing_binary_does_not_claim_ide_login(self):
        with patch('agenthub.registry.resolve_command', side_effect=FileNotFoundError), patch('agenthub.registry.common_candidates', return_value=[]):
            state = discover_agent('antigravity', self.entry('antigravity'))
        self.assertEqual(state['state'], 'NOT_INSTALLED')

    def test_codex_official_auth_and_ready(self):
        commands = []
        def fake(command):
            commands.append(command)
            if command[-1] == '--version': return 0, 'codex-cli 1.2.3'
            if command[-1] == '--help': return 0, 'exec --model'
            return 0, 'Logged in'
        value = discover_agent('codex', self.entry(), True, fake)
        self.assertEqual(value['state'], 'READY')
        self.assertEqual(commands[-1][-2:], ['login', 'status'])
        self.assertEqual(value['quota_calls'], 0)
        self.assertFalse(value['live_verified'])

    def test_unknown_auth_is_not_guessed_for_copilot(self):
        calls = []
        def fake(command):
            calls.append(command)
            return 0, '1.2.3 --output-format'
        value = discover_agent('copilot', self.entry('copilot'), True, fake)
        self.assertEqual(value['state'], 'UNKNOWN')
        self.assertEqual(len(calls), 2)

    def test_claude_auth_json_is_not_leaked(self):
        def fake(command):
            if command[-2:] == ['auth', 'status']: return 0, '{"loggedIn":true,"email":"synthetic@example.invalid"}'
            return 0, '2.1.0 --output-format'
        result = discover_agent('claude', self.entry('claude'), True, fake)
        self.assertEqual(result['state'], 'READY')
        self.assertNotIn('synthetic@example.invalid', json.dumps(result))

    def test_failed_probe_is_unavailable_without_raw_output(self):
        result = discover_agent('codex', self.entry(), True, lambda _: (2, 'private diagnostic'))
        self.assertEqual(result['state'], 'UNAVAILABLE')
        self.assertNotIn('private diagnostic', json.dumps(result))

    def test_inherit_does_not_force_model_even_if_stale_value_exists(self):
        self.assertEqual(model_arguments('codex', {'model_policy': 'INHERIT', 'model': 'old'}), [])

    def test_native_auto_and_explicit_fallback(self):
        self.assertEqual(model_arguments('copilot', {'model_policy': 'AUTO'}), ['--model', 'auto'])
        with self.assertRaises(ValueError): model_arguments('codex', {'model_policy': 'AUTO'})
        self.assertEqual(model_arguments('codex', {'model_policy': 'AUTO', 'model_fallback': 'INHERIT'}), [])

    def test_manual_requires_dynamic_catalog_and_handles_retired_model(self):
        config = {'model_policy': 'MANUAL', 'model': 'fixture-model', 'model_catalog': ['fixture-model']}
        self.assertEqual(model_arguments('claude', config), ['--model', 'fixture-model'])
        config['model_catalog'] = []
        with self.assertRaises(ValueError): model_arguments('claude', config)
        config['model_fallback'] = 'INHERIT'
        self.assertEqual(model_arguments('claude', config), [])

    def test_legacy_manual_and_unsupported_roles(self):
        self.assertEqual(model_arguments('codex', {'model': 'legacy-model'}), ['--model', 'legacy-model'])
        with self.assertRaises(ValueError): validate_entry('copilot', {'roles': ['implement']})


class WizardInputTests(unittest.TestCase):
    def preferences(self, answers, selected=None):
        from agenthub.wizard import collect_preferences
        selected = selected or {'antigravity', 'codex', 'copilot'}
        prompts, messages = [], []
        values = iter(answers)
        def ask(prompt):
            prompts.append(prompt)
            return next(values)
        result = collect_preferences(defaults(), selected, [{'agent': n, 'model_catalog': []} for n in selected], ask, messages.append)
        return result, prompts, messages

    def test_common_auto_asks_fallback_once_and_keeps_roles_without_prompt(self):
        result, prompts, _ = self.preferences(['AUTO', 'y', 'n'])
        self.assertEqual({e['model_policy'] for e in result.values()}, {'AUTO'})
        self.assertEqual(result['codex']['model_fallback'], 'INHERIT')
        self.assertEqual(result['antigravity']['model_fallback'], 'INHERIT')
        self.assertIsNone(result['copilot']['model_fallback'])
        self.assertEqual(sum('model policy [' in p for p in prompts), 1)
        self.assertEqual(sum('fallback for all' in p for p in prompts), 1)
        self.assertFalse(any(' roles [' in p for p in prompts))

    def test_common_inherit_applies_to_all_selected_agents(self):
        result, prompts, _ = self.preferences(['INHERIT', ''])
        self.assertEqual(set(result), {'antigravity', 'codex', 'copilot'})
        self.assertTrue(all(e['model_policy'] == 'INHERIT' for e in result.values()))
        self.assertEqual(len(prompts), 2)

    def test_literal_blank_keeps_current_is_not_saved_as_role(self):
        result, _, _ = self.preferences(['INHERIT', 'y', 'y', '', 'blank keeps current'], {'antigravity'})
        self.assertNotIn('roles', result['antigravity'])

    def test_invalid_role_reprompts_locally_then_accepts_supported_role(self):
        result, prompts, messages = self.preferences(['INHERIT', 'y', 'y', '', 'implement', 'plan,review'], {'antigravity'})
        self.assertEqual(result['antigravity']['roles'], ['plan', 'review'])
        self.assertEqual(sum(' roles [' in p for p in prompts), 2)
        self.assertTrue(any('Invalid roles' in m for m in messages))

    def test_declining_auto_fallback_requires_new_explicit_policy(self):
        result, _, messages = self.preferences(['AUTO', 'n', 'INHERIT', 'n'])
        self.assertTrue(all(e['model_policy'] == 'INHERIT' for e in result.values()))
        self.assertTrue(any('not applied' in m for m in messages))

    def test_bad_common_policy_and_unknown_manual_model_can_be_corrected(self):
        result, _, messages = self.preferences(['typo', 'MANUAL', 'unknown-fixture-model', 'INHERIT', 'n'])
        self.assertTrue(all(e['model_policy'] == 'INHERIT' for e in result.values()))
        self.assertTrue(any('not in the provider-reported catalog' in m for m in messages))


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ma-v2-')
        self.base = Path(self.temp.name)
        self.hub, self.source, self.project = setup_fixture(self.base)

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, cwd=None, home=None):
        return subprocess.run([sys.executable, str(ROOT / 'ma.py'), '--home', str(home or self.hub.store.home), *args],
                              cwd=cwd or self.source, capture_output=True, encoding='utf-8', timeout=25)

    def test_init_no_source_write_and_context_versioning(self):
        before = {p.relative_to(self.source).as_posix(): p.read_bytes() for p in self.source.rglob('*') if p.is_file() and '.git' not in p.relative_to(self.source).parts}
        one = initialize(self.hub, self.source / 'tests')
        two = initialize(self.hub, self.source)
        self.assertEqual(one['project']['id'], two['project']['id'])
        self.assertEqual(one['context']['version'], two['context']['version'])
        self.assertFalse(two['context_changed'])
        after = {p.relative_to(self.source).as_posix(): p.read_bytes() for p in self.source.rglob('*') if p.is_file() and '.git' not in p.relative_to(self.source).parts}
        self.assertEqual(before, after)
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        (self.source / 'app/tasks.py').write_text('def list_tasks(tasks): return tasks[:]\n')
        self.assertTrue(get_context(self.hub, self.project['id'])['stale'])
        three = initialize(self.hub, self.source)
        self.assertEqual(three['context']['version'], one['context']['version'] + 1)

    def test_unknown_checks_registration_cannot_run(self):
        other = self.base / 'Tiếng Việt project'; other.mkdir()
        git(other, 'init')
        initialized = initialize(self.hub, other)
        self.assertFalse(initialized['verification_configured'])
        with self.assertRaisesRegex(ValueError, 'No verification'):
            self.hub.start(initialized['project']['id'], 'Synthetic task', 'key', launch=False)
        filled = initialize(self.hub, other, verify=[[sys.executable, '-m', 'unittest']])
        self.assertTrue(filled['verification_configured'])

    def test_init_refuses_internal_home_before_creating_any_file(self):
        home = self.source / '.ma'
        result = self.cli('init', home=home)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(home.exists())

    def test_init_accepts_plain_verification_command_without_executing_it(self):
        repo = self.base / 'explicit verify project'
        repo.mkdir(); git(repo, 'init')
        command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests']
        result = self.cli('init', '--json', '--verify-command', *command, cwd=repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        registered = json.loads(result.stdout)
        self.assertEqual(json.loads(registered['project']['verify']), [command])
        self.assertEqual(registered['ai_calls'], 0)
        self.assertTrue(registered['verification_configured'])
        empty = self.cli('init', '--verify-command', cwd=repo)
        self.assertNotEqual(empty.returncode, 0)
        self.assertIn('Provide an executable', empty.stderr)

    def gradle_fixture(self, name='nested gradle', folders=('SkillNova App',), tests=True):
        repo = self.base / name
        repo.mkdir(); git(repo, 'init')
        for folder in folders:
            root = repo / folder
            root.mkdir()
            (root / 'settings.gradle.kts').write_text('// synthetic settings')
            (root / 'gradlew.bat').write_text('@echo off\necho SYNTHETIC %*\n')
            (root / 'gradlew').write_text('#!/bin/sh\necho synthetic\n')
            if tests:
                source = root / 'app/src/test/java/FixtureTest.java'
                source.parent.mkdir(parents=True)
                source.write_text('// synthetic unit-test source')
        return repo

    def test_mcp_install_accepts_empty_whitespace_and_bom_config_with_backups(self):
        for index, data in enumerate((b'', b' \n', b'\xef\xbb\xbf', b'\xef\xbb\xbf{"synthetic":true}')):
            with self.subTest(data=data):
                target = self.base / ('empty-mcp-' + str(index) + '.json')
                target.write_bytes(data)
                result = install_client(self.hub.store.home, 'antigravity', True, target=target)
                self.assertEqual(Path(result['backup']).read_bytes(), data)
                value = json.loads(target.read_text(encoding='utf-8'))
                self.assertIn('multi_agents', value['mcpServers'])
                if b'synthetic' in data:
                    self.assertTrue(value['synthetic'])

    def test_mcp_install_preserves_invalid_or_wrong_shape_json(self):
        for index, data in enumerate((b'broken JSON', b'[]', b'{"mcpServers": []}')):
            with self.subTest(data=data):
                target = self.base / ('bad-mcp-' + str(index) + '.json')
                target.write_bytes(data)
                with self.assertRaises(ValueError):
                    install_client(self.hub.store.home, 'antigravity', True, target=target)
                self.assertEqual(target.read_bytes(), data)

    def test_init_detects_nested_untracked_gradle_without_running_build(self):
        repo = self.gradle_fixture()
        value = initialize(self.hub, repo)
        command = json.loads(value['project']['verify'])[0]
        self.assertIn('--offline', command)
        self.assertEqual(command[-1], 'test')
        self.assertEqual(command[command.index('--project-dir') + 1], 'SkillNova App')
        self.assertIn('SkillNova App', ' '.join(command))
        self.assertFalse(value['verification_executed'])
        self.assertIn('not executed', value['verification_hint'])
        from agenthub.presentation import compact
        self.assertIn('Tests run: no', compact(value))
        self.assertIn('Check:', compact(value))
        self.assertEqual(git(repo, 'ls-files').strip(), '')

    def test_gradle_ambiguity_and_missing_tests_do_not_create_false_verifier(self):
        for name, folders, tests in (('two gradles', ('A', 'B'), True), ('no tests', ('A',), False)):
            with self.subTest(name=name):
                value = initialize(self.hub, self.gradle_fixture(name, folders, tests))
                self.assertFalse(value['verification_configured'])
                self.assertEqual(json.loads(value['project']['verify']), [])

    def test_gradle_missing_wrapper_is_rejected_before_project_registration(self):
        repo = self.base / 'bad wrapper'; repo.mkdir(); git(repo, 'init')
        with self.assertRaisesRegex(ValueError, 'Gradle wrapper not found'):
            initialize(self.hub, repo, verify=[['cmd.exe', '/d', '/c', 'gradlew.bat', 'test']])
        self.assertFalse(self.hub.store.one('SELECT id FROM projects WHERE path=?', (str(repo.resolve()),)))

    def test_replace_verify_is_explicit_backed_up_and_refreshes_cached_context(self):
        from agenthub.settings import project_settings_path
        repo = self.gradle_fixture('replace gradle')
        before = initialize(self.hub, repo)
        original = json.loads(before['project']['verify'])
        replacement = [[sys.executable, '-m', 'unittest']]
        with self.assertRaisesRegex(ValueError, '--replace-verify'):
            initialize(self.hub, repo, verify=replacement)
        after = initialize(self.hub, repo, verify=replacement, replace_verify=True)
        backup = project_settings_path(self.hub.store.home, before['project']['id']).parent / 'verification-previous.json'
        self.assertEqual(json.loads(backup.read_text())['commands'], original)
        self.assertEqual(after['context']['verification'], replacement)
        self.assertEqual(after['context']['version'], before['context']['version'] + 1)
        self.assertEqual(get_context(self.hub, before['project']['id'])['verification'], replacement)

    def test_replace_verify_blocks_active_workflow_and_preserves_current_command(self):
        original = self.hub.store.project(self.project['id'])['verify']
        self.hub.start('demo', 'Filter tasks', 'active-verify-change', launch=False)
        with self.assertRaisesRegex(ValueError, 'workflow is active'):
            initialize(self.hub, self.source, verify=[[sys.executable, '-m', 'unittest']], replace_verify=True)
        self.assertEqual(self.hub.store.project(self.project['id'])['verify'], original)

    def test_replace_verify_can_redetect_but_preserves_settings_when_ambiguous(self):
        repo = self.gradle_fixture('redetect gradle')
        before = initialize(self.hub, repo, verify=[[sys.executable, '-m', 'unittest']])
        changed = initialize(self.hub, repo, replace_verify=True)
        self.assertEqual(json.loads(changed['project']['verify'])[0][-1], 'test')
        self.assertNotEqual(changed['project']['verify'], before['project']['verify'])
        second = repo / 'Second'; second.mkdir()
        for name in ('settings.gradle.kts', 'gradlew.bat', 'gradlew'):
            (second / name).write_text('// synthetic fixture')
        test = second / 'src/test/java/Test.java'; test.parent.mkdir(parents=True); test.write_text('// synthetic')
        with self.assertRaisesRegex(ValueError, 'existing verification was preserved'):
            initialize(self.hub, repo, replace_verify=True)
        self.assertEqual(self.hub.store.project(before['project']['id'])['verify'], changed['project']['verify'])

    def test_cli_replace_verify_updates_without_json_or_source_writes(self):
        repo = self.gradle_fixture('cli replace')
        first = self.cli('init', cwd=repo)
        self.assertEqual(first.returncode, 0, first.stderr)
        changed = self.cli('init', '--replace-verify', '--verify-command', sys.executable, '-m', 'unittest', cwd=repo)
        self.assertEqual(changed.returncode, 0, changed.stderr)
        self.assertIn('Tests run: no', changed.stdout)
        self.assertIn('-m unittest', changed.stdout)
        self.assertEqual(git(repo, 'status', '--porcelain').strip(), '?? "SkillNova App/"')

    @unittest.skipUnless(os.name == 'nt', 'Windows Gradle wrapper quoting')
    def test_generated_windows_gradle_command_handles_spaces(self):
        from agenthub.discovery import detect_checks
        repo = self.gradle_fixture('space wrapper invocation')
        _, checks = detect_checks(repo, include_untracked=True)
        result = subprocess.run(checks[0], cwd=repo, capture_output=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SYNTHETIC', result.stdout)
        self.assertIn('--offline test', result.stdout)

    def test_cli_plain_defaults_and_explicit_json_remain_compatible(self):
        for command in (('init',), ('config',), ('doctor', '--offline'), ('agents', 'models'),
                        ('projects', 'list')):
            with self.subTest(command=command):
                plain = self.cli(*command)
                structured = self.cli(*command, '--json')
                self.assertEqual(plain.returncode, 0, plain.stderr)
                self.assertEqual(structured.returncode, 0, structured.stderr)
                self.assertIsNotNone(json.loads(structured.stdout))
                self.assertTrue(plain.stdout.strip())
                self.assertNotIn('{', plain.stdout)
                self.assertLessEqual(len(plain.stdout.splitlines()), 9)
        exported = self.cli('mcp-config')
        self.assertIn('multi_agents', json.loads(exported.stdout)['mcpServers'])

    def test_context_excludes_secret_and_appsettings_files(self):
        (self.source / '.env').write_text('synthetic secret marker')
        (self.source / 'appsettings.json').write_text('synthetic connection marker')
        value = initialize(self.hub, self.source)['context']
        names = [i['path'] for i in value['files']]
        self.assertNotIn('.env', names)
        self.assertNotIn('appsettings.json', names)

    def test_same_names_have_distinct_stable_local_ids(self):
        a = self.base / 'a/same'; b = self.base / 'b/same'
        for path in (a, b): path.mkdir(parents=True); git(path, 'init')
        first, second = initialize(self.hub, a), initialize(self.hub, b)
        self.assertNotEqual(first['project']['id'], second['project']['id'])
        self.assertEqual(initialize(self.hub, a)['project']['id'], first['project']['id'])

    def test_disable_backups_and_project_cannot_reenable_global_disabled(self):
        result = update_provider(self.hub, 'codex', {'enabled': False})
        self.assertTrue(Path(result['backup']).exists())
        update_provider(self.hub, 'codex', {'enabled': True}, self.project['id'])
        merged = effective_config(self.hub.config, self.hub.store.home, self.project['id'])
        self.assertFalse(merged['providers']['codex']['enabled'])

    def test_active_workflow_configuration_is_not_interrupted(self):
        self.hub.start('demo', 'Filter tasks', 'active', launch=False)
        before = (self.hub.store.home / 'config.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'active'):
            update_provider(self.hub, 'codex', {'enabled': False})
        self.assertEqual((self.hub.store.home / 'config.json').read_bytes(), before)

    def test_project_provider_override_used_by_engine(self):
        update_provider(self.hub, 'codex', {'enabled': False}, 'demo')
        flow = self.hub.start('demo', 'Filter tasks', 'override', launch=False)
        invoker = SimulatedInvoker(False)
        engine = Engine(self.hub.store, self.hub.config, invoker)
        for _ in range(12): engine.tick()
        self.assertEqual(self.hub.status(flow['id'])['status'], 'completed')
        self.assertIn(('claude', 'implement'), invoker.calls)
        self.assertNotIn(('codex', 'implement'), invoker.calls)

    def test_single_provider_self_review_is_explicit(self):
        for n in self.hub.config['providers']:
            self.hub.config['providers'][n]['enabled'] = n == 'codex'
        flow = self.hub.start('demo', 'Filter tasks', 'self-review', launch=False)
        engine = Engine(self.hub.store, self.hub.config, SimulatedInvoker(False))
        for _ in range(10): engine.tick()
        state = self.hub.status(flow['id'])
        self.assertEqual(state['status'], 'completed')
        self.assertFalse(state['review']['reviews'][0]['independent_provider'])
        self.assertIn('self_review', [e['kind'] for e in state['events']])

    def test_no_coding_agent_blocks_without_spending_calls(self):
        for n in ('codex', 'claude'): self.hub.config['providers'][n]['enabled'] = False
        flow = self.hub.start('demo', 'Filter tasks', 'no-code', launch=False)
        engine = Engine(self.hub.store, self.hub.config, SimulatedInvoker(False)); engine.tick()
        state = self.hub.status(flow['id'])
        self.assertEqual(state['status'], 'blocked')
        self.assertEqual(state['calls'], 0)
        self.assertIn('No coding agent', state['error'])

    def test_recursive_worker_dispatch_rejected(self):
        with patch.dict(os.environ, {'MULTI_AGENTS_WORKER': 'synthetic-workflow'}):
            with self.assertRaisesRegex(ValueError, 'Recursive'):
                self.hub.start('demo', 'Filter tasks', 'recursive', launch=False)

    def test_unregister_retains_code_and_history_and_can_reinitialize(self):
        flow = self.hub.start('demo', 'Filter tasks', 'retained', launch=False)
        self.hub.store.cancel(flow['id'])
        unregister(self.hub, 'demo')
        self.assertTrue(self.source.exists())
        self.assertTrue(is_removed(self.hub.store.home, self.project['id']))
        self.assertEqual(self.hub.store.workflow(flow['id'])['status'], 'cancelled')
        initialize(self.hub, self.source)
        self.assertFalse(is_removed(self.hub.store.home, self.project['id']))

    def test_cli_help_init_and_legacy_hub_init(self):
        help_result = subprocess.run([sys.executable, str(ROOT / 'ma.py'), '--help'], capture_output=True, encoding='utf-8')
        self.assertEqual(help_result.returncode, 0)
        self.assertIn('agents', help_result.stdout)
        self.assertEqual(self.cli('init').returncode, 0)
        legacy = subprocess.run([sys.executable, str(ROOT/'hub.py'), '--home', str(self.hub.store.home), 'init'], capture_output=True, encoding='utf-8')
        self.assertEqual(legacy.returncode, 0)

    def test_mcp_new_tools_and_configuration_permission(self):
        requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
                    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'set_agent_enabled', 'arguments': {'agent': 'codex', 'enabled': False}}}]
        result = subprocess.run([sys.executable, str(ROOT/'ma.py'), '--home', str(self.hub.store.home), 'mcp', '--client', 'synthetic-client'],
                                input=''.join(json.dumps(r)+'\n' for r in requests), capture_output=True, encoding='utf-8', timeout=15)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        names = {t['name'] for t in replies[0]['result']['tools']}
        self.assertTrue({'dispatch_task', 'list_agents', 'get_project_context', 'workflow_start'} <= names)
        self.assertTrue(replies[1]['result']['isError'])
        self.assertIn('grant permission', replies[1]['result']['content'][0]['text'])

    def test_monitor_uses_actual_events_not_fake_progress(self):
        from agenthub.monitor import render
        flow = self.hub.start('demo', 'Filter tasks', 'monitor', launch=False)
        view = render(self.hub.status(flow['id']))
        self.assertIn('queued', view)
        self.assertIn('created', view)
        self.assertNotIn('%', view)

    def test_checkbox_and_setup_idempotency_keep_security(self):
        keys = iter([' ', 'j', ' ', '\r'])
        selected = checkbox(['codex', 'claude'], {'codex'}, read=lambda: next(keys), write=lambda _: None)
        self.assertEqual(selected, {'claude'})
        before = self.hub.config['security'].copy()
        configure(self.hub, {'codex'}); configure(self.hub, {'codex'})
        self.assertEqual(self.hub.config['security'], before)
        self.assertFalse(self.hub.config['providers']['claude']['enabled'])

    def test_invalid_wizard_choice_leaves_settings_unchanged(self):
        before = (self.hub.store.home/'config.json').read_bytes()
        with self.assertRaises(ValueError): configure(self.hub, {'copilot'}, {'copilot': {'roles': ['implement']}})
        self.assertEqual((self.hub.store.home/'config.json').read_bytes(), before)

    def test_setup_common_policy_finishes_without_per_agent_roles_or_installation(self):
        import io
        from agenthub.wizard import run
        selected = {'antigravity', 'codex', 'copilot'}
        rows = [{'agent': n, 'state': 'UNKNOWN', 'version': 'Unknown', 'authentication': 'UNKNOWN',
                 'roles': defaults()['providers'][n]['roles'], 'model_catalog': []} for n in selected]
        answers = ['AUTO', 'y', 'n', 'n', '', 'n']
        security = self.hub.config['security'].copy()
        with patch('agenthub.wizard.discover', return_value=rows), patch('agenthub.wizard.checkbox', return_value=selected), patch('builtins.input', side_effect=answers), patch('sys.stdout', io.StringIO()) as printed:
            run(self.hub, check=False)
        self.assertIn('Setup complete.', printed.getvalue())
        self.assertNotIn('Setup did not complete', printed.getvalue())
        self.assertEqual(self.hub.config['security'], security)
        self.assertTrue(all(self.hub.config['providers'][n]['model_policy'] == 'AUTO' for n in selected))

    def test_client_setup_preserves_siblings_and_removes_owned_entry_only(self):
        path = self.base / 'external-client.json'
        path.write_text(json.dumps({'other_setting': 'keep', 'mcpServers': {'existing': {'command': 'fixture'}}}))
        value = install_client(self.hub.store.home, 'antigravity', True, target=path)
        self.assertTrue(Path(value['backup']).exists())
        again = install_client(self.hub.store.home, 'antigravity', True, target=path)
        self.assertEqual(again['status'], 'already configured')
        remove_client(self.hub.store.home, 'antigravity')
        remaining = json.loads(path.read_text())
        self.assertEqual(remaining['other_setting'], 'keep')
        self.assertIn('existing', remaining['mcpServers'])
        self.assertNotIn('multi_agents', remaining['mcpServers'])

    def test_client_collision_is_not_overwritten(self):
        path = self.base / 'external-client.json'
        path.write_text('{"mcpServers":{"multi_agents":{"command":"other"}}}')
        with self.assertRaises(ValueError): install_client(self.hub.store.home, 'copilot', True, target=path)
        self.assertIn('other', path.read_text())

    def test_path_install_idempotent_uninstall_retains_user_data(self):
        path = ['C:\\Other']
        get = lambda: path[0]
        def set_(value): path[0] = value
        home = self.base / 'Tiếng Việt home'
        first = install_command(home, get, set_, which=lambda _: None)
        launcher = Path(first['installed'])
        second = install_command(home, get, set_, which=lambda _: str(launcher))
        self.assertFalse(second['user_path_added'])
        self.assertEqual(len(path_entries(path[0])), 2)
        marker = home / 'user-data.txt'; marker.write_text('preserve')
        uninstall(home, get, set_)
        self.assertEqual(path[0], 'C:\\Other')
        self.assertTrue(marker.exists())

    def test_install_recognizes_same_checkout_launcher_from_old_hub_path(self):
        path = [str(ROOT)]
        result = install_command(self.base/'install', lambda: path[0], lambda value: path.__setitem__(0, value),
                                 which=lambda _: str(ROOT/'ma.cmd'))
        self.assertEqual(path[0].split(';')[0], str(Path(result['installed']).parent))
        self.assertTrue((ROOT/'ma.cmd').exists())

    def test_install_refuses_command_collision_and_rolls_back_path_error(self):
        home = self.base/'install'
        with self.assertRaises(ValueError): install_command(home, lambda: '', lambda _: None, which=lambda _: 'C:/Other/ma.cmd')
        self.assertFalse((home/'runtime/bin/ma.cmd').exists())
        changes = []
        def fail_once(value):
            changes.append(value)
            if len(changes) == 1: raise OSError('synthetic registry error')
        with self.assertRaises(OSError): install_command(home, lambda: 'previous', fail_once, which=lambda _: None)
        self.assertEqual(changes[-1], 'previous')
        self.assertFalse((home/'runtime/bin/ma.cmd').exists())

    def test_migration_copies_database_and_retains_source(self):
        from agenthub.lifecycle import migrate_legacy
        from agenthub.api import Hub
        destination = self.base / 'new home'
        original = self.hub.store.db_path.read_bytes()
        result = migrate_legacy(self.hub.store.home, destination)
        self.assertTrue(result['source_retained'])
        self.assertEqual(Hub(destination).store.project('demo')['id'], self.project['id'])
        self.assertTrue(self.hub.store.db_path.exists())
        with self.assertRaises(ValueError): migrate_legacy(self.hub.store.home, destination)

    def test_migration_refuses_active_workflow_without_destination_write(self):
        from agenthub.lifecycle import migrate_legacy
        self.hub.start('demo', 'Filter tasks', 'migration-active', launch=False)
        destination = self.base / 'new home'
        with self.assertRaisesRegex(ValueError, 'active'):
            migrate_legacy(self.hub.store.home, destination)
        self.assertFalse(destination.exists())

    def test_setup_rolls_back_configuration_after_later_failure(self):
        from agenthub.wizard import run
        before = json.loads((self.hub.store.home/'config.json').read_text())
        def fake_setup(hub, check):
            configure(hub, {'codex'})
            raise OSError('synthetic client failure')
        with patch('agenthub.wizard._run', side_effect=fake_setup), self.assertRaises(OSError):
            run(self.hub)
        self.assertEqual(json.loads((self.hub.store.home/'config.json').read_text()), before)

    def test_update_refuses_dirty_checkout_and_only_explicit_fast_forward(self):
        from agenthub.lifecycle import update_source
        calls = []
        def fake(command, **_):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, '', '')
        update_source(self.source, False, fake)
        self.assertFalse(any('pull' in c for c in calls))
        update_source(self.source, True, fake)
        self.assertIn(['git', '-C', str(self.source), 'pull', '--ff-only'], calls)
        with self.assertRaises(ValueError):
            update_source(self.source, True, lambda command, **_: subprocess.CompletedProcess(command, 0, ' M file', ''))

    def test_provider_reported_model_metadata_is_retained(self):
        from agenthub.adapters import extract_report
        from agenthub.simulation import report
        result, usage = extract_report(json.dumps({'model': 'fixture-actual-model', 'structured_output': report('plan')}))
        self.assertEqual(usage['actual_model'], 'fixture-actual-model')

    def test_sandbox_bypass_arguments_rejected(self):
        from agenthub.adapters import build_command
        folder = self.base/'artifacts'; folder.mkdir()
        for flag in ('--yolo', '--dangerously-skip-permissions', '--allow-all-tools'):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'bypass'):
                build_command('codex', {'command': [sys.executable], 'extra_args': [flag]}, 'implement', 'fixture', folder, False)

    def test_cli_launcher_preserves_unicode_caller_directory(self):
        if os.name != 'nt': self.skipTest('Windows .cmd launcher only')
        repo = self.base/'Dự án có dấu'; repo.mkdir(); git(repo, 'init')
        # The source launcher is invoked directly; no user PATH registration occurs.
        result = subprocess.run(['cmd.exe', '/d', '/c', str(ROOT/'ma.cmd'), '--home', str(self.hub.store.home), 'init', '--json'],
                                cwd=repo, capture_output=True, encoding='utf-8', errors='replace', timeout=20,
                                env={**os.environ, 'PATH': str(Path(sys.executable).parent) + ';' + str(Path(sys.executable).parent.parent/'Launcher') + ';' + os.environ.get('PATH', '')})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['project']['path'], str(repo.resolve()))

    def test_context_reused_in_engine_pack(self):
        from agenthub.workspace import build_pack
        initialize(self.hub, self.source)
        flow = self.hub.start('demo', 'Filter tasks', 'context-reuse', launch=False)
        engine = Engine(self.hub.store, self.hub.config, SimulatedInvoker(False)); engine.tick()
        state = self.hub.store.workflow(flow['id'])
        pack = build_pack(self.hub.store, state, self.project, 'implement', 40000)
        self.assertIn('SHARED PROJECT CONTEXT', pack['text'])

    def test_codex_integration_uses_official_cli_and_backs_up_config(self):
        from agenthub.integrations import install_codex
        codex_home = self.base/'codex-config'; codex_home.mkdir()
        config = codex_home/'config.toml'; config.write_text('model = "fixture"\n')
        calls = []
        def fake(command):
            calls.append(command)
            return (1, '') if 'get' in command else (0, '')
        with patch.dict(os.environ, {'CODEX_HOME': str(codex_home)}), patch('agenthub.platforms.resolve_command', return_value=[sys.executable]):
            result = install_codex(self.hub.store.home, fake)
        self.assertEqual(Path(result['backup']).read_bytes(), config.read_bytes())
        self.assertEqual(calls[-1][1:4], ['mcp', 'add', 'multi_agents'])
        self.assertFalse(result['live_verified'])

    def test_codex_integration_failure_restores_official_config(self):
        from agenthub.integrations import install_codex
        codex_home = self.base/'codex-config'; codex_home.mkdir()
        config = codex_home/'config.toml'; config.write_text('model = "fixture"\n')
        def fake(command):
            if 'get' in command: return 1, ''
            config.write_text('incomplete fixture config')
            return 2, 'synthetic failure'
        with patch.dict(os.environ, {'CODEX_HOME': str(codex_home)}), patch('agenthub.platforms.resolve_command', return_value=[sys.executable]):
            with self.assertRaises(ValueError): install_codex(self.hub.store.home, fake)
        self.assertEqual(config.read_text(), 'model = "fixture"\n')

    def test_vscode_mcp_entry_is_external_stdio_not_provider_login(self):
        path = self.base/'vscode/mcp.json'
        value = install_client(self.hub.store.home, 'vscode', True, path)
        document = json.loads(path.read_text())
        entry = document['servers']['multi_agents']
        self.assertEqual(entry['type'], 'stdio')
        self.assertNotIn('env', entry)
        self.assertIn('vscode', entry['args'])
        self.assertFalse(value['live_verified'])

    def test_dotnet_init_does_not_fake_test_success_without_test_project(self):
        other = self.base/'dotnet-app'; other.mkdir(); git(other, 'init')
        (other/'App.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0-windows</TargetFramework><UseWindowsForms>true</UseWindowsForms></PropertyGroup></Project>')
        git(other, 'add', '.')
        value = initialize(self.hub, other)
        self.assertFalse(value['verification_configured'])
        self.assertIn('Windows Forms', value['context']['frameworks'])

    def test_model_catalog_is_parsed_from_provider_help_not_hardcoded(self):
        def fake(command):
            if command[-1] == '--help': return 0, '--output-format --model MODEL [choices: "fixture-one", "fixture-two"]'
            return 0, '1.0.0'
        result = discover_agent('copilot', {'command': [sys.executable]}, True, fake)
        self.assertEqual(result['model_catalog'], ['fixture-one', 'fixture-two'])

    def test_mcp_dispatch_alias_deduplicates_and_records_client_without_launching(self):
        import io
        from agenthub.mcp import serve
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'dispatch_task',
                   'arguments': {'project': 'demo', 'objective': 'Filter tasks', 'request_key': 'mcp-dedupe'}}}
        text = json.dumps(request) + '\n' + json.dumps({**request, 'id': 2}) + '\n'
        capture = io.StringIO()
        with patch('sys.stdin', io.StringIO(text)), patch('sys.stdout', capture), patch('agenthub.api.start_daemon'):
            serve(self.hub.store.home, client='synthetic-entry')
        replies = [json.loads(line) for line in capture.getvalue().splitlines()]
        self.assertNotIn('isError', replies[0]['result'])
        self.assertEqual(len(self.hub.store.all('SELECT id FROM workflows')), 1)
        event = self.hub.store.one("SELECT data FROM events WHERE kind='client_dispatch' LIMIT 1")
        self.assertEqual(json.loads(event['data'])['client'], 'synthetic-entry')

    def test_mcp_rejects_arbitrary_project_initialization(self):
        import io
        from agenthub.mcp import serve
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'initialize_project',
                   'arguments': {'project': str(self.base/'unapproved')}}}
        capture = io.StringIO()
        with patch('sys.stdin', io.StringIO(json.dumps(request)+'\n')), patch('sys.stdout', capture):
            serve(self.hub.store.home)
        self.assertTrue(json.loads(capture.getvalue())['result']['isError'])
        self.assertFalse((self.base/'unapproved').exists())

    def test_model_failure_uses_only_operator_authorized_fallback_within_budget(self):
        from agenthub.adapters import Result
        entry = self.hub.config['providers']['antigravity']
        entry.update(model_policy='MANUAL', model='fixture-retired', model_catalog=['fixture-retired'], model_fallback='INHERIT')
        class Retired(SimulatedInvoker):
            def __init__(self): super().__init__(False); self.first = True
            def run(self, *args, **kwargs):
                if self.first:
                    self.first = False
                    return Result(error='model_not_found')
                return super().run(*args, **kwargs)
        flow = self.hub.start('demo', 'Filter tasks', 'model-fallback', launch=False)
        engine = Engine(self.hub.store, self.hub.config, Retired())
        for _ in range(10): engine.tick()
        state = self.hub.status(flow['id'])
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['calls'], 4)
        self.assertEqual(entry['model_policy'], 'MANUAL')
        self.assertTrue(self.hub.store.one("SELECT id FROM events WHERE workflow_id=? AND kind='model_fallback_selected'", (flow['id'],)))


if __name__ == '__main__': unittest.main()
