import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agenthub.api import Hub
from agenthub.config import ROOT
from agenthub.discovery import identify
from agenthub.workspace import git


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-discovery-')
        self.base = Path(self.temp.name)
        self.hub = Hub(self.base / 'hub-data')
        self.source = self.base / 'project with spaces'
        self.source.mkdir()
        git(self.source, 'init')
        (self.source / 'tests').mkdir()
        (self.source / 'tests/test_example.py').write_text('raise RuntimeError("must not execute")\n')
        git(self.source, 'add', '.')

    def tearDown(self):
        self.temp.cleanup()

    def test_subfolder_detects_root_without_starting_or_changing_source(self):
        result = identify(self.hub, self.source / 'tests')
        self.assertTrue(result['created'])
        self.assertEqual(result['project']['path'], str(self.source.resolve()))
        self.assertEqual(result['ai_calls'], 0)
        self.assertEqual(self.hub.store.all('SELECT * FROM workflows'), [])
        self.assertFalse(self.hub.config['security']['isolated_test_environment'])
        self.assertEqual((self.source / 'tests/test_example.py').read_text(), 'raise RuntimeError("must not execute")\n')

    def test_repeat_recovers_existing_name_and_memory(self):
        first = identify(self.hub, self.source, name='my-project')
        self.hub.store.remember(first['project']['id'], 'decision', 'Synthetic fixture only')
        second = identify(self.hub, self.source / 'tests')
        self.assertFalse(second['created'])
        self.assertEqual(second['project']['id'], first['project']['id'])
        self.assertEqual(second['context']['memories'][0]['content'], 'Synthetic fixture only')
        self.assertEqual(len(self.hub.store.all('SELECT * FROM projects')), 1)

    def test_same_basename_separate_repos_get_distinct_names(self):
        other = self.base / 'another' / self.source.name
        other.mkdir(parents=True)
        git(other, 'init')
        a = identify(self.hub, self.source)
        b = identify(self.hub, other, verify=[['node', '--test']])
        self.assertNotEqual(a['project']['name'], b['project']['name'])

    def test_unknown_or_mixed_project_needs_explicit_checks(self):
        (self.source / 'package.json').write_text('not read as JSON')
        git(self.source, 'add', 'package.json')
        with self.assertRaisesRegex(ValueError, 'Pass --verify'):
            identify(self.hub, self.source)
        self.assertEqual(self.hub.store.all('SELECT * FROM projects'), [])
        result = identify(self.hub, self.source, verify=[['node', '--test']])
        self.assertEqual(json.loads(result['project']['verify']), [['node', '--test']])

    def test_existing_settings_are_not_silently_overwritten(self):
        identify(self.hub, self.source)
        with self.assertRaisesRegex(ValueError, 'not overwrite'):
            identify(self.hub, self.source, verify=[['different', 'command']])

    def test_outside_git_fails_without_creating_repo(self):
        folder = self.base / 'empty'
        folder.mkdir()
        # TMPDIR can itself be nested inside an unrelated Git checkout.
        with patch.dict(os.environ, {'GIT_CEILING_DIRECTORIES': str(self.base)}), \
                self.assertRaisesRegex(ValueError, 'Not inside a Git project'):
            identify(self.hub, folder)
        self.assertFalse((folder / '.git').exists())

    def test_cli_preserves_caller_directory_and_supports_spaces(self):
        result = subprocess.run([sys.executable, str(ROOT / 'hub.py'), '--home', str(self.base / 'cli data'), 'here'],
                                cwd=self.source / 'tests', capture_output=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['project']['path'], str(self.source.resolve()))
        self.assertTrue(payload['created'])
