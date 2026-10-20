"""POSIX launcher/integration regression: local synthetic sources, no provider calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agenthub.config import ROOT
from agenthub.lifecycle import install_command, uninstall
from agenthub.workspace import git


@unittest.skipIf(os.name == 'nt', 'POSIX shell executable semantics')
class PosixLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ma-posix-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "Tiếng Việt user's state"

    def install(self, **kwargs):
        return install_command(self.home, which=kwargs.get('which', lambda _: None))

    def test_pinned_launcher_handles_unicode_quotes_and_preserves_project_cwd(self):
        source = self.base / 'synthetic project'
        (source / 'tests').mkdir(parents=True)
        (source / 'tests/test_example.py').write_text('import unittest\n')
        git(source, 'init'); git(source, 'add', '.')
        result = self.install()
        launcher = Path(result['installed'])
        self.assertTrue(os.access(launcher, os.X_OK))
        before = git(source, 'status', '--porcelain')
        command = [str(launcher), 'init', '--register-only', '--name', 'ubuntu-demo', '--json']
        run = subprocess.run(command, cwd=source / 'tests', capture_output=True, encoding='utf-8', timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)
        payload = json.loads(run.stdout)
        self.assertIn('ubuntu-demo', run.stdout)
        self.assertEqual(git(source, 'status', '--porcelain'), before)
        from agenthub.api import Hub
        hub = Hub(self.home)
        self.assertEqual(hub.store.project('ubuntu-demo')['path'], str(source.resolve()))
        self.assertEqual(hub.store.all('SELECT * FROM workflows'), [])
        self.assertFalse(hub.config['security']['synthetic_data_only'])
        self.assertFalse((source / 'data').exists())
        self.assertIn('shell_command', result)

    def test_idempotent_uninstall_preserves_config_and_source(self):
        first = self.install()
        launcher = Path(first['installed'])
        self.assertEqual(self.install(which=lambda _: str(launcher))['installed'], first['installed'])
        marker = self.home / 'synthetic-marker.txt'
        marker.write_text('keep')
        uninstall(self.home)
        self.assertFalse(launcher.exists())
        self.assertEqual(marker.read_text(), 'keep')
        self.assertTrue((ROOT / 'ma').exists())

    def test_collision_unowned_and_modified_launchers_are_preserved(self):
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.install(which=lambda _: '/some/other/ma')
        self.assertFalse(self.home.exists())
        target = self.home / 'runtime/bin/ma'
        target.parent.mkdir(parents=True)
        target.write_text('unowned')
        with self.assertRaisesRegex(ValueError, 'Unowned'):
            self.install()
        self.assertEqual(target.read_text(), 'unowned')
        target.unlink()
        self.install()
        target.write_text('externally changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.install()
        with self.assertRaisesRegex(ValueError, 'changed'):
            uninstall(self.home)
        self.assertEqual(target.read_text(), 'externally changed')

    def test_symlink_parent_cannot_write_outside_owned_home(self):
        outside = self.base / 'outside'
        outside.mkdir()
        runtime = self.home / 'runtime'
        runtime.mkdir(parents=True)
        (runtime / 'bin').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])

    def test_linux_vscode_uses_xdg_config_not_windows_appdata(self):
        from agenthub.integrations import client_target
        with patch('agenthub.integrations.sys.platform', 'linux'), \
                patch('agenthub.integrations.Path.home', return_value=self.base), \
                patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.base / 'xdg'), 'APPDATA': 'ignore-windows'}):
            self.assertEqual(client_target('vscode'), self.base / 'xdg/Code/User/mcp.json')

    def test_mcp_advertises_normal_prompt_routing_without_source_mutation(self):
        request = json.dumps({'jsonrpc':'2.0', 'id':1, 'method':'initialize', 'params':{}}) + '\n'
        result = subprocess.run([sys.executable, str(ROOT/'ma.py'), '--home', str(self.home), 'mcp'],
                                input=request, capture_output=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        instructions = json.loads(result.stdout)['result']['instructions']
        self.assertIn('ordinary coding requests', instructions)
        self.assertIn('exact current workspace Git root', instructions)
        self.assertIn('Do not change security flags', instructions)
        self.assertFalse((ROOT/'scope.json').exists())

    def test_default_four_provider_commands_are_portable_and_do_not_attest_scope(self):
        from agenthub.config import defaults
        from agenthub.registry import validate_entry
        config = defaults()
        for name, command in [('codex','codex'), ('claude','claude'), ('copilot','copilot'), ('antigravity','agy')]:
            entry = config['providers'][name]
            self.assertEqual(entry['command'], [command])
            self.assertTrue(entry['enabled'])
            validate_entry(name, entry)
        self.assertFalse(config['security']['synthetic_data_only'])
        self.assertFalse(config['security']['isolated_test_environment'])

    def test_user_local_native_clis_discovered_without_path_or_reading_auth(self):
        from agenthub.registry import discover_agent
        fake = self.base / '.local/bin'
        fake.mkdir(parents=True)
        for name, command in [('codex','codex'), ('claude','claude'), ('copilot','copilot'), ('antigravity','agy')]:
            binary = fake / command
            binary.write_bytes(b'synthetic marker, never executed')
            with patch('agenthub.registry.Path.home', return_value=self.base), \
                    patch('agenthub.registry.shutil.which', return_value=None):
                value = discover_agent(name, {'command':[command]}, check=False,
                                       runner=lambda _: self.fail('No model/auth probe allowed'))
            self.assertEqual(value['command'], [str(binary.resolve())])
            self.assertEqual(value['state'], 'INSTALLED')
            self.assertEqual(value['authentication'], 'UNKNOWN')
