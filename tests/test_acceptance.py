"""Real file application on disposable synthetic repositories; no model calls."""
import tempfile
import subprocess
import sys
import os
from unittest.mock import patch
import unittest
from pathlib import Path

from agenthub.acceptance import accept, mode
from agenthub.engine import Engine
from agenthub.simulation import setup_fixture, SimulatedInvoker
from agenthub.workspace import git


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ma-accept-')
        self.addCleanup(self.tmp.cleanup)
        self.hub, self.source, self.project = setup_fixture(self.tmp.name)
        self.hub.config['retention']['archive_completed_worktrees'] = True
        self.flow = self.hub.start('demo', 'Add task filtering', 'accept-test', launch=False)

    def finish(self):
        engine = Engine(self.hub.store, self.hub.config, SimulatedInvoker(False))
        for _ in range(20):
            if not engine.tick(): break
        flow = self.hub.store.workflow(self.flow['id'])
        self.assertEqual(flow['status'], 'completed', flow['error'])
        self.assertTrue(flow['delivery'])
        return flow

    def test_default_waits_then_accept_writes_files_without_commit(self):
        before = git(self.source, 'rev-parse', 'HEAD')
        flow = self.finish()
        self.assertFalse(mode(self.hub.store, self.project['id'])['auto_accept'])
        self.assertFalse(git(self.source, 'status', '--porcelain'))
        result = accept(self.hub.store, flow['id'])
        self.assertEqual(result['status'], 'accepted')
        self.assertTrue(git(self.source, 'status', '--porcelain'))
        self.assertEqual(git(self.source, 'rev-parse', 'HEAD'), before)
        checked = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'],
                                 cwd=self.source, capture_output=True, text=True, timeout=15)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(accept(self.hub.store, flow['id']), result)
        self.assertEqual(self.hub.brief(flow['id'])['acceptance']['status'], 'accepted')

    def test_dirty_source_is_preserved(self):
        flow = self.finish()
        marker = Path(self.source) / 'user-change.txt'
        marker.write_text('synthetic user edit')
        before = git(self.source, 'status', '--porcelain')
        with self.assertRaisesRegex(ValueError, 'Project changed'):
            accept(self.hub.store, flow['id'])
        self.assertEqual(marker.read_text(), 'synthetic user edit')
        self.assertEqual(git(self.source, 'status', '--porcelain'), before)

    def test_auto_accept_is_project_opt_in(self):
        mode(self.hub.store, self.project['id'], True)
        self.finish()
        self.assertTrue(git(self.source, 'status', '--porcelain'))
        self.assertTrue(self.hub.brief(self.flow['id'])['acceptance']['automatic'])
        mode(self.hub.store, self.project['id'], False)
        self.assertFalse(mode(self.hub.store, self.project['id'])['auto_accept'])

    def test_running_workflow_cannot_be_accepted(self):
        with self.assertRaisesRegex(ValueError, 'Only completed'):
            accept(self.hub.store, self.flow['id'])

    def test_worker_cannot_approve_or_enable_auto_accept(self):
        with patch.dict(os.environ, {'MULTI_AGENTS_WORKER': '1'}):
            with self.assertRaisesRegex(ValueError, 'Workers cannot'):
                accept(self.hub.store, self.flow['id'])
            with self.assertRaisesRegex(ValueError, 'Workers cannot'):
                mode(self.hub.store, self.project['id'], True)

    def test_ignored_existing_file_is_not_read_or_overwritten(self):
        flow = self.finish()
        ignore = Path(self.tmp.name) / 'synthetic-ignore'
        ignore.write_text('tests/test_filter.py\n')
        git(self.source, 'config', 'core.excludesFile', str(ignore))
        target = Path(self.source) / 'tests/test_filter.py'
        target.write_text('synthetic file owned by user')
        self.assertFalse(git(self.source, 'status', '--porcelain'))
        with self.assertRaisesRegex(ValueError, 'ignored file'):
            accept(self.hub.store, flow['id'])
        self.assertEqual(target.read_text(), 'synthetic file owned by user')
