import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agenthub.quick_setup import apply, login, plan, open_interface
from agenthub.simulation import setup_fixture


class QuickSetupTests(unittest.TestCase):
    def interface_record(self):
        import sys
        from agenthub.config import ROOT
        folder = self.hub.store.home / 'integrations'
        folder.mkdir(exist_ok=True)
        version = json.loads((ROOT / 'integrations/vscode-chat/package.json').read_text())['version']
        path = folder / 'vscode-chat.json'
        path.write_text(json.dumps({'source': str(ROOT), 'python': sys.executable, 'version': version}))
        return path, version

    def test_interface_opens_fixed_uri_without_applying_or_installing(self):
        import subprocess
        from agenthub.chat_bridge import EXTENSION_ID
        _, version = self.interface_record()
        calls = []
        before = (self.hub.store.home / 'config.json').read_bytes()
        def run(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, EXTENSION_ID + '@' + version + '\n', '')
        with patch('shutil.which', return_value='synthetic-code'), patch('agenthub.chat_bridge.code_command', return_value=(['code-bin'], {})):
            result = open_interface(self.hub, run)
        self.assertEqual(calls[-1][0], ['code-bin', '--open-url', '--reuse-window', 'vscode://' + EXTENSION_ID + '/setup'])
        self.assertNotIn('shell', calls[-1][1])
        self.assertIn('request sent', result['status'])
        self.assertEqual((self.hub.store.home / 'config.json').read_bytes(), before)

    def test_interface_missing_outdated_or_foreign_install_is_not_overwritten(self):
        with patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'VS Code CLI not found'): open_interface(self.hub)
        with patch('shutil.which', return_value='synthetic-code'):
            with self.assertRaisesRegex(ValueError, 'Run ma setup first'): open_interface(self.hub)
            path, _ = self.interface_record()
            value = json.loads(path.read_text())
            for changed, message in [({'version': '0.0.0'}, 'Update'), ({'source': 'other-source'}, 'another source')]:
                path.write_text(json.dumps({**value, **changed}))
                with self.assertRaisesRegex(ValueError, message): open_interface(self.hub)
        with patch.dict(os.environ, {'MULTI_AGENTS_WORKER': '1'}):
            with self.assertRaisesRegex(ValueError, 'Workers'): open_interface(self.hub)

    def test_interface_rejected_or_missing_extension_does_not_claim_opened(self):
        import subprocess
        from agenthub.chat_bridge import EXTENSION_ID
        _, version = self.interface_record()
        with patch('shutil.which', return_value='synthetic-code'), patch('agenthub.chat_bridge.code_command', return_value=(['code-bin'], {})):
            with self.assertRaisesRegex(ValueError, 'missing/outdated'):
                open_interface(self.hub, lambda args, **kw: subprocess.CompletedProcess(args, 0, '', ''))
            def failing(args, **kw):
                return subprocess.CompletedProcess(args, 0 if '--list-extensions' in args else 1, EXTENSION_ID + '@' + version, '')
            with self.assertRaisesRegex(ValueError, 'could not open'):
                open_interface(self.hub, failing)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ma-quick-setup-')
        self.addCleanup(self.tmp.cleanup)
        self.hub, self.source, self.project = setup_fixture(self.tmp.name)
        self.before = copy.deepcopy(self.hub.config)

    def test_one_apply_sets_shared_inherit_and_keeps_security_commands_and_roles(self):
        from agenthub.settings import atomic_json
        atomic_json(self.hub.store.home / 'config.json', self.hub.config)
        result = apply(self.hub, ['codex', 'copilot'], {})
        self.assertFalse(result['security_changed'])
        self.assertTrue(Path(result['backup']).exists())
        self.assertEqual(self.hub.config['security'], self.before['security'])
        for name in ('codex', 'copilot'):
            self.assertEqual(self.hub.config['providers'][name]['model_policy'], 'INHERIT')
            self.assertEqual(self.hub.config['providers'][name]['command'], self.before['providers'][name]['command'])
            self.assertEqual(self.hub.config['providers'][name]['roles'], self.before['providers'][name]['roles'])
        self.assertFalse(self.hub.config['providers']['claude']['enabled'])

    def test_setup_plan_keeps_unknown_and_does_not_write_source(self):
        rows = [{'agent': 'codex', 'enabled': True, 'state': 'INSTALLED', 'authentication': 'UNKNOWN'}]
        from agenthub.workspace import git
        before = git(self.source, 'status', '--porcelain')
        with patch('agenthub.quick_setup.discover', return_value=rows):
            value = plan(self.hub)
        self.assertEqual(value['agents'][0]['authentication'], 'UNKNOWN')
        self.assertEqual(value['policy'], 'INHERIT')
        self.assertEqual(git(self.source, 'status', '--porcelain'), before)

    def test_invalid_options_and_worker_cannot_apply_or_open_login(self):
        for providers, actions in [([], {}), (['invalid'], {}), (['codex'], {'security': True}), (['codex'], {'chat': 'yes'})]:
            with self.assertRaises(ValueError):
                apply(self.hub, providers, actions)
        with patch.dict(os.environ, {'MULTI_AGENTS_WORKER': '1'}):
            with self.assertRaises(ValueError): apply(self.hub, ['codex'], {})
            with self.assertRaises(ValueError): login(self.hub, 'codex')

    def test_active_workflow_blocks_setup_and_login(self):
        self.hub.start('demo', 'Synthetic task', 'active', launch=False)
        with self.assertRaises(ValueError): apply(self.hub, ['codex'], {})
        with self.assertRaises(ValueError): login(self.hub, 'codex')

    def test_optional_failure_rolls_back_config_and_keeps_backup(self):
        before = json.loads((self.hub.store.home / 'config.json').read_text())
        with patch('agenthub.chat_bridge.install', side_effect=OSError('Synthetic failure')):
            with self.assertRaises(OSError): apply(self.hub, ['codex'], {'chat': True})
        self.assertEqual(json.loads((self.hub.store.home / 'config.json').read_text()), before)

    def test_official_login_is_argument_array_without_reading_auth_or_claiming_ready(self):
        import subprocess
        commands = []
        result = login(self.hub, 'copilot', runner=lambda args: (commands.append(args) or subprocess.CompletedProcess(args, 0)))
        self.assertEqual(commands[0][-1], 'login')
        self.assertEqual(result['authentication'], 'UNKNOWN')
