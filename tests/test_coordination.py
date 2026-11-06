import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from agenthub.adapters import REPORT_SCHEMA, validate_report, Result
from agenthub.api import Hub
from agenthub.config import defaults
from agenthub.demo_fixture import write_demo
from agenthub.engine import Engine
from agenthub.registry import AGENT_PROFILES
from agenthub.simulation import DEMO_CODE, DEMO_TEST, report
from agenthub.workspace import git


class CoordinationTests(unittest.TestCase):
    def test_agent_profiles_exist(self):
        self.assertIn('antigravity', AGENT_PROFILES)
        self.assertIn('claude', AGENT_PROFILES)
        self.assertIn('codex', AGENT_PROFILES)
        self.assertIn('copilot', AGENT_PROFILES)
        self.assertIn('strengths', AGENT_PROFILES['antigravity'])

    def test_validate_report_with_assigned_worker(self):
        rep = report('plan', assigned_worker='codex')
        validated = validate_report(rep)
        self.assertEqual(validated['assigned_worker'], 'codex')

    def test_validate_report_with_subtasks(self):
        rep = report('plan')
        rep['subtasks'] = [{'title': 'Write tests', 'agent': 'codex'}]
        validated = validate_report(rep)
        self.assertEqual(validated['subtasks'][0]['agent'], 'codex')

    def test_always_start_with_plan(self):
        with tempfile.TemporaryDirectory(prefix='agenthub-test-') as tmp:
            tmp_path = Path(tmp)
            hub = Hub(tmp_path / 'state')
            source = tmp_path / 'source'
            write_demo(source)
            git(source, 'init')
            git(source, 'add', '.')
            git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'Baseline')
            hub.store.add_project('demo', source, [['{python}', '-m', 'unittest']], ['app'])
            # Even with mode='small', workflow must start in phase='plan'
            flow = hub.start('demo', 'Fix minor typo in readme', 'req-1', mode='small', launch=False)
            self.assertEqual(flow['phase'], 'plan')

    def test_delegated_worker_and_analyst_review(self):
        # Leader is claude, assigns codex as worker, then claude reviews.
        with tempfile.TemporaryDirectory(prefix='agenthub-test-') as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / 'source'
            write_demo(source)
            git(source, 'init')
            git(source, 'add', '.')
            git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'Baseline')
            hub = Hub(tmp_path / 'state')
            config = defaults()
            config['retention']['archive_completed_worktrees'] = False
            config['leader_priority'] = ['claude', 'codex']
            config['worker_priority'] = ['antigravity', 'codex', 'claude']
            config['reviewer_priority'] = ['claude', 'antigravity', 'codex']
            for entry in config['providers'].values():
                entry['command'] = [sys.executable]
            hub.config = config
            project = hub.store.add_project('demo', source,
                [['{python}', '-m', 'unittest', 'discover', '-s', 'tests', '-v']], ['README.md', 'app', 'tests'])

            calls = []
            class MockInvoker:
                def run(self, provider, role, context, workspace, folder, network, on_pid, cancelled):
                    calls.append((provider, role))
                    if role == 'implement':
                        (Path(workspace) / 'app/tasks.py').write_text(DEMO_CODE, encoding='utf-8')
                        (Path(workspace) / 'tests/test_filter.py').write_text(DEMO_TEST, encoding='utf-8')
                    rep = report(role, assigned_worker='codex')
                    return Result(report=rep)

            invoker = MockInvoker()
            engine = Engine(hub.store, hub.config, invoker)
            flow = hub.start('demo', 'Implement filter feature', 'req-delegated', launch=False)

            for _ in range(10):
                if not engine.tick():
                    break
                if hub.store.workflow(flow['id'])['status'] in {'completed', 'blocked', 'needs_review'}:
                    break

            final = hub.status(flow['id'])
            self.assertEqual(final['status'], 'completed')
            # 1: claude plans (and assigns codex)
            # 2: codex implements (assigned by claude)
            # 3: claude reviews!
            self.assertEqual(calls, [('claude', 'plan'), ('codex', 'implement'), ('claude', 'review')])

    def test_self_assignment_and_analyst_review(self):
        # Leader is claude, assigns claude as worker (self-assignment), then claude reviews.
        with tempfile.TemporaryDirectory(prefix='agenthub-test-') as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / 'source'
            write_demo(source)
            git(source, 'init')
            git(source, 'add', '.')
            git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'Baseline')
            hub = Hub(tmp_path / 'state')
            config = defaults()
            config['retention']['archive_completed_worktrees'] = False
            config['leader_priority'] = ['claude', 'codex']
            config['worker_priority'] = ['codex', 'claude']
            config['reviewer_priority'] = ['codex', 'claude']
            for entry in config['providers'].values():
                entry['command'] = [sys.executable]
            hub.config = config
            project = hub.store.add_project('demo', source,
                [['{python}', '-m', 'unittest', 'discover', '-s', 'tests', '-v']], ['README.md', 'app', 'tests'])

            calls = []
            class MockInvoker:
                def run(self, provider, role, context, workspace, folder, network, on_pid, cancelled):
                    calls.append((provider, role))
                    if role == 'implement':
                        (Path(workspace) / 'app/tasks.py').write_text(DEMO_CODE, encoding='utf-8')
                        (Path(workspace) / 'tests/test_filter.py').write_text(DEMO_TEST, encoding='utf-8')
                    rep = report(role, assigned_worker='claude')
                    return Result(report=rep)

            invoker = MockInvoker()
            engine = Engine(hub.store, hub.config, invoker)
            flow = hub.start('demo', 'Implement filter feature', 'req-self-assigned', launch=False)

            for _ in range(10):
                if not engine.tick():
                    break
                if hub.store.workflow(flow['id'])['status'] in {'completed', 'blocked', 'needs_review'}:
                    break

            final = hub.status(flow['id'])
            self.assertEqual(final['status'], 'completed')
            # 1: claude plans (and assigns claude)
            # 2: claude implements (self-assigned)
            # 3: claude reviews!
            self.assertEqual(calls, [('claude', 'plan'), ('claude', 'implement'), ('claude', 'review')])

    def test_auto_init_unregistered_git_project(self):
        import os
        from agenthub.cli import current_project
        with tempfile.TemporaryDirectory(prefix='agenthub-test-') as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / 'source'
            write_demo(source)
            git(source, 'init')
            git(source, 'add', '.')
            git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'Baseline')
            hub = Hub(tmp_path / 'state')
            old_cwd = os.getcwd()
            try:
                os.chdir(source)
                name = current_project(hub, auto_init=True)
                self.assertTrue(name.startswith('source-'))
                project = hub.store.project(name)
                self.assertEqual(Path(project['path']).resolve(), source.resolve())
            finally:
                os.chdir(old_cwd)

    def test_auto_init_non_git_project(self):
        import os
        from agenthub.cli import current_project
        with tempfile.TemporaryDirectory(prefix='agenthub-test-') as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / 'source_nongit'
            write_demo(source)
            # Notice: No git init here!
            hub = Hub(tmp_path / 'state')
            old_cwd = os.getcwd()
            try:
                os.chdir(source)
                name = current_project(hub, auto_init=True)
                self.assertTrue(name.startswith('source_nongit-'))
                project = hub.store.project(name)
                self.assertEqual(Path(project['path']).resolve(), source.resolve())

                # Also verify workspace.prepare works on this non-git project
                from agenthub.workspace import prepare
                workflow = {'id': 'wf-nongit', 'workspace': None, 'base_commit': None}
                ws_path, commit = prepare(hub.store, workflow, project)
                self.assertTrue(Path(ws_path).exists())
                self.assertTrue((Path(ws_path) / '.git').exists())
                # Source must remain clean and without a .git folder!
                self.assertFalse((source / '.git').exists())
            finally:
                os.chdir(old_cwd)

    def test_project_without_verification_commands(self):
        # Projects without test runners (e.g. static HTML/CSS, docs) can run and complete
        with tempfile.TemporaryDirectory(prefix='agenthub-test-') as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / 'source_web'
            source.mkdir()
            (source / 'index.html').write_text('<h1>Hello</h1>', encoding='utf-8')
            hub = Hub(tmp_path / 'state')
            config = defaults()
            config['retention']['archive_completed_worktrees'] = False
            config['leader_priority'] = ['claude']
            config['worker_priority'] = ['codex']
            config['reviewer_priority'] = ['claude']
            for entry in config['providers'].values():
                entry['command'] = [sys.executable]
            hub.config = config
            # Explicitly add project with NO verification command (verify=[])
            project = hub.store.add_project('web-demo', source, [], ['index.html'], allow_unverified=True)

            calls = []
            class MockInvoker:
                def run(self, provider, role, context, workspace, folder, network, on_pid, cancelled):
                    calls.append((provider, role))
                    if role == 'implement':
                        (Path(workspace) / 'style.css').write_text('body { margin: 0; }', encoding='utf-8')
                    rep = report(role, assigned_worker='codex')
                    return Result(report=rep)

            invoker = MockInvoker()
            engine = Engine(hub.store, hub.config, invoker)
            flow = hub.start('web-demo', 'Create dashboard with html, css', 'req-web', launch=False)

            for _ in range(10):
                if not engine.tick():
                    break
                if hub.store.workflow(flow['id'])['status'] in {'completed', 'blocked', 'needs_review'}:
                    break

            final = hub.status(flow['id'])
            self.assertEqual(final['status'], 'completed')
            self.assertEqual(calls, [('claude', 'plan'), ('codex', 'implement'), ('claude', 'review')])

    def test_workflow_with_uncommitted_changes(self):
        with tempfile.TemporaryDirectory(prefix='agenthub-test-') as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / 'source'
            write_demo(source)
            git(source, 'init')
            git(source, 'add', '.')
            git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'Baseline')
            # Add uncommitted modification and untracked file
            (source / 'main.py').write_text('# modified uncommitted', encoding='utf-8')
            (source / 'extra.txt').write_text('untracked file', encoding='utf-8')

            hub = Hub(tmp_path / 'state')
            project = hub.store.add_project('uncommitted-demo', source, [['python', '-c', 'exit(0)']], ['main.py'])
            flow = hub.start('uncommitted-demo', 'Task with dirty worktree', 'req-dirty', launch=False)
            
            from agenthub.workspace import prepare, clone_file, copy_tree_cow
            ws_path, commit = prepare(hub.store, flow, project)
            self.assertTrue(Path(ws_path).exists())
            self.assertEqual((Path(ws_path) / 'main.py').read_text(encoding='utf-8'), '# modified uncommitted')
            self.assertEqual((Path(ws_path) / 'extra.txt').read_text(encoding='utf-8'), 'untracked file')

    def test_copy_tree_cow_and_clone(self):
        with tempfile.TemporaryDirectory(prefix='agenthub-test-cow-') as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / 'source_cow'
            src.mkdir()
            (src / 'file1.txt').write_text('content 1', encoding='utf-8')
            (src / 'nested').mkdir()
            (src / 'nested' / 'file2.txt').write_text('content 2', encoding='utf-8')

            dst = tmp_path / 'dest_cow'
            from agenthub.workspace import copy_tree_cow, clone_file
            copy_tree_cow(src, dst)
            self.assertTrue((dst / 'file1.txt').is_file())
            self.assertEqual((dst / 'file1.txt').read_text(encoding='utf-8'), 'content 1')
            self.assertTrue((dst / 'nested' / 'file2.txt').is_file())
            self.assertEqual((dst / 'nested' / 'file2.txt').read_text(encoding='utf-8'), 'content 2')

            # Test single clone_file
            single_dst = tmp_path / 'file1_clone.txt'
            self.assertTrue(clone_file(src / 'file1.txt', single_dst))
            self.assertEqual(single_dst.read_text(encoding='utf-8'), 'content 1')

    def test_sparse_checkout(self):
        with tempfile.TemporaryDirectory(prefix='agenthub-test-sparse-') as tmp:
            tmp_path = Path(tmp)
            repo = tmp_path / 'repo_sparse'
            repo.mkdir()
            git(repo, 'init')
            git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'config', 'user.name', 'Test')
            git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'config', 'user.email', 'test@localhost')
            (repo / 'file_a.txt').write_text('aaa', encoding='utf-8')
            (repo / 'file_b.txt').write_text('bbb', encoding='utf-8')
            (repo / 'dir').mkdir()
            (repo / 'dir' / 'file_c.txt').write_text('ccc', encoding='utf-8')
            git(repo, 'add', '.')
            git(repo, 'commit', '-m', 'Init')

            from agenthub.workspace import apply_sparse_checkout, disable_sparse_checkout
            applied = apply_sparse_checkout(repo, ['file_a.txt', 'dir/file_c.txt'])
            if applied:
                self.assertTrue((repo / 'file_a.txt').exists())
                self.assertFalse((repo / 'file_b.txt').exists())
                self.assertTrue((repo / 'dir' / 'file_c.txt').exists())

                disabled = disable_sparse_checkout(repo)
                self.assertTrue(disabled)
                self.assertTrue((repo / 'file_b.txt').exists())

    def test_open_in_editor(self):
        from unittest.mock import patch
        from agenthub.cli import open_in_editor

        self.assertEqual(open_in_editor([]), 'none')
        self.assertEqual(open_in_editor(None), 'none')

        with patch('shutil.which', return_value='/usr/bin/code'), \
             patch('subprocess.Popen') as mock_popen:
            res = open_in_editor(['/tmp/file1.js', '/tmp/file2.html'])
            self.assertEqual(res, 'editor')
            mock_popen.assert_called_once_with(
                ['/usr/bin/code', '-r', '/tmp/file1.js', '/tmp/file2.html'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        with patch('shutil.which', return_value=None), \
             patch('os.name', 'nt'), \
             patch('os.startfile', create=True) as mock_startfile:
            res = open_in_editor(['C:\\path\\file.txt'])
            self.assertEqual(res, 'startfile')
            mock_startfile.assert_called_once_with('C:\\path\\file.txt')


if __name__ == '__main__':
    unittest.main()


