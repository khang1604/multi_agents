import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from agenthub.adapters import Result, validate_report, extract_report, build_command
from agenthub.api import Hub
from agenthub.config import ROOT
from agenthub.engine import Engine
from agenthub.platforms import FileLock, AlreadyRunning, resolve_command
from agenthub.policy import classify, failure, reset_time
from agenthub.simulation import SimulatedInvoker, setup_fixture, report, DEMO_CODE
from agenthub.workspace import git, fingerprint


class HubTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hub-test-')
        self.hub, self.source, self.project = setup_fixture(self.tmp.name)
        self.hub.config['security'] = {'isolated_test_environment': True, 'synthetic_data_only': True, 'isolation_description': 'Disposable synthetic unittest fixture; fake CLI only'}

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, objective='Add task filtering', **kwargs):
        return self.hub.start('demo', objective, 'request', launch=False, **kwargs)

    def drive(self, invoker=None, turns=12):
        engine = Engine(self.hub.store, self.hub.config, invoker or SimulatedInvoker(False))
        for _ in range(turns):
            if not engine.tick(): break
        return engine

    def test_auto_routing(self):
        self.assertEqual(classify('Fix a spelling typo in README'), 'small')
        self.assertEqual(classify('Add status filtering'), 'standard')
        self.assertEqual(classify('Add login authentication'), 'complex')
        self.assertEqual(classify('Sửa phân quyền đăng nhập'), 'complex')

    def test_deduplication_and_different_request_rejected(self):
        one = self.create()
        two = self.create()
        self.assertEqual(one['id'], two['id'])
        with self.assertRaises(ValueError): self.create('Different objective')
        with self.assertRaises(ValueError): self.hub.start('demo', 'Another task', 'second', launch=False)

    def test_full_workflow_and_leader_failover(self):
        flow = self.create()
        invoker = SimulatedInvoker(True)
        self.drive(invoker)
        result = self.hub.status(flow['id'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['leader'], 'claude')
        self.assertEqual(len(invoker.calls), 4)
        self.assertTrue(any(e['kind'] == 'leader_changed' for e in result['events']))
        self.assertTrue(all(c['exit_code'] == 0 for c in result['verification']['checks']))
        self.assertNotEqual((self.source / 'app/tasks.py').read_text(), DEMO_CODE)
        self.assertEqual((Path(result['workspace']) / 'app/tasks.py').read_text(), DEMO_CODE)

    def test_small_task_skips_planning_and_review(self):
        flow = self.create('Fix typo in README')
        invoker = SimulatedInvoker(False)
        self.drive(invoker)
        self.assertEqual(self.hub.status(flow['id'])['status'], 'completed')
        self.assertEqual(invoker.calls, [('codex', 'implement')])

    def test_context_restores_from_database(self):
        flow = self.create()
        self.hub.store.remember(self.project['id'], 'decision', 'Use standard library')
        fresh = Hub(self.hub.store.home)
        recovered = fresh.recover('demo')
        self.assertEqual(recovered['workflows'][0]['id'], flow['id'])
        self.assertEqual(recovered['memories'][0]['content'], 'Use standard library')

    def test_all_leaders_quota_wait_without_calling(self):
        flow = self.create()
        for name in self.hub.config['providers']:
            self.hub.store.health(name, time.time() + 900, 'quota: simulated')
        invoker = SimulatedInvoker()
        self.drive(invoker, 3)
        state = self.hub.status(flow['id'])
        self.assertEqual(state['status'], 'waiting')
        self.assertEqual(state['calls'], 0)
        self.assertEqual(invoker.calls, [])

    def test_missing_all_providers_blocks_honestly(self):
        flow = self.create()
        for entry in self.hub.config['providers'].values(): entry['command'] = ['missing-agent-binary-1234']
        self.drive()
        self.assertEqual(self.hub.status(flow['id'])['status'], 'blocked')

    def test_call_budget_is_hard_limit(self):
        flow = self.create(max_calls=1)
        invoker = SimulatedInvoker(False)
        self.drive(invoker)
        result = self.hub.status(flow['id'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(len(invoker.calls), 1)
        self.assertIn('budget', result['error'])

    def test_explicit_extra_budget_required(self):
        flow = self.create(max_calls=1)
        self.drive()
        with self.assertRaises(ValueError): self.hub.retry(flow['id'], launch=False)
        self.hub.retry(flow['id'], extra_calls=3, launch=False)
        self.drive()
        self.assertEqual(self.hub.status(flow['id'])['status'], 'completed')

    def test_cancel_fences_late_result(self):
        flow = self.create()
        hub = self.hub
        class CancelInvoker(SimulatedInvoker):
            def run(self, *args, **kwargs):
                hub.store.cancel(flow['id'])
                return Result(report=report('plan'))
        self.drive(CancelInvoker())
        result = self.hub.status(flow['id'])
        self.assertEqual(result['status'], 'cancelled')
        self.assertTrue(any(e['kind'] == 'late_result_ignored' for e in result['events']))

    def test_unsafe_old_process_prevents_failover(self):
        flow = self.create()
        class Unsafe(SimulatedInvoker):
            def run(self, *args, **kwargs): return Result(error='timeout', unsafe_to_continue=True)
        self.drive(Unsafe())
        result = self.hub.status(flow['id'])
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['calls'], 1)
        self.assertIn('no failover', result['error'])

    def test_readonly_role_mutation_is_detected(self):
        flow = self.create()
        class Mutating(SimulatedInvoker):
            def run(self, provider, role, context, workspace, *args):
                (Path(workspace) / 'app/tasks.py').write_text('bad mutation')
                return Result(report=report(role))
        self.drive(Mutating(), 1)
        result = self.hub.status(flow['id'])
        self.assertNotEqual(result['status'], 'completed')
        self.assertIn('Read-only role', result['error'])

    def test_prepared_plan_saves_planner_call(self):
        plan = {'summary':'Implement filtering', 'steps':['Edit function','Add tests'], 'acceptance':['Tests pass'], 'complexity':'standard'}
        flow = self.create(prepared_plan=plan)
        invoker = SimulatedInvoker(False)
        self.drive(invoker)
        self.assertEqual(self.hub.status(flow['id'])['status'], 'completed')
        self.assertNotIn('plan', [role for _, role in invoker.calls])
        self.assertEqual(len(invoker.calls), 2)

    def test_complex_requires_two_distinct_reviews(self):
        flow = self.create('Add secure authentication')
        self.drive()
        result = self.hub.status(flow['id'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len({r['provider'] for r in result['review']['reviews']}), 2)

    def test_dirty_project_is_not_silently_copied(self):
        flow = self.create()
        (self.source / 'README.md').write_text('local changes')
        self.drive()
        result = self.hub.status(flow['id'])
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('uncommitted', result['error'])

    def test_crash_recovery_does_not_duplicate_live_process(self):
        flow = self.create()
        self.hub.store.update(flow['id'], status='running')
        with self.hub.store.connection() as db:
            db.execute('INSERT INTO attempts(id,workflow_id,provider,phase,generation,status,pid,artifact,created) VALUES(?,?,?,?,?,?,?,?,?)',
                       ('a',flow['id'],'codex','plan',0,'running',os.getpid(),'test',time.time()))
        engine = Engine(self.hub.store, self.hub.config, SimulatedInvoker(False))
        engine.recover()
        self.assertEqual(self.hub.status(flow['id'])['status'], 'recovering')
        with self.hub.store.connection() as db: db.execute('UPDATE attempts SET pid=NULL')
        engine.recover()
        self.assertEqual(self.hub.status(flow['id'])['status'], 'queued')

    def test_result_schema_does_not_accept_blocked_as_success(self):
        bad = report('plan'); bad['outcome'] = 'blocked'; bad['summary'] = 'quota exceeded'
        with self.assertRaises(ValueError): validate_report(bad)
        with self.assertRaises(ValueError): extract_report('Everything is done!')
        parsed, usage = extract_report(json.dumps({'structured_output': report('plan'), 'usage': {'input_tokens': 12}}))
        self.assertEqual(parsed['outcome'], 'completed')
        self.assertEqual(usage['input_tokens'], 12)

    def test_failure_classification_and_unambiguous_reset(self):
        self.assertEqual(failure('bwrap: loopback: Operation not permitted'), 'permissions')
        self.assertEqual(failure('quota exceeded'), 'quota')
        self.assertEqual(failure('503 overloaded'), 'temporary')
        self.assertEqual(reset_time('retry after 2 minutes', 100), 220)
        self.assertEqual(reset_time('resetsAt: 1792415000', 1792410000), 1792415000)
        self.assertIsNone(reset_time('resets at 3pm', 100))

    def test_single_daemon_lock(self):
        path = self.hub.store.home / 'daemon.lock'
        with FileLock(path):
            with self.assertRaises(AlreadyRunning):
                with FileLock(path): pass

    def test_mcp_protocol(self):
        requests = [{'jsonrpc':'2.0','id':1,'method':'initialize'},
                    {'jsonrpc':'2.0','method':'notifications/initialized'},
                    {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                    {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'projects_list','arguments':{}}}]
        result = subprocess.run([sys.executable,str(ROOT/'hub.py'),'--home',str(self.hub.store.home),'mcp'],
                                input=''.join(json.dumps(r)+'\n' for r in requests), capture_output=True, encoding='utf-8', timeout=10)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies), 3)
        self.assertGreaterEqual(len(replies[1]['result']['tools']), 7)
        self.assertIn('dispatch_task', {t['name'] for t in replies[1]['result']['tools']})
        self.assertIn('demo', replies[2]['result']['content'][0]['text'])

    def test_no_shell_string_commands(self):
        with self.assertRaises(ValueError): resolve_command('python -c print(1)')
        with self.assertRaises(ValueError): self.hub.store.add_project('bad',self.source,['python test.py'],[])

    def test_provider_arguments_preserve_metacharacters(self):
        folder = Path(self.tmp.name) / 'artifacts'; folder.mkdir()
        task = 'Review "file" with & % ! | Unicode tiếng Việt'
        entry = {'command':[sys.executable]}
        for name in ['claude','copilot','antigravity','codex']:
            command, stdin, file = build_command(name, entry, 'plan', task, folder, False)
            self.assertIsInstance(command, list)
            self.assertTrue(task == stdin or task in command)

    def test_real_subprocess_adapter_uses_structured_result(self):
        from agenthub.adapters import Invoker
        script = Path(self.tmp.name) / 'fake_cli.py'
        script.write_text('import sys,json\nfrom pathlib import Path\n'
                          'prompt=sys.stdin.read()\n'
                          'Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text('+repr(json.dumps(report('plan')))+',encoding="utf-8")\n'
                          'print(json.dumps({"usage":{"input_tokens":7}}))\n', encoding='utf-8')
        self.hub.config['providers']['codex']['command'] = [sys.executable, str(script)]
        result = Invoker(self.hub.config).run('codex','plan','quoted " & % tiếng Việt', str(self.source),
            Path(self.tmp.name)/'attempt', False, lambda _: None, lambda: False)
        self.assertIsNotNone(result.report)
        self.assertEqual(result.usage['input_tokens'], 7)

    def test_timeout_even_when_child_does_not_read_large_stdin(self):
        from agenthub.adapters import Invoker
        script = Path(self.tmp.name) / 'hang_cli.py'
        script.write_text('import time\ntime.sleep(60)\n', encoding='utf-8')
        self.hub.config['providers']['codex']['command'] = [sys.executable, str(script)]
        self.hub.config['agent_timeout_seconds'] = 0.1
        started = time.monotonic()
        result = Invoker(self.hub.config).run('codex','plan','x'*300000, str(self.source),
            Path(self.tmp.name)/'hang', False, lambda _: None, lambda: False)
        self.assertLess(time.monotonic()-started, 15)
        self.assertIn('timed out', result.error)
        self.assertFalse(result.unsafe_to_continue)

    def test_test_failure_repairs_before_spending_review_quota(self):
        flow = self.create()
        class RepairInvoker(SimulatedInvoker):
            def __init__(self): super().__init__(False); self.workers = 0
            def run(self, provider, role, context, workspace, folder, network, on_pid, cancelled):
                if role == 'implement':
                    self.workers += 1
                    if self.workers == 1:
                        self.calls.append((provider,role))
                        (Path(workspace)/'app/tasks.py').write_text('raise RuntimeError("broken")',encoding='utf-8')
                        return Result(report=report(role))
                return super().run(provider,role,context,workspace,folder,network,on_pid,cancelled)
        invoker = RepairInvoker()
        self.drive(invoker)
        result = self.hub.status(flow['id'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual([role for _,role in invoker.calls], ['plan','implement','implement','review'])

    def test_context_fingerprint_keeps_source_repository_untouched(self):
        before = fingerprint(self.source)
        self.create(); self.drive()
        self.assertEqual(fingerprint(self.source), before)
        self.assertEqual(git(self.source,'status','--porcelain'), '')

    def test_live_pid_prevents_manual_retry(self):
        flow = self.create()
        self.hub.store.update(flow['id'],status='blocked')
        with self.hub.store.connection() as db:
            db.execute('INSERT INTO attempts(id,workflow_id,provider,phase,generation,status,pid,artifact,created) VALUES(?,?,?,?,?,?,?,?,?)',
                       ('a',flow['id'],'codex','plan',0,'failed',os.getpid(),'test',time.time()))
        with self.assertRaises(ValueError): self.hub.retry(flow['id'],launch=False)

    def test_changes_after_verification_force_recheck_without_model_call(self):
        flow = self.create()
        invoker = SimulatedInvoker(False)
        engine = Engine(self.hub.store,self.hub.config,invoker)
        for _ in range(3): engine.tick()
        state = self.hub.store.workflow(flow['id'])
        self.assertEqual(state['phase'],'review')
        (Path(state['workspace'])/'README.md').write_text('updated after verify',encoding='utf-8')
        calls = len(invoker.calls)
        engine.tick()
        self.assertEqual(self.hub.store.workflow(flow['id'])['phase'],'verify')
        self.assertEqual(len(invoker.calls),calls)

    def test_handoff_selects_only_relevant_files_and_reuses_analysis(self):
        from agenthub.workspace import build_pack
        (self.source/'app/unrelated.py').write_text('UNRELATED_LARGE_CODE = 123\n',encoding='utf-8')
        git(self.source,'add','.'); git(self.source,'-c','user.name=Test','-c','user.email=test@localhost','commit','-m','Extra file')
        handoff = {'summary':'The task list function is the only implementation target',
                   'files':[{'path':'app/tasks.py','start':1,'end':20,'note':'Preserve input order'}],
                   'decisions':['No dependency installation']}
        flow = self.create(handoff=handoff)
        engine=Engine(self.hub.store,self.hub.config,SimulatedInvoker(False)); engine.tick()
        state=self.hub.store.workflow(flow['id'])
        pack=build_pack(self.hub.store,state,self.project,'implement',40000)
        self.assertIn('only implementation target',pack['text'])
        self.assertNotIn('UNRELATED_LARGE_CODE',pack['text'])
        self.assertNotIn('app/unrelated.py',[item['path'] for item in pack['files']])
        self.assertTrue(any(item['cache_hit'] for item in pack['files']))

    def test_context_cache_invalidation_is_per_file(self):
        from agenthub.workspace import cached_file
        target=self.source/'app/tasks.py'
        one=cached_file(self.hub.store,target)
        two=cached_file(self.hub.store,target)
        self.assertEqual(one['sha256'],two['sha256']); self.assertTrue(two['cache_hit'])
        target.write_text('changed function\n',encoding='utf-8')
        three=cached_file(self.hub.store,target)
        self.assertNotEqual(one['sha256'],three['sha256'])
        self.assertFalse(three['cache_hit'])

    def test_review_context_has_diff_not_full_source(self):
        from agenthub.workspace import build_pack
        flow=self.create(); Engine(self.hub.store,self.hub.config,SimulatedInvoker(False)).tick()
        state=self.hub.store.workflow(flow['id'])
        pack=build_pack(self.hub.store,state,self.project,'review',40000)
        self.assertEqual(pack['files'],[])
        self.assertNotIn('def list_tasks',pack['text'])
        self.assertEqual(pack['strategy'],'diff-and-verification-only')

    def test_handoff_rejects_outside_paths(self):
        for path in ['../../secret','C:\\secret','/etc/passwd']:
            with self.assertRaises(ValueError): self.create(handoff={'files':[{'path':path}]})

    def test_completed_cleanup_exports_code_before_removing_worktree(self):
        from agenthub.retention import sweep
        import zipfile
        flow=self.create(); self.drive()
        state=self.hub.store.workflow(flow['id']); worktree=Path(state['workspace'])
        self.assertTrue(worktree.exists())
        code_path = worktree / 'app/tasks.py'
        self.assertEqual(code_path.read_text(encoding='utf-8'), DEMO_CODE)
        expected_code = code_path.read_bytes()
        self.hub.config['retention']['archive_completed_worktrees']=True
        result=sweep(self.hub.store,self.hub.config)
        after=self.hub.status(flow['id'])
        self.assertTrue(after['workspace_retired'])
        self.assertFalse(worktree.exists())
        self.assertTrue(Path(after['delivery']).is_file())
        with zipfile.ZipFile(after['delivery']) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read('files/app/tasks.py'), expected_code)
            self.assertIn('files/tests/test_filter.py',archive.namelist())
            self.assertIn('manifest.json',archive.namelist())
        self.assertNotEqual((self.source/'app/tasks.py').read_text(),DEMO_CODE)
        self.assertTrue((self.hub.store.home/'runs'/flow['id']/'CLEANED.json').exists())

    def test_cleanup_never_discards_changed_after_review_code(self):
        from agenthub.retention import sweep
        flow=self.create(); self.drive()
        state=self.hub.store.workflow(flow['id']); path=Path(state['workspace'])
        (path/'app/tasks.py').write_text('manual user change',encoding='utf-8')
        self.hub.config['retention']['archive_completed_worktrees']=True
        result=sweep(self.hub.store,self.hub.config)
        self.assertTrue(path.exists())
        self.assertTrue(result['retained'])
        self.assertIsNone(self.hub.store.workflow(flow['id'])['delivery'])

    def test_cleanup_preserves_active_and_quota_waiting(self):
        from agenthub.retention import sweep
        flow=self.create(); self.hub.store.update(flow['id'],status='waiting',next_run=time.time()+900)
        folder=self.hub.store.home/'runs'/flow['id']; folder.mkdir(parents=True)
        (folder/'checkpoint.txt').write_text('keep me')
        sweep(self.hub.store,self.hub.config)
        self.assertTrue((folder/'checkpoint.txt').exists())

    def test_cache_size_limit_evicts_only_recomputable_cache(self):
        from agenthub.retention import sweep
        from agenthub.workspace import cached_file
        cached_file(self.hub.store,self.source/'app/tasks.py')
        self.hub.config['retention']['cache_max_bytes']=0
        sweep(self.hub.store,self.hub.config)
        self.assertEqual(self.hub.store.all('SELECT * FROM file_cache'),[])
        self.assertTrue((self.source/'app/tasks.py').exists())

    def test_daemon_detaches_runs_offline_job_and_archives_delivery(self):
        from agenthub.service import stop_daemon, daemon_status
        from agenthub.platforms import pid_alive
        script=Path(self.tmp.name)/'offline_worker.py'
        script.write_text('import sys\nfrom pathlib import Path\n'
                          'if "sandbox" in sys.argv:\n    print("HUB_SANDBOX_OK"); sys.exit(0)\n'
                          'sys.stdin.read()\n'
                          'p=Path("README.md"); p.write_text(p.read_text()+"\\nOffline worker verified.\\n")\n'
                          'Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text('+repr(json.dumps(report('implement')))+',encoding="utf-8")\n',encoding='utf-8')
        config=self.hub.config
        for name,entry in config['providers'].items():
            entry['enabled']=name=='codex'
        config['providers']['codex']['command']=[sys.executable,str(script)]
        config['retention']['archive_completed_worktrees']=True
        config['poll_seconds']=0.2
        (self.hub.store.home/'config.json').write_text(json.dumps(config),encoding='utf-8')
        try:
            flow=self.hub.start('demo','Fix a typo in README','daemon-detach-test',launch=True)
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                state=self.hub.status(flow['id'])
                if state['status']=='completed' and state.get('delivery'): break
                if state['status'] in {'blocked','needs_review'}: self.fail(state['error'])
                time.sleep(0.1)
            else: self.fail('Detached daemon did not finish')
            self.assertTrue(Path(state['delivery']).exists())
            self.assertEqual(state['calls'],1)
        finally:
            stop_daemon(self.hub.store.home)
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                pid_file=self.hub.store.home/'daemon.pid'
                pid=int(pid_file.read_text()) if pid_file.exists() else None
                if daemon_status(self.hub.store.home)=='stopped' and not pid_alive(pid): break
                time.sleep(0.1)


class SecurityTests(unittest.TestCase):
    def test_default_blocks_until_synthetic_data_confirmed(self):
        from agenthub.security import preflight
        from agenthub.config import defaults
        with self.assertRaisesRegex(ValueError, 'SECURITY BLOCKED'):
            preflight(defaults())
        with self.assertRaises(ValueError):
            preflight({'security': {'isolated_test_environment': True}})

    def test_synthetic_environment_without_requested_isolation(self):
        from agenthub.security import preflight
        from agenthub.config import defaults
        config = defaults()
        config['security']['synthetic_data_only'] = True
        preflight(config)
        self.assertFalse(config['security']['isolated_test_environment'])
        self.assertEqual(config['security']['isolation_description'], '')

    def test_requested_isolation_requires_operator_attestation(self):
        from agenthub.security import preflight
        scope = {'require_isolation': True, 'synthetic_data_only': True}
        with self.assertRaisesRegex(ValueError, 'requested isolation'):
            preflight({'security': scope})
        scope['isolated_test_environment'] = True
        for description in ('', '   ', None, True):
            scope['isolation_description'] = description
            with self.subTest(description=description), self.assertRaises(ValueError):
                preflight({'security': scope})
        scope['isolation_description'] = 'Operator-confirmed test VM'
        preflight({'security': scope})

    def test_legacy_configuration_keeps_isolation_requirement(self):
        from agenthub.security import preflight
        with self.assertRaisesRegex(ValueError, 'requested isolation'):
            preflight({'security': {'synthetic_data_only': True}})

    def test_policy_boolean_types_do_not_bypass_security(self):
        from agenthub.security import preflight
        for value in ('false', 'true', 0, 1, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                preflight({'security': {'require_isolation': value, 'synthetic_data_only': True}})
        with self.assertRaises(ValueError):
            preflight({'security': {'require_isolation': False, 'synthetic_data_only': 'true'}})

    def test_unrestricted_network_blocked_without_isolation_requirement(self):
        from agenthub.security import preflight
        config = {'security': {'require_isolation': False, 'synthetic_data_only': True}}
        with self.assertRaisesRegex(ValueError, 'network'):
            preflight(config, True)

    def test_unrestricted_network_blocks_even_with_attestation(self):
        from agenthub.security import preflight
        config = {'security': {'isolated_test_environment': True, 'synthetic_data_only': True, 'isolation_description': 'test'}}
        preflight(config)
        with self.assertRaisesRegex(ValueError, 'network'):
            preflight(config, True)
