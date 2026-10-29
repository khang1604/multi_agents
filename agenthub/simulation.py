"""Offline integration demonstration. It never invokes a real model."""
import json
from pathlib import Path
import sys
import tempfile

from .demo_fixture import write_demo
from .adapters import Result
from .api import Hub
from .config import ROOT, defaults
from .engine import Engine
from .workspace import git

DEMO_CODE = '''def list_tasks(tasks, status="all", query=""):
    if status not in {"all", "done", "pending"}:
        raise ValueError("invalid status")
    query = query.strip().casefold()
    return [task for task in tasks
            if (status == "all" or bool(task.get("done", False)) == (status == "done"))
            and query in task.get("title", "").casefold()]
'''
DEMO_TEST = '''import unittest
from app.tasks import list_tasks
class FilterTests(unittest.TestCase):
    def test_combined(self):
        tasks = [{"title": "CODEX", "done": True}, {"title": "Codex", "done": False}]
        self.assertEqual(list_tasks(tasks, "done", " codex "), [tasks[0]])
    def test_invalid(self):
        with self.assertRaises(ValueError): list_tasks([], "bad")
'''


def report(role, complexity='standard', verdict='approve', findings=None):
    """Build a synthetic role report for offline orchestration tests."""
    return {'outcome': 'completed', 'summary': 'SIMULATED ' + role,
            'steps': ['Inspect code', 'Implement task filtering', 'Run verification'],
            'acceptance': ['Compatible API', 'Filtering works', 'Tests pass'],
            'verdict': verdict if role == 'review' else 'not_applicable',
            'findings': findings or [], 'complexity': complexity,
            'context_files': ['app/tasks.py','tests/test_tasks.py']}


class SimulatedInvoker:
    def __init__(self, fail_leader=True):
        """Initialize SimulatedInvoker state and its configured dependencies."""
        self.fail_leader = fail_leader
        self.calls = []

    def run(self, provider, role, context, workspace, folder, network, on_pid, cancelled):
        """Simulate one provider attempt, including optional leader failure and fixture changes."""
        self.calls.append((provider, role))
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'SIMULATED.txt').write_text('No model called.\n', encoding='utf-8')
        if self.fail_leader and provider == 'antigravity' and role == 'plan':
            return Result(error='SIMULATED quota exceeded; retry after 30 minutes')
        if role == 'implement':
            (Path(workspace) / 'app/tasks.py').write_text(DEMO_CODE, encoding='utf-8')
            (Path(workspace) / 'tests/test_filter.py').write_text(DEMO_TEST, encoding='utf-8')
        return Result(report=report(role), usage={'source': 'simulation', 'actual_model_tokens': 0})


def setup_fixture(folder):
    """Create a disposable synthetic Git project and independent Hub state."""
    folder = Path(folder)
    source = folder / 'source'
    write_demo(source)
    git(source, 'init')
    git(source, 'add', '.')
    git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', 'commit', '-m', 'Baseline')
    hub = Hub(folder / 'state')
    config = defaults()
    config['retention']['archive_completed_worktrees'] = False  # tests inspect worktrees; janitor has separate coverage
    for entry in config['providers'].values():
        entry['command'] = [sys.executable]  # Availability only; simulated invoker never runs these.
    hub.config = config
    project = hub.store.add_project('demo', source,
        [['{python}', '-m', 'unittest', 'discover', '-s', 'tests', '-v']], ['README.md','app','tests'])
    return hub, source, project


def simulate():
    """Run an offline workflow with fake providers and real Git/verifier behavior."""
    with tempfile.TemporaryDirectory(prefix='agenthub-offline-') as tmp:
        hub, source, project = setup_fixture(tmp)
        flow = hub.start('demo', 'Add status and search filters with tests', 'offline-demo', launch=False)
        invoker = SimulatedInvoker()
        engine = Engine(hub.store, hub.config, invoker)
        for _ in range(12):
            if not engine.tick(): break
            if hub.store.workflow(flow['id'])['status'] in {'completed','blocked','needs_review'}: break
        result = hub.status(flow['id'])
        return {'simulation': True, 'actual_model_calls': 0, 'status': result['status'],
                'leader': result['leader'], 'simulated_calls': invoker.calls,
                'leader_failover_observed': any(e['kind'] == 'leader_changed' for e in result['events']),
                'verification': result['verification'],
                'source_unchanged': (source / 'app/tasks.py').read_text(encoding='utf-8') != DEMO_CODE,
                'note': 'Real Python verification and git worktrees; model responses are simulated. Temporary files removed after this run.'}
