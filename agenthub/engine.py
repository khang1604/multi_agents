import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from .adapters import Invoker, Result, read_tail
from .platforms import FileLock, AlreadyRunning, pid_alive, spawn, stop_tree, resolve_command
from .policy import choose, failure, reset_time
from .store import ACTIVE, encode
from . import workspace as ws
from .handoff import checkpoint, guard


class Engine:
    def __init__(self, store, config, invoker=None):
        """Initialize Engine state and its configured dependencies."""
        self.store, self.config = store, config
        self.invoker = invoker or Invoker(config)
        self.last_cleanup = time.time()

    def recover(self):
        """Recover interrupted work while checking process ownership and generation safety."""
        for flow in self.store.all("SELECT * FROM workflows WHERE status IN ('running','recovering')"):
            attempts = self.store.all("SELECT * FROM attempts WHERE workflow_id=? AND status IN ('running','orphan')", (flow['id'],))
            alive = [a for a in attempts if pid_alive(a['pid'])]
            if alive:
                self.store.update(flow['id'], status='recovering', error='Waiting for old process to exit; duplicate writers are forbidden')
                continue
            saved = self.store.one('SELECT * FROM attempts WHERE workflow_id=? AND generation=? AND status=\'completed\' ORDER BY ended DESC LIMIT 1', (flow['id'], flow['generation']))
            if not attempts and saved and saved['outcome']:
                report = json.loads(saved['outcome'])
                if saved['phase'] in {'plan', 'implement', 'review'} and report.get('outcome') == 'completed':
                    original = self.config
                    from .settings import effective_config
                    self.config = effective_config(original, self.store.home, flow['project_id'])
                    try:
                        observed = json.loads(flow['handoff']).get('checkpoint', {}).get('hub_observation', {})
                        current_hash = ws.fingerprint(flow['workspace'], self.store)
                        if saved['phase'] == 'review' and observed.get('fingerprint_after') != current_hash:
                            self.store.update(flow['id'], status='queued', phase='verify', review='{}', error='Source changed after saved review; rerun verification')
                        else:
                            self._apply_report(flow, self.store.project(flow['project_id']), saved['phase'], saved['provider'], report,
                                               observed.get('fingerprint_before', current_hash))
                        self.store.event(flow['id'], 'saved_report_recovered', {'attempt': saved['id'], 'ai_calls_consumed': 0})
                    finally:
                        self.config = original
                    continue
            with self.store.connection() as db:
                current = dict(db.execute('SELECT * FROM workflows WHERE id=?', (flow['id'],)).fetchone())
                for attempt in attempts:
                    checkpoint(db, current, attempt, error='Interrupted process; no final report')
                    current = dict(db.execute('SELECT * FROM workflows WHERE id=?', (flow['id'],)).fetchone())
                db.execute("UPDATE attempts SET status='interrupted',ended=? WHERE workflow_id=? AND status IN ('running','orphan')",
                           (time.time(), flow['id']))
            self.store.update(flow['id'], status='queued', generation=flow['generation'] + 1,
                              error='Recovered interrupted step; inspect checkpoint and continue')
            self.store.event(flow['id'], 'recovered', {'phase': flow['phase']})

    def tick(self):
        """Advance eligible saved work by one bounded orchestration step."""
        self.recover()
        flow = self.store.one("SELECT * FROM workflows WHERE status IN ('queued','waiting') AND next_run <= ? ORDER BY updated LIMIT 1", (time.time(),))
        if not flow:
            return False
        try:
            self.step(flow)
        except Exception as error:
            # Retain the phase/artifacts for explicit retry, never silently discard the task.
            self.store.update(flow['id'], status='blocked', error=str(error))
            self.store.event(flow['id'], 'blocked', {'reason': str(error)})
        current = self.store.workflow(flow['id'])
        if current['status'] == 'completed':
            from .acceptance import mode, accept
            if mode(self.store, current['project_id'])['auto_accept']:
                try:
                    from .retention import archive_completed
                    if not current.get('delivery'):
                        archive_completed(self.store, current, self.config['retention'])
                    accept(self.store, current['id'], automatic=True)
                except Exception as error:
                    self.store.event(current['id'], 'auto_accept_blocked', {'reason': str(error)})
        self.maybe_cleanup(force=current['status'] == 'completed')
        return True

    def maybe_cleanup(self, force=False):
        """Run due retention work without cleaning active workflows."""
        if not force and time.time()-self.last_cleanup < self.config['retention']['sweep_interval_seconds']:
            return
        from .retention import sweep
        try:
            sweep(self.store,self.config)
        except Exception as error:
            self.store.event(None,'cleanup_error',{'reason':str(error)})
        self.last_cleanup = time.time()

    def _attempt(self, flow, provider, phase, folder):
        """Reserve and prepare a provider attempt within the remaining call budget."""
        attempt_id = uuid.uuid4().hex[:12]
        with self.store.connection() as db:
            db.execute('''INSERT INTO attempts(id,workflow_id,provider,phase,generation,status,artifact,created)
                VALUES(?,?,?,?,?,?,?,?)''', (attempt_id, flow['id'], provider, phase,
                flow['generation'], 'running', str(folder), time.time()))
        return attempt_id

    def _pid(self, attempt_id, pid):
        """Persist the child process identity for crash-safe supervision."""
        with self.store.connection() as db:
            db.execute('UPDATE attempts SET pid=? WHERE id=?', (pid, attempt_id))

    def _finish_attempt(self, attempt_id, result, observation=None):
        """Commit attempt results and handoff evidence with generation fencing."""
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            attempt = dict(db.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone())
            flow = dict(db.execute('SELECT * FROM workflows WHERE id=?', (attempt['workflow_id'],)).fetchone())
            checkpoint(db, flow, attempt, result.report or result.checkpoint_report, result.error, observation)
            db.execute('UPDATE attempts SET status=?,ended=?,outcome=?,error=?,usage=? WHERE id=?',
                       ('completed' if result.report else 'failed', time.time(),
                        encode(result.report or result.checkpoint_report) if result.report or result.checkpoint_report else None, result.error[-6000:], encode(result.usage), attempt_id))
        if result.report and result.report.get('outcome') == 'completed':
            attempt = self.store.one('SELECT provider FROM attempts WHERE id=?', (attempt_id,))
            if attempt and attempt['provider'] in self.config['providers']:
                from .registry import record_live_success
                record_live_success(self.store.home, attempt['provider'], self.config['providers'][attempt['provider']])

    def _cancelled(self, workflow_id, generation):
        """Check whether cancellation or a newer generation invalidates the current attempt."""
        row = self.store.workflow(workflow_id)
        return (row['status'] == 'cancelled' or row['generation'] != generation or
                (self.store.home / 'stop').exists())

    def _fallback_priority(self, flow):
        """Return fallback provider candidates ordered by active workflow leader and configured priorities."""
        previous = [r['provider'] for r in self.store.all(
            "SELECT provider FROM attempts WHERE workflow_id=? AND status='completed' ORDER BY created DESC",
            (flow['id'],))]
        candidates = (([flow['leader']] if flow.get('leader') else []) + previous +
                      self.config['leader_priority'] + self.config['worker_priority'] +
                      list(self.config['providers']))
        return list(dict.fromkeys(candidates))

    def _choose_provider(self, flow, role, priority, excluded):
        """Select a provider for a role, falling back to the active CLI when no dedicated provider is available."""
        prior_failed = []
        if role == 'implement':
            failed_counts = {}
            for row in self.store.all(
                    "SELECT provider FROM attempts WHERE workflow_id=? AND phase='implement' AND status='failed'",
                    (flow['id'],)):
                failed_counts[row['provider']] = failed_counts.get(row['provider'], 0) + 1
            model_fallbacks = {
                json.loads(e['data'])['provider']
                for e in self.store.all(
                    "SELECT data FROM events WHERE workflow_id=? AND kind='model_fallback_selected'",
                    (flow['id'],))
            }
            prior_failed = [
                p for p, count in failed_counts.items()
                if p not in excluded and (p not in model_fallbacks or count > 1)
            ]
        preferred_excluded = list(excluded) + prior_failed
        provider = choose(self.config, self.store, role, priority, excluded=preferred_excluded)
        if provider:
            return provider, False
        if role in {'implement', 'plan'} or (role == 'review' and not excluded):
            fallback = choose(self.config, self.store, role, self._fallback_priority(flow),
                              excluded=preferred_excluded, allow_role_fallback=True)
            if fallback:
                return fallback, True
        if prior_failed:
            ordered = sorted(self._fallback_priority(flow), key=lambda p: failed_counts.get(p, 0))
            for candidate in ordered:
                if candidate in excluded:
                    continue
                if candidate in priority and choose(self.config, self.store, role, [candidate], excluded=excluded):
                    return candidate, False
                if role in {'implement', 'plan'} or (role == 'review' and not excluded):
                    if choose(self.config, self.store, role, [candidate], excluded=excluded, allow_role_fallback=True):
                        return candidate, True
        return None, False

    def _wait_or_block(self, flow, role, priority, excluded):
        """Persist a retry wait or blocker when no eligible provider can proceed."""
        installed = []
        candidates = self._fallback_priority(flow) if role == 'implement' else priority
        for provider in candidates:
            entry = self.config['providers'].get(provider, {})
            if provider in excluded or not entry.get('enabled'):
                continue
            if role != 'implement' and role not in entry.get('roles', []):
                continue
            try:
                from .registry import execution_command
                execution_command(provider, entry)
                installed.append(provider)
            except (OSError, ValueError):
                pass
        health = {h['provider']: h for h in self.store.all('SELECT * FROM health')}
        cooldowns = [health[p]['until'] for p in installed if p in health and
                     health[p]['reason'].startswith(('quota:', 'temporary:')) and health[p]['until'] > time.time()]
        if cooldowns:
            wake_at = min(cooldowns)
            self.store.update(flow['id'], status='waiting', next_run=min(cooldowns),
                              error='Available providers are cooling down; no AI calls before next_run')
            self.store.event(flow['id'], 'quota_wait_scheduled', {'not_before': wake_at, 'providers': installed})
        else:
            reason = 'No eligible CLI available for ' + role + '. Run doctor/configure providers.'
            if role == 'review' and excluded:
                self.store.update(flow['id'], status='needs_review', error=reason)
            else:
                self.store.update(flow['id'], status='blocked', error=reason)
        self.store.event(flow['id'], 'routing_unavailable', {'role': role, 'installed': installed})

    def step(self, flow):
        """Advance one workflow while recording failures and preserving its checkpoint."""
        from .settings import effective_config
        original = self.config
        self.config = effective_config(original, self.store.home, flow['project_id'])
        for event in self.store.all("SELECT data FROM events WHERE workflow_id=? AND kind='model_fallback_selected'", (flow['id'],)):
            name = json.loads(event['data'])['provider']
            entry = self.config['providers'].get(name, {})
            if entry.get('model_fallback') == 'INHERIT':
                entry['model_policy'] = 'INHERIT'
        if isinstance(self.invoker, Invoker):
            self.invoker.config = self.config
        try:
            self._step(flow)
        finally:
            self.config = original
            if isinstance(self.invoker, Invoker):
                self.invoker.config = original

    def _step(self, flow):
        """Execute the current workflow phase using configured providers and verification."""
        budget_start = flow['created']
        wake = self.store.one("SELECT id,data FROM events WHERE workflow_id=? AND kind IN ('resume_scheduled','quota_wait_scheduled') ORDER BY id DESC LIMIT 1", (flow['id'],))
        if wake:
            deadline = json.loads(wake['data'])['not_before']
            activation = self.store.one("SELECT data,created FROM events WHERE workflow_id=? AND kind='wake_activated' ORDER BY id DESC LIMIT 1", (flow['id'],))
            if activation and json.loads(activation['data']).get('schedule_id') == wake['id']:
                budget_start = max(budget_start, activation['created'])
            elif time.time() >= deadline:
                budget_start = time.time()
                self.store.event(flow['id'], 'wake_activated', {'schedule_id': wake['id']})
            else:
                return
        if time.time() - budget_start > self.config['max_workflow_age_hours'] * 3600:
            self.store.update(flow['id'], status='blocked', error='Workflow time budget exhausted; progress retained')
            return
        project = self.store.project(flow['project_id'])
        if not any(e.get('enabled') and ('implement' in e.get('roles', []) or 'plan' in e.get('roles', [])) for e in self.config['providers'].values()):
            raise ValueError('No coding agent enabled; enable Codex or Claude for implementation')
        if isinstance(self.invoker, Invoker):
            from .security import preflight
            preflight(self.config, bool(project.get('network', False)))
        path, base = ws.prepare(self.store, flow, project)
        self.store.update(flow['id'], workspace=path, base_commit=base)
        flow.update(workspace=path, base_commit=base)
        if flow['phase'] == 'review':
            verified = json.loads(flow['verification']).get('fingerprint_after')
            if verified != ws.fingerprint(path, self.store):
                self.store.update(flow['id'], status='queued', phase='verify', review='{}',
                                  error='Worktree changed since verification; rerun checks before review')
                self.store.event(flow['id'], 'verification_invalidated', {})
                return
        if flow['phase'] == 'verify':
            self.verify(flow, project)
            return
        if flow['calls'] >= flow['max_calls']:
            self.store.update(flow['id'], status='blocked', error='AI call budget exhausted; progress retained')
            return
        role = flow['phase']
        excluded = []
        if role == 'plan':
            priority = self.config['leader_priority']
        elif role == 'implement':
            priority = self.config['worker_priority']
        else:
            priority = list(dict.fromkeys(([flow['leader']] if flow['leader'] else []) + self.config['reviewer_priority']))
            reviews = json.loads(flow['review']).get('reviews', [])
            excluded = [r['provider'] for r in reviews]
            worker = self.store.one("SELECT provider FROM attempts WHERE workflow_id=? AND phase='implement' AND status='completed' ORDER BY created DESC LIMIT 1", (flow['id'],))
            # Prefer another model family, but don't manufacture independence if only one exists.
            if worker and not reviews:
                other = choose(self.config, self.store, role, priority, excluded=[worker['provider']])
                if other:
                    excluded.append(worker['provider'])
        provider, fallback_used = self._choose_provider(flow, role, priority, excluded)
        if not provider:
            self._wait_or_block(flow, role, priority, excluded)
            return
        if role == 'implement' and isinstance(self.invoker, Invoker):
            from .readiness import probe_worker
            while provider:
                try:
                    probe_worker(self.config, provider, path)
                    break
                except ValueError as error:
                    self.store.event(flow['id'], 'worker_environment_failed',
                                     {'provider': provider, 'ai_calls_consumed': 0})
                    excluded.append(provider)
                    next_provider, fallback_used = self._choose_provider(flow, role, priority, excluded)
                    if not next_provider:
                        self.store.update(flow['id'], flow['generation'], status='blocked', error=str(error))
                        return
                    provider = next_provider
        guard(json.loads(flow['handoff']), ws.fingerprint(path, self.store), role)
        from .adapters import context_capacity
        # A small-context reviewer must not block a verified delivery when a later
        # configured reviewer can receive the complete, required diff.  Packing is
        # local and read-only, so trying the next eligible provider consumes no AI
        # call and keeps the review evidence intact.
        context_error = None
        while provider:
            context_limit = min(self.config['max_context_chars'], 14000) if provider in {'antigravity','copilot'} else self.config['max_context_chars']
            context_limit = min(context_limit, context_capacity(provider, role))
            try:
                pack = ws.build_pack(self.store, flow, project, role, context_limit,
                                     security=self.config.get('security'))
                break
            except ValueError as error:
                if 'Context budget cannot fit' not in str(error):
                    raise
                context_error = str(error)
                excluded.append(provider)
                provider, fallback_used = self._choose_provider(flow, role, priority, excluded)
        if not provider:
            message = context_error or 'No eligible provider can receive the required context'
            self.store.update(flow['id'], status='needs_review' if role == 'review' else 'blocked', error=message)
            self.store.event(flow['id'], 'context_capacity_blocked', {'role': role, 'providers': excluded})
            return
        generation = flow['generation'] + 1
        old_leader = flow['leader']
        leader = provider if role in {'plan', 'review'} else old_leader
        if not self.store.update(flow['id'], flow['generation'], status='running', generation=generation, calls=flow['calls'] + 1,
                                 leader=leader, next_run=0):
            return
        flow.update(status='running', generation=generation, calls=flow['calls'] + 1, leader=leader)
        if role in {'plan', 'review'} and old_leader and old_leader != provider:
            self.store.event(flow['id'], 'leader_changed', {'from': old_leader, 'to': provider, 'generation': generation})
        if fallback_used:
            self.store.event(flow['id'], 'worker_fallback_selected',
                             {'provider': provider, 'role': role, 'leader': flow.get('leader')})
        self.store.event(flow['id'], 'agent_started', {'provider': provider, 'role': role, 'call': flow['calls']})
        if role == 'review' and worker and worker['provider'] == provider:
            self.store.event(flow['id'], 'self_review', {'provider': provider, 'independent': False})
        folder = self.store.home / 'runs' / flow['id'] / f"{flow['calls']:02d}-{role}-{provider}"
        attempt_id = self._attempt(flow, provider, role, folder)
        context = pack.pop('text')
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'context-pack.json').write_text(encode(pack), encoding='utf-8')
        self.store.event(flow['id'], 'context_pack', pack)
        before = ws.fingerprint(path, self.store)
        result = self.invoker.run(provider, role, context, path, folder, bool(project['network']),
                                  lambda pid: self._pid(attempt_id, pid),
                                  lambda: self._cancelled(flow['id'], generation))
        result.usage.setdefault('context_chars', len(context))
        result.usage.setdefault('context_files', len(pack['files']))
        if result.failure_category:
            result.usage['failure_category'] = result.failure_category
        readonly_changed = role in {'plan', 'review'} and ws.fingerprint(path, self.store) != before
        if readonly_changed:
            result = Result(error='Read-only role changed the worktree; inspect artifacts before continuing')
        self._finish_attempt(attempt_id, result, {'fingerprint_before': before,
                                                   'fingerprint_after': ws.fingerprint(path, self.store)})
        if self._cancelled(flow['id'], generation):
            self.store.event(flow['id'], 'late_result_ignored', {'attempt': attempt_id, 'generation': generation})
            return
        if readonly_changed:
            self.store.update(flow['id'], generation, status='blocked', error=result.error)
            return
        if result.unsafe_to_continue:
            self.store.update(flow['id'], generation, status='blocked', error='Old process could not be stopped; no failover permitted')
            return
        if not result.report:
            if result.failure_category == 'task_blocked':
                self.store.update(flow['id'], generation, status='blocked', error=result.error[-6000:])
                self.store.event(flow['id'], 'task_blocked', {'provider': provider, 'role': role,
                                                            'provider_health_changed': False})
                return
            category = failure(result.error)
            entry = self.config['providers'][provider]
            if category == 'model' and entry.get('model_fallback') == 'INHERIT' and entry.get('model_policy', 'MANUAL' if entry.get('model') else 'INHERIT') != 'INHERIT':
                self.store.event(flow['id'], 'model_fallback_selected', {'provider': provider, 'policy': 'INHERIT', 'operator_authorized': True})
                self.store.update(flow['id'], generation, status='queued', error='Configured model unavailable; retry with operator-authorized Provider Default inside existing call budget')
                return
            until = reset_time(result.error) or time.time() + (
                self.config['quota_cooldown_seconds'] if category == 'quota' else
                self.config['temporary_cooldown_seconds'] if category == 'temporary' else 86400)
            self.store.health(provider, until, category + ': ' + result.error[-1000:])
            self.store.update(flow['id'], generation, status='queued', error=result.error[-6000:])
            self.store.event(flow['id'], 'agent_failed', {'provider': provider, 'role': role, 'category': category, 'cooldown_until': until})
            # Next deterministic tick elects another available provider in this exact phase.
            return
        self.store.health(provider, 0, '')
        self._apply_report(flow, project, role, provider, result.report, before)

    def _apply_report(self, flow, project, role, provider, report, before):
        """Apply a validated phase report without accepting unsupported success claims."""
        generation, path = flow['generation'], flow['workspace']
        worker = self.store.one("SELECT provider FROM attempts WHERE workflow_id=? AND phase='implement' AND status='completed' ORDER BY created DESC LIMIT 1", (flow['id'],))
        if role == 'implement':
            self.store.event(flow['id'], 'files_changed', ws.file_changes(path))
        self.store.remember(project['id'], 'checkpoint', role + ': ' + report['summary'][:3500])
        if role == 'plan':
            complexity = 'complex' if report['complexity'] == 'complex' else flow['complexity']
            self.store.update(flow['id'], generation, status='queued', phase='implement',
                              plan=encode(report), complexity=complexity, error='', summary=report['summary'])
        elif role == 'implement':
            self.store.update(flow['id'], generation, status='queued', phase='verify',
                              summary=report['summary'], error='', review=encode({'previous_findings': json.loads(flow['review']).get('findings', [])}))
        else:
            if report['verdict'] not in {'approve', 'changes_requested'}:
                self.store.update(flow['id'], generation, status='blocked', error='Reviewer returned no usable verdict')
                return
            reviews = json.loads(flow['review']).get('reviews', [])
            reviews.append({'provider': provider, 'fingerprint': before, 'report': report,
                            'independent_provider': bool(worker and worker['provider'] != provider)})
            review = {'reviews': reviews, 'findings': report['findings']}
            if report['verdict'] == 'changes_requested' or report['findings']:
                self.repair(flow, 'Reviewer requested changes', review)
                return
            required = self.config['auto'][flow['complexity']]['reviewers']
            if len(reviews) < required:
                priority = list(dict.fromkeys(([flow['leader']] if flow['leader'] else []) + self.config['reviewer_priority']))
                reviewed = [r['provider'] for r in reviews]
                next_reviewer = choose(self.config, self.store, 'review', priority, excluded=reviewed)
                health = {h['provider']: h for h in self.store.all('SELECT * FROM health')}
                cooling = any(p not in reviewed and p in health and
                              health[p]['reason'].startswith(('quota:', 'temporary:')) and health[p]['until'] > time.time()
                              for p in priority if self.config['providers'].get(p, {}).get('enabled'))
                if next_reviewer or cooling:
                    self.store.update(flow['id'], generation, status='queued', phase='review', review=encode(review), error='')
                    return
            self.store.update(flow['id'], generation, status='completed', review=encode(review), error='', summary=report['summary'])
            self.store.event(flow['id'], 'completed', {'reviews': len(reviews), 'calls': flow['calls']})

    def repair(self, flow, reason, review=None):
        """Schedule an allowed implementation repair within existing repair/call limits."""
        fields = {'review': encode(review)} if review is not None else {}
        if flow['repairs'] >= flow['max_repairs']:
            self.store.update(flow['id'], status='needs_review', error=reason + '; repair budget exhausted', **fields)
        else:
            self.store.update(flow['id'], status='queued', phase='implement', repairs=flow['repairs'] + 1, error=reason, **fields)
        self.store.event(flow['id'], 'repair_requested', {'reason': reason})

    def verify(self, flow, project):
        """Run configured verification commands and record independent evidence."""
        generation = flow['generation'] + 1
        if not self.store.update(flow['id'], flow['generation'], status='running', generation=generation):
            return
        flow['generation'] = generation
        self.store.event(flow['id'], 'verification_started', {'commands': json.loads(project['verify'])})
        before = ws.fingerprint(flow['workspace'], self.store)
        folder = self.store.home / 'runs' / flow['id'] / f"verify-{generation}"
        folder.mkdir(parents=True, exist_ok=True)
        attempt_id = self._attempt(flow, 'local', 'verify', folder)
        results = []
        for index, command in enumerate(json.loads(project['verify'])):
            args = [sys.executable if value == '{python}' else value for value in command]
            process = None
            output = folder / f'{index}.log'
            try:
                args = resolve_command(args)
                with output.open('wb') as log:
                    process = spawn(args, cwd=flow['workspace'], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                    env={**os.environ, **self.config.get('_execution_environment', {})})
                self._pid(attempt_id, process.pid)
                deadline = time.monotonic() + self.config['verify_timeout_seconds']
                while process.poll() is None:
                    if self._cancelled(flow['id'], generation):
                        stop_tree(process)
                        self._finish_attempt(attempt_id, Result(error='cancelled'))
                        return
                    if time.monotonic() > deadline:
                        if not stop_tree(process):
                            raise ValueError('Verification process could not be stopped')
                        break
                    time.sleep(0.1)
                code = process.wait()
                results.append({'command': command, 'exit_code': code, 'output': read_tail(output, 6000)})
            finally:
                if process is not None and process.poll() is None:
                    stop_tree(process)
        evidence = {'fingerprint_before': before, 'fingerprint_after': ws.fingerprint(flow['workspace'], self.store), 'checks': results}
        passed = results and all(item['exit_code'] == 0 for item in results)
        self._finish_attempt(attempt_id, Result(report={'verified': bool(passed)}), {
            'fingerprint_before': before, 'fingerprint_after': evidence['fingerprint_after'],
            'checks': [{'command': item['command'], 'exit_code': item['exit_code']} for item in results]})
        if self._cancelled(flow['id'], generation):
            return
        if evidence['fingerprint_after'] != before:
            self.store.update(flow['id'], generation, status='blocked', verification=encode(evidence),
                              error='Verification command modified source files; review the worktree')
            return
        self.store.update(flow['id'], generation, verification=encode(evidence))
        self.store.event(flow['id'], 'verification', {'passed': bool(passed), 'fingerprint': before})
        if not passed:
            self.repair(flow, 'Verification failed; fix the recorded test output')
        elif self.config['auto'][flow['complexity']]['reviewers'] == 0:
            self.store.update(flow['id'], generation, status='completed', error='',
                              summary=flow.get('summary') or 'Small task completed; configured verification passed; AI review skipped by Auto')
        else:
            self.store.update(flow['id'], generation, status='queued', phase='review', error='')

    def serve(self):
        """Run the locked daemon loop and recover queued work without model polling."""
        with FileLock(self.store.home / 'daemon.lock'):
            from .service import daemon_version
            (self.store.home / 'daemon.pid').write_text(str(os.getpid()),encoding='utf-8')
            (self.store.home / 'daemon.version').write_text(daemon_version(), encoding='utf-8')
            self.recover()
            (self.store.home / 'stop').unlink(missing_ok=True)
            while not (self.store.home / 'stop').exists():
                # Reload between steps, never interrupt a writer to change settings.
                from .config import load
                self.config = load(self.store.home)
                if isinstance(self.invoker, Invoker):
                    self.invoker.config = self.config
                (self.store.home / 'heartbeat').write_text(str(time.time()), encoding='utf-8')
                if not self.tick():
                    self.maybe_cleanup()
                    time.sleep(self.config['poll_seconds'])
