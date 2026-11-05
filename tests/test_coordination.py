import json
from pathlib import Path
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


if __name__ == '__main__':
    unittest.main()

