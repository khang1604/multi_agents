import json
import time
from pathlib import Path
from .config import load
from .policy import classify
from .store import Store, encode
from .platforms import pid_alive
from .service import start_daemon, daemon_status


class Hub:
    def __init__(self, home):
        """Initialize Hub state and its configured dependencies."""
        self.store = Store(home)
        self.config = load(home)

    def start(self, project, objective, request_key, max_calls=None, mode='auto', launch=True, prepared_plan=None, handoff=None):
        """Validate a task request and create or recover its durable workflow without duplicate dispatch."""
        import os
        from .project_context import is_removed
        row = self.store.project(project)
        if os.environ.get('MULTI_AGENTS_WORKER'):
            raise ValueError('Recursive dispatch from an executing worker is forbidden')
        if is_removed(self.store.home, row['id']):
            raise ValueError('Project registration was removed; initialize it explicitly before dispatch')
        if not json.loads(row['verify']):
            raise ValueError('No verification commands configured; initialize with explicit --verify first')
        from .settings import effective_config
        config = effective_config(self.config, self.store.home, row['id'])
        if handoff is not None:
            from .workspace import validate_handoff
            validate_handoff(handoff)
        if mode not in {'auto', 'small', 'standard', 'complex'}:
            raise ValueError('Unknown mode')
        level = classify(objective) if mode == 'auto' else mode
        if prepared_plan is not None:
            if not isinstance(prepared_plan, dict) or set(prepared_plan) != {'summary','steps','acceptance','complexity'}:
                raise ValueError('prepared_plan needs summary, steps, acceptance and complexity')
            if not isinstance(prepared_plan['summary'], str) or not isinstance(prepared_plan['steps'], list) or not isinstance(prepared_plan['acceptance'], list):
                raise ValueError('Invalid prepared_plan')
            if not prepared_plan['steps'] or not prepared_plan['acceptance'] or not all(isinstance(x,str) for x in prepared_plan['steps'] + prepared_plan['acceptance']):
                raise ValueError('Plan needs concrete steps and acceptance criteria')
            if len(encode(prepared_plan)) > 12000 or prepared_plan['complexity'] not in {'small','standard','complex'}:
                raise ValueError('Invalid plan size/complexity')
            levels = ['small','standard','complex']
            level = levels[max(levels.index(level), levels.index(prepared_plan['complexity']))]
        policy = config['auto'][level]
        cap = policy['max_calls'] if max_calls is None else max_calls
        if not isinstance(cap, int) or not 1 <= cap <= 50:
            raise ValueError('max_calls must be 1–50')
        with self.store.connection() as db:
            db.execute("UPDATE health SET until=0, reason='' WHERE reason NOT LIKE 'quota:%'")
        flow = self.store.create(project, objective, request_key, level, cap, policy['max_repairs'])
        if handoff is not None and flow['calls'] == 0 and flow['handoff'] == '{}':
            self.store.update(flow['id'], handoff=encode(handoff))
        if prepared_plan is not None and flow['calls'] == 0 and flow['phase'] == 'plan':
            self.store.update(flow['id'], phase='implement', plan=encode(prepared_plan), leader='external-antigravity')
            self.store.event(flow['id'], 'prepared_plan_reused', {'saved_planner_call': True})
        if launch:
            start_daemon(self.store.home)
        return self.status(flow['id'])

    def status(self, workflow_id):
        """Read persisted workflow details, evidence, and current execution state."""
        flow = self.store.workflow(workflow_id)
        for key in ['plan', 'review', 'verification', 'handoff']:
            flow[key] = json.loads(flow[key])
        flow['attempts'] = self.store.all('SELECT id,provider,phase,generation,status,pid,artifact,created,ended,error,usage FROM attempts WHERE workflow_id=? ORDER BY created', (workflow_id,))
        for attempt in flow['attempts']:
            attempt['usage'] = json.loads(attempt['usage'])
        flow['events'] = self.store.all('SELECT id,kind,data,created FROM events WHERE workflow_id=? ORDER BY id DESC LIMIT 20', (workflow_id,))
        for event in flow['events']:
            event['data'] = json.loads(event['data'])
        from .acceptance import state
        flow['acceptance'] = state(self.store, workflow_id)
        changes = self.store.one("SELECT data FROM events WHERE workflow_id=? AND kind='files_changed' ORDER BY id DESC LIMIT 1", (workflow_id,))
        flow['file_changes'] = json.loads(changes['data']) if changes else {}
        # Only validated, persisted report fields are displayed; never reopen artifacts.
        flow['agent_response'] = {}
        report_row = self.store.one("SELECT outcome FROM attempts WHERE workflow_id=? AND phase='implement' AND status='completed' ORDER BY created DESC LIMIT 1", (workflow_id,))
        if report_row:
            try:
                report = json.loads(report_row['outcome'])
                if isinstance(report, dict) and isinstance(report.get('summary'), str):
                    flow['agent_response'] = {'summary': report['summary'][:4000]}
            except (ValueError, TypeError):
                pass
        flow['daemon'] = daemon_status(self.store.home)
        flow['workspace_retired'] = bool(flow.get('delivery') and not Path(flow.get('workspace') or '').exists())
        return flow

    def brief(self, workflow_id):
        """Build a bounded workflow summary for CLI or chat clients."""
        state = self.status(workflow_id)
        result = {key:state[key] for key in ['id','status','phase','leader','complexity','calls','max_calls','next_run','workspace','delivery','workspace_retired','daemon','acceptance']}
        result['summary'] = state['summary'][:1500]
        result['error'] = state['error'][-1500:]
        active = next((a for a in reversed(state['attempts']) if a['generation'] == state['generation']
                       and a['phase'] == state['phase']), None)
        result['current_agent'] = ({'provider': active['provider'], 'role': active['phase'],
                                    'status': active['status'], 'model': active['usage'].get('actual_model', 'UNKNOWN')}
                                   if active else None)
        result['checks'] = [{'command':check['command'],'exit_code':check['exit_code']} for check in state['verification'].get('checks',[])]
        result['reviews'] = [{'provider':review['provider'],'verdict':review['report']['verdict'],
                              'findings':review['report']['findings'][:5]} for review in state['review'].get('reviews',[])]
        result['reports'] = []
        # Validated reports are already checkpointed in SQLite. Never read arbitrary
        # artifact/source paths just to display a completed or partial answer.
        for attempt in self.store.all("SELECT outcome FROM attempts WHERE workflow_id=? AND phase='implement' AND status='completed' ORDER BY created LIMIT 50", (workflow_id,)):
            try:
                report = json.loads(attempt['outcome'])
                if not isinstance(report, dict) or report.get('outcome') != 'completed':
                    continue
                result['reports'].append({'summary': str(report.get('summary', ''))[:1500],
                    'findings': [item[:700] for item in report.get('findings', [])[:5] if isinstance(item, str)]})
            except (ValueError, TypeError):
                continue
        if len(result['reports']) > 2:
            result['reports'] = [result['reports'][0], result['reports'][-1]]
        result['changed_files'] = next((event['data'].get('files', [])[:8]
            for event in state['events'] if event['kind'] == 'files_changed'), [])
        result['context_chars_by_call'] = [attempt['usage'].get('context_chars') for attempt in state['attempts'] if attempt['phase'] != 'verify']
        result['details'] = 'Request workflow_status with include_details=true only if needed.'
        return result

    def retry(self, workflow_id, extra_calls=0, launch=True, not_before=0, request_key=None):
        """Resume an eligible workflow while preserving idempotency, checkpoints, and call caps."""
        import math
        if type(not_before) not in (int, float) or not math.isfinite(not_before) or not_before < 0:
            raise ValueError('not_before must be a finite nonnegative Unix timestamp')
        if request_key is not None and (not isinstance(request_key, str) or not 1 <= len(request_key) <= 128):
            raise ValueError('Invalid retry request key')
        if not isinstance(extra_calls, int) or not 0 <= extra_calls <= 20:
            raise ValueError('extra_calls must be 0–20; zero preserves the existing cap')
        flow = self.store.workflow(workflow_id)
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM workflows WHERE id=?', (workflow_id,)).fetchone()
            if request_key:
                previous = db.execute("SELECT data FROM events WHERE workflow_id=? AND kind IN ('retry_requested','resume_scheduled') ORDER BY id DESC", (workflow_id,)).fetchall()
                for event in previous:
                    data = json.loads(event['data'])
                    if data.get('request_key') == request_key:
                        if data.get('extra_calls') != extra_calls or data.get('not_before', 0) != not_before:
                            raise ValueError('Retry key was already used with different settings')
                        return self.status(workflow_id)
            if current['status'] not in {'blocked', 'cancelled', 'needs_review', 'waiting'}:
                raise ValueError('Only blocked/cancelled/needs_review/waiting workflows can be retried')
            active = db.execute("SELECT id FROM workflows WHERE project_id=? AND id != ? AND status IN ('queued','running','waiting','recovering')",
                                (flow['project_id'], workflow_id)).fetchone()
            if active:
                raise ValueError('Another workflow is active for this project')
            attempts = db.execute('SELECT pid FROM attempts WHERE workflow_id=? ORDER BY created DESC LIMIT 1', (workflow_id,)).fetchall()
            if any(pid_alive(row['pid']) for row in attempts):
                raise ValueError('Previous process may still exist. Wait for it to stop before retrying.')
            new_cap = current['max_calls'] + extra_calls
            if current['phase'] != 'verify' and current['calls'] >= new_cap:
                raise ValueError('Call cap exhausted; explicitly grant extra_calls to continue')
            phase = 'verify' if current['phase'] == 'review' else current['phase']
            review = '{}' if phase == 'verify' else current['review']
            scheduled = not_before > time.time()
            db.execute("UPDATE health SET until=0, reason='' WHERE reason NOT LIKE 'quota:%'")
            db.execute("UPDATE workflows SET status=?,generation=generation+1,next_run=?,error=?,max_calls=?,phase=?,review=?,created=?,updated=? WHERE id=?",
                       ('waiting' if scheduled else 'queued', not_before if scheduled else 0,
                        'Scheduled resume; no AI calls before next_run' if scheduled else '',
                        new_cap, phase, review, time.time(), time.time(), workflow_id))
            self.store._event(db, workflow_id, 'resume_scheduled' if scheduled else 'retry_requested',
                              {'extra_calls': extra_calls, 'not_before': not_before, 'request_key': request_key})
        if launch:
            start_daemon(self.store.home)
        return self.status(workflow_id)

    def recover(self, project):
        """Recover project memory and unfinished workflow state for handoff."""
        row = self.store.project(project)
        memories=self.store.all('SELECT name,content,updated FROM memories WHERE project_id=? ORDER BY updated DESC LIMIT 8',(row['id'],))
        for memory in memories:
            if len(memory['content'])>1800: memory['content']=memory['content'][:1800]+' [truncated]'
        flows=self.store.all('SELECT id,status,phase,leader,complexity,calls,max_calls,next_run,workspace,delivery,summary,error FROM workflows WHERE project_id=? ORDER BY updated DESC LIMIT 5',(row['id'],))
        for flow in flows:
            flow['summary']=flow['summary'][:1000]; flow['error']=flow['error'][-1000:]
        return {'project': row, 'memories': memories,
                'workflows': flows,
                'provider_health': self.store.all('SELECT * FROM health'), 'daemon': daemon_status(self.store.home),
                'instruction': 'Do not duplicate active workflows. Completed changes require operator Accept, unless the operator enabled project Auto accept. Check acceptance status; never accept or enable auto accept on behalf of the operator. Read review and verification evidence. If all leaders have quota errors, the daemon waits without AI calls.'}
