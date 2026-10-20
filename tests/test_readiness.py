"""Regression cases from Windows failover; all providers are synthetic."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from agenthub.adapters import Invoker, Result
from agenthub.engine import Engine
from agenthub.policy import failure, reset_time
from agenthub.project_context import initialize
from agenthub.simulation import setup_fixture, report
from agenthub.workspace import build_pack, git


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-readiness-')
        self.addCleanup(self.temp.cleanup)
        self.hub, self.source, self.project = setup_fixture(self.temp.name)
        self.hub.config['security']['synthetic_data_only'] = True

    def test_official_compact_quota_reset_and_invalid_durations(self):
        message = 'RESOURCE_EXHAUSTED (code 429): Individual quota reached. Resets in 124h1m3s.'
        self.assertEqual(failure(message), 'quota')
        self.assertEqual(reset_time(message, 100), 100 + 124 * 3600 + 63)
        self.assertEqual(reset_time('Resets in 2m3s', 100), 223)
        for invalid in ['Resets in 999h', 'Resets in -2h', 'Resets in 2h1h', 'Resets in 1m2h',
                        'Resets in 0s', 'Resets in 1hgarbage']:
            self.assertIsNone(reset_time(invalid, 100), invalid)
        self.assertEqual(failure('RESOURCE_EXHAUSTED 429 without quota evidence'), 'temporary')

    def test_real_fake_cli_blocked_response_does_not_poison_provider_health(self):
        blocked = dict(report('plan'), outcome='blocked', summary='Missing verifier declaration',
                       findings=['Previous Antigravity had quota exceeded 429; do not change permissions.'])
        script = Path(self.temp.name) / 'fake_blocked.py'
        script.write_text('import sys,json\nsys.stdin.read()\nprint(' + repr(json.dumps(blocked)) + ')\n', encoding='utf-8')
        self.hub.config['leader_priority'] = ['codex']
        self.hub.config['providers']['codex']['command'] = [sys.executable, str(script)]
        flow = self.hub.start('demo', 'Update technical guide', 'blocked-case', mode='standard', launch=False)
        health_before = self.hub.store.all('SELECT * FROM health')
        engine = Engine(self.hub.store, self.hub.config, Invoker(self.hub.config))
        engine.tick()
        state = self.hub.status(flow['id'])
        self.assertEqual(state['status'], 'blocked')
        self.assertEqual(state['calls'], 1)
        self.assertEqual(state['max_calls'], flow['max_calls'])
        self.assertEqual(self.hub.store.all('SELECT * FROM health'), health_before)
        self.assertEqual(state['attempts'][0]['usage']['failure_category'], 'task_blocked')
        self.assertTrue(any(event['kind'] == 'task_blocked' for event in state['events']))
        self.assertFalse(engine.tick())

    def test_scope_verifier_and_nested_documents_reach_planner(self):
        nested = self.source / 'Nested App'
        nested.mkdir()
        (nested / 'build.gradle.kts').write_text('plugins { id("synthetic-android") }\n', encoding='utf-8')
        git(self.source, 'add', 'Nested App/build.gradle.kts')
        git(self.source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'Nested synthetic manifest')
        initialize(self.hub, self.source)
        flow = self.hub.start('demo', 'Guide for Nested App', 'pack-case', mode='standard', launch=False)
        class Capture:
            def run(inner, provider, role, context, *args):
                inner.context = context
                return Result(report=report(role))
        invoker = Capture()
        Engine(self.hub.store, self.hub.config, invoker).tick()
        self.assertIn('"synthetic_data_only": true', invoker.context)
        self.assertIn('NONE permitted', invoker.context)
        self.assertIn('CONFIGURED VERIFIER', invoker.context)
        self.assertLess(invoker.context.index('CONFIGURED VERIFIER'), invoker.context.index('OBJECTIVE:'))
        self.assertIn('unittest', invoker.context)
        self.assertIn('synthetic-android', invoker.context)
        self.assertIn('LAST VERIFICATION RESULTS', invoker.context)
        state = self.hub.store.workflow(flow['id'])
        unknown = build_pack(self.hub.store, state, self.project, 'plan', 40000)['text']
        self.assertIn('"synthetic_data_only": "UNKNOWN"', unknown)

    def test_monitor_watch_only_renders_changed_evidence(self):
        from agenthub.cli import main
        flow = self.hub.start('demo', 'Technical guide', 'monitor-case', launch=False)
        first = self.hub.status(flow['id'])
        second = copy.deepcopy(first)
        second.update(status='blocked', error='Operator action required')
        with patch('agenthub.cli.Hub.status', side_effect=[first, first, second]), \
                patch('agenthub.cli.time.sleep'), patch('sys.stdout', new_callable=io.StringIO) as out:
            main(['--home', str(self.hub.store.home), 'status', flow['id'], '--watch'])
        self.assertEqual(out.getvalue().count('Workflow:'), 2)

    def test_waiting_monitor_shows_scheduled_retry(self):
        from agenthub.monitor import render
        flow = self.hub.start('demo', 'Technical guide', 'waiting-case', launch=False)
        state = self.hub.status(flow['id'])
        state.update(status='waiting', next_run=time.time() + 400000)
        self.assertIn('Next retry:', render(state))

    def test_execution_discovery_share_fallback_without_overriding_custom_command(self):
        from agenthub.registry import execution_command, discover_agent
        def resolver(command):
            if command == ['synthetic-installed-agy']:
                return [sys.executable]
            raise FileNotFoundError('synthetic missing binary')
        with patch('agenthub.registry.common_candidates', return_value=[['synthetic-installed-agy']]), \
                patch('agenthub.registry.resolve_command', side_effect=resolver):
            self.assertEqual(execution_command('antigravity', {'command': ['agy']}), [sys.executable])
            self.assertEqual(discover_agent('antigravity', {'command': ['agy']})['state'], 'INSTALLED')
            with self.assertRaises(FileNotFoundError):
                execution_command('antigravity', {'command': ['custom-unavailable-agy']})
            self.assertEqual(discover_agent('antigravity', {'command': ['custom-unavailable-agy']})['state'], 'NOT_INSTALLED')

    def test_windows_long_path_worktree_can_be_archived_and_removed(self):
        if os.name != 'nt':
            self.skipTest('Windows long-path regression')
        relative = Path('long-path-fixture').joinpath(*(['generated-deep-synthetic-directory'] * 12), 'proof.py')
        target = (self.source / relative).resolve()
        assert target.is_relative_to(self.source.resolve())
        extended = Path('\\\\?\\' + str(target))
        extended.parent.mkdir(parents=True)
        extended.write_text('VALUE = "synthetic"\n', encoding='utf-8')
        git(self.source, 'add', 'long-path-fixture')
        git(self.source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'Long path fixture')
        worktree = (Path(self.temp.name) / 'long-path-worktree').resolve()
        assert worktree.is_relative_to(Path(self.temp.name).resolve())
        try:
            git(self.source, 'worktree', 'add', '--detach', str(worktree), 'HEAD')
            archive = Path(self.temp.name) / 'long-path-source.zip'
            git(worktree, 'archive', '--format=zip', '--output=' + str(archive), 'HEAD')
            import zipfile
            with zipfile.ZipFile(archive) as saved:
                self.assertIsNone(saved.testzip())
                self.assertEqual(saved.read(relative.as_posix()).replace(b'\r\n', b'\n'), b'VALUE = "synthetic"\n')
            git(self.source, 'worktree', 'remove', '--force', str(worktree))
            self.assertFalse(worktree.exists())
        finally:
            # Only explicit directories created by this test, within its own temp root.
            for owned in (worktree, self.source / 'long-path-fixture'):
                assert owned.resolve().is_relative_to(Path(self.temp.name).resolve())
                if owned.exists():
                    shutil.rmtree('\\\\?\\' + str(owned.resolve()))
