import copy
import contextlib
import io
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agenthub.adapters import Invoker, Result, TaskBlocked, context_capacity, prompt_prefix, validate_report
from agenthub.engine import Engine
from agenthub.handoff import allow_approach, guard, validate_delta
from agenthub.simulation import setup_fixture, report, SimulatedInvoker
from agenthub.workspace import build_pack, fingerprint


def delta(next_id='inspect-session'):
    return {'intent': {'rationale': 'Prevent expired sessions from being accepted'},
            'progress': {'completed': ['Located session validation'], 'in_progress': ['Fix expiry'],
                         'unknowns': ['UI behavior unverified']},
            'attempts': [{'approach_id': 'clear-cache', 'status': 'rejected',
                          'reason': 'Reproduced without cached entries', 'evidence_refs': [],
                          'revisit_if': 'New evidence shows cached credentials involved'}],
            'decisions': [{'decision': 'Preserve public API', 'reason': 'Callers depend on it'}],
            'next_action': {'action': 'Inspect expiry check', 'approach_id': next_id,
                            'role': 'implement', 'files': ['app/tasks.py'], 'stop_conditions': ['Scope unclear']}}


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='handoff-synthetic-')
        self.hub, self.source, self.project = setup_fixture(self.tmp.name)
        self.flow = self.hub.start('demo', 'Add task filtering', 'handoff-test', launch=False)

    def tearDown(self):
        self.tmp.cleanup()

    def engine(self, invoker):
        return Engine(self.hub.store, self.hub.config, invoker)

    def first_report(self, value=None, blocked=False):
        response = report('plan')
        response['handoff'] = value or delta()
        class Planner:
            def run(inner, *args):
                if blocked:
                    return Result(error='Need operator input', failure_category='task_blocked', checkpoint_report=response)
                return Result(report=response)
        self.engine(Planner()).tick()
        return self.hub.store.workflow(self.flow['id'])

    def test_provider_switch_receives_complete_handoff_and_observed_evidence(self):
        flow = self.first_report()
        state = json.loads(flow['handoff'])['checkpoint']
        self.assertEqual(state['revision'], 1)
        self.assertTrue(state['claims_are_unverified'])
        contexts = []
        delegate = SimulatedInvoker(False)
        class Worker:
            def run(inner, provider, role, context, *args):
                contexts.append((provider, context))
                return delegate.run(provider, role, context, *args)
        engine = self.engine(Worker())
        engine.tick()
        self.assertEqual(contexts[0][0], 'codex')
        self.assertEqual(self.hub.brief(self.flow['id'])['current_agent'], None)  # Next phase is local verification.
        for text in ['clear-cache', 'Reproduced without cached entries', 'inspect-session',
                     'Preserve public API', 'HUB OBSERVED EVIDENCE', 'OPERATOR SCOPE']:
            self.assertIn(text, contexts[0][1])
        engine.tick()  # Independent local verification, not model claims.
        flow = self.hub.store.workflow(self.flow['id'])
        self.assertEqual(json.loads(flow['handoff'])['checkpoint']['intent']['acceptance'], report('implement')['acceptance'])
        pack = build_pack(self.hub.store, flow, self.project, 'review', 14000)
        self.assertIn('"exit_code": 0', pack['text'])
        self.assertEqual(len(self.hub.store.all("SELECT * FROM events WHERE kind='handoff_checkpoint'")), 3)

    def test_rejected_next_action_blocks_without_spending_another_call(self):
        self.first_report(delta('clear-cache'))
        invoker = SimulatedInvoker(False)
        self.engine(invoker).tick()
        flow = self.hub.store.workflow(self.flow['id'])
        self.assertEqual(flow['status'], 'blocked')
        self.assertEqual(flow['calls'], 1)
        self.assertEqual(invoker.calls, [])
        self.assertIn('rejected approach', flow['error'])

    def test_budget_never_slices_required_handoff_or_charges_call(self):
        self.first_report()
        self.hub.config['max_context_chars'] = 100
        self.engine(SimulatedInvoker(False)).tick()
        flow = self.hub.store.workflow(self.flow['id'])
        self.assertEqual(flow['calls'], 1)
        self.assertEqual(flow['status'], 'blocked')
        self.assertIn('complete handoff', flow['error'])

    def test_truncation_preserves_complete_checkpoint(self):
        flow = self.first_report()
        self.hub.store.remember(self.project['id'], 'huge', 'x' * 20000)
        pack = build_pack(self.hub.store, flow, self.project, 'implement', 5000)
        self.assertTrue(pack['truncated'])
        self.assertLessEqual(len(pack['text']), 5000)
        required = {key: value for key, value in json.loads(flow['handoff'])['checkpoint'].items() if key != 'hub_observation'}
        for key in ('intent', 'progress', 'attempts', 'decisions', 'next_action'):
            self.assertIn(json.dumps(required[key], ensure_ascii=False), pack['text'])
        self.assertIn('context_omissions', pack['text'])

    def test_review_keeps_entire_diff_ahead_of_old_plan_and_memory(self):
        flow = self.first_report()
        root = Path(flow['workspace'])
        (root / 'app/tasks.py').write_text('# Synthetic patch\n' + 'def added(): return 1\n', encoding='utf-8')
        self.hub.store.remember(self.project['id'], 'huge', 'x' * 20000)
        flow['plan'] = json.dumps({'summary': 'x' * 20000})
        from agenthub.workspace import diff
        patch_text = diff(root)
        pack = build_pack(self.hub.store, flow, self.project, 'review', 5000)
        self.assertIn(patch_text, pack['text'])
        self.assertLess(pack['text'].index('CURRENT DIFF:'), pack['text'].index('MEMORY:'))
        (root / 'app/tasks.py').write_text('print("synthetic")\n' * 1000, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'handoff/diff'):
            build_pack(self.hub.store, flow, self.project, 'review', 5000)

    def test_failure_keeps_ledger_with_explicit_unknowns(self):
        self.first_report()
        class Failed:
            def run(inner, *args):
                return Result(error='quota exceeded')
        self.engine(Failed()).tick()
        state = json.loads(self.hub.store.workflow(self.flow['id'])['handoff'])['checkpoint']
        self.assertEqual(state['attempts'][0]['status'], 'rejected')
        self.assertTrue(any('unknown' in item for item in state['progress']['unknowns']))

    def test_blocked_report_retains_handoff_without_marking_provider_bad(self):
        flow = self.first_report(blocked=True)
        self.assertEqual(flow['status'], 'blocked')
        self.assertIn('clear-cache', flow['handoff'])
        self.assertEqual(self.hub.store.all('SELECT * FROM health'), [])
        self.assertFalse(any('interrupted' in item for item in json.loads(flow['handoff'])['checkpoint']['progress']['unknowns']))

    def test_temporarily_blocked_approach_is_not_treated_as_disproven(self):
        value = delta('clear-cache')
        value['attempts'][0]['status'] = 'blocked'
        flow = self.first_report(value)
        guard(json.loads(flow['handoff']), fingerprint(flow['workspace']), 'implement')

    def test_late_report_cannot_overwrite_cancelled_checkpoint(self):
        self.first_report()
        previous = self.hub.store.workflow(self.flow['id'])['handoff']
        store = self.hub.store
        class Late:
            def run(inner, *args):
                store.update(self.flow['id'], status='cancelled', generation=99)
                response = report('implement')
                response['handoff'] = delta('late-action')
                return Result(report=response)
        self.engine(Late()).tick()
        self.assertEqual(store.workflow(self.flow['id'])['handoff'], previous)

    def test_recovery_keeps_checkpoint_and_marks_unreported_work_unknown(self):
        flow = self.first_report()
        engine = self.engine(SimulatedInvoker(False))
        self.hub.store.update(flow['id'], status='running')
        engine._attempt(flow, 'codex', 'implement', Path(self.tmp.name) / 'attempt')
        engine.recover()
        recovered = self.hub.store.workflow(flow['id'])
        self.assertEqual(recovered['generation'], flow['generation'] + 1)
        state = json.loads(recovered['handoff'])['checkpoint']
        self.assertIn('clear-cache', recovered['handoff'])
        self.assertIn('Interrupted process', state['last_observation']['error'])

    def test_crash_after_saved_report_advances_without_calling_model_again(self):
        engine = self.engine(SimulatedInvoker(False))
        with patch.object(engine, '_apply_report', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                engine.tick()
        flow = self.hub.store.workflow(self.flow['id'])
        self.assertEqual(flow['status'], 'running')
        self.assertEqual(flow['calls'], 1)
        engine.recover()
        restored = self.hub.store.workflow(flow['id'])
        self.assertEqual(restored['phase'], 'implement')
        self.assertEqual(restored['calls'], 1)
        self.assertEqual(restored['status'], 'queued')
        self.assertEqual(json.loads(restored['handoff'])['checkpoint']['revision'], 1)

    def test_legacy_report_is_accepted_without_inventing_attempts(self):
        self.assertEqual(validate_report(report('plan')), report('plan'))
        self.engine(SimulatedInvoker(False)).tick()
        state = json.loads(self.hub.store.workflow(self.flow['id'])['handoff'])['checkpoint']
        self.assertEqual(state['attempts'], [])
        self.assertIn('Legacy report', state['progress']['unknowns'][0])

    def test_schema_rejects_forged_evidence_unsafe_paths_and_missing_reasons(self):
        for change in ('evidence', 'path', 'reason', 'duplicate'):
            value = delta()
            if change == 'evidence':
                value['verified'] = True
            elif change == 'path':
                value['next_action']['files'] = ['../private.txt']
            elif change == 'reason':
                value['attempts'][0]['reason'] = ''
            else:
                value['attempts'].append(copy.deepcopy(value['attempts'][0]))
            with self.assertRaises(ValueError):
                validate_delta(value)
        response = report('plan')
        response.update(outcome='blocked', handoff=delta())
        with self.assertRaises(TaskBlocked) as caught:
            validate_report(response)
        self.assertEqual(caught.exception.report['handoff'], delta())

    def test_rejection_cannot_be_erased_by_later_agent(self):
        self.first_report()
        response = report('implement')
        response['handoff'] = delta('clear-cache')
        response['handoff']['attempts'][0]['status'] = 'succeeded'
        class Contradictory:
            def run(inner, *args):
                return Result(report=response)
        self.engine(Contradictory()).tick()
        handoff = json.loads(self.hub.store.workflow(self.flow['id'])['handoff'])
        self.assertEqual(handoff['checkpoint']['attempts'][0]['status'], 'rejected')
        with self.assertRaises(ValueError):
            guard(handoff)

    def test_source_change_warns_that_handoff_analysis_is_stale(self):
        flow = self.first_report()
        (Path(flow['workspace']) / 'app/tasks.py').write_text('# Different synthetic source\n', encoding='utf-8')
        pack = build_pack(self.hub.store, flow, self.project, 'implement', 14000)
        self.assertIn('SOURCE CHANGED', pack['text'])
        self.assertIn('"handoff_source_changed": true', pack['text'])

    def test_argument_transport_reserves_space_for_rules_and_new_schema(self):
        for provider in ('copilot', 'antigravity'):
            for role in ('plan', 'review'):
                capacity = context_capacity(provider, role)
                self.assertGreater(capacity, 0)
                self.assertLessEqual(capacity + len(prompt_prefix(role)), 18000 if os.name == 'nt' else 60000)

    def test_cli_shows_three_lines_and_json_only_when_requested(self):
        from agenthub.cli import main
        self.first_report()
        args = ['--home', str(self.hub.store.home), 'handoff', self.flow['id']]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(args)
        self.assertEqual(len(out.getvalue().splitlines()), 3)
        self.assertNotIn('{', out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(args + ['--json'])
        self.assertEqual(json.loads(out.getvalue())['version'], 2)

    def test_fake_cli_roundtrip_preserves_v2_in_completed_and_blocked_reports(self):
        script = Path(self.tmp.name) / 'fake_cli.py'
        self.hub.config['security'] = {'synthetic_data_only': True, 'require_isolation': False}
        self.hub.config['providers']['codex']['command'] = [sys.executable, str(script)]
        for outcome in ('completed', 'blocked'):
            response = dict(report('plan'), outcome=outcome, handoff=delta())
            script.write_text('import sys\nfrom pathlib import Path\n'
                              'sys.stdin.read()\nPath(sys.argv[sys.argv.index("--output-last-message")+1]).write_text('
                              + repr(json.dumps(response)) + ',encoding="utf-8")\n', encoding='utf-8')
            result = Invoker(self.hub.config).run('codex', 'plan', 'Synthetic fixture only', str(self.source),
                        Path(self.tmp.name) / outcome, False, lambda _: None, lambda: False)
            saved = result.report if outcome == 'completed' else result.checkpoint_report
            self.assertIsNotNone(saved, result.error)
            self.assertEqual(saved['handoff'], delta())
            if outcome == 'blocked':
                self.assertEqual(result.failure_category, 'task_blocked')

    def test_operator_allowance_is_source_bound_consumed_and_worker_denied(self):
        self.first_report(delta('clear-cache'))
        engine = self.engine(SimulatedInvoker(False))
        engine.tick()
        with patch.dict('os.environ', {'MULTI_AGENTS_WORKER': '1'}):
            with self.assertRaises(ValueError):
                allow_approach(self.hub.store, self.flow['id'], 'clear-cache', 'New synthetic evidence')
        allow_approach(self.hub.store, self.flow['id'], 'clear-cache', 'Reviewed new synthetic evidence')
        flow = self.hub.store.workflow(self.flow['id'])
        handoff = json.loads(flow['handoff'])
        guard(handoff, fingerprint(flow['workspace'], self.hub.store))
        with self.assertRaises(ValueError):
            guard(handoff, 'changed-source')
        self.hub.retry(flow['id'], launch=False)
        engine.tick()
        state = self.hub.store.workflow(flow['id'])
        self.assertEqual(state['calls'], 2)
        self.assertNotIn('approach_allowance', json.loads(state['handoff']))
        self.assertEqual(json.loads(state['handoff'])['checkpoint']['attempts'][0]['status'], 'rejected')

    def test_worker_allowance_is_not_consumed_by_replanning(self):
        flow = self.first_report(delta('clear-cache'))
        self.hub.store.update(flow['id'], status='blocked', phase='plan')
        allow_approach(self.hub.store, flow['id'], 'clear-cache', 'Operator reviewed changed worker conditions')
        self.hub.retry(flow['id'], launch=False)
        delegate = SimulatedInvoker(False)
        class Replanned:
            def run(inner, provider, role, *args):
                if role == 'plan':
                    return Result(report=dict(report('plan'), handoff=delta('clear-cache')))
                return delegate.run(provider, role, *args)
        engine = self.engine(Replanned())
        engine.tick()
        saved = json.loads(self.hub.store.workflow(flow['id'])['handoff'])
        self.assertEqual(saved['approach_allowance']['revision'], saved['checkpoint']['revision'])
        self.assertEqual(saved['approach_allowance']['role'], 'implement')
        engine.tick()
        flow = self.hub.store.workflow(flow['id'])
        self.assertEqual(flow['phase'], 'verify')
        self.assertEqual(flow['calls'], 3)
        self.assertNotIn('approach_allowance', json.loads(flow['handoff']))
