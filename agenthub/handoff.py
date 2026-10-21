"""Versioned, fenced handoffs. Agent claims never become verifier evidence."""
import json
import re
import time


def strings():
    return {'type': 'array', 'items': {'type': 'string'}}


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


DELTA_SCHEMA = object_schema({
    'intent': object_schema({'rationale': {'type': 'string'}}),
    'progress': object_schema({'completed': strings(), 'in_progress': strings(), 'unknowns': strings()}),
    'attempts': {'type': 'array', 'items': object_schema({
        'approach_id': {'type': 'string'},
        'status': {'type': 'string', 'enum': ['proposed', 'tried', 'blocked', 'rejected', 'succeeded']},
        'reason': {'type': 'string'}, 'evidence_refs': strings(), 'revisit_if': {'type': 'string'}})},
    'decisions': {'type': 'array', 'items': object_schema({
        'decision': {'type': 'string'}, 'reason': {'type': 'string'}})},
    'next_action': object_schema({'action': {'type': 'string'}, 'approach_id': {'type': 'string'},
                                  'role': {'type': 'string', 'enum': ['plan', 'implement', 'verify', 'review']},
                                  'files': strings(), 'stop_conditions': strings()})})


def validate_delta(value):
    def validate(node, schema):
        kind = schema['type']
        if kind == 'object':
            if not isinstance(node, dict) or set(node) != set(schema['required']):
                raise ValueError('Invalid structured handoff fields')
            for key, sub in schema['properties'].items():
                validate(node[key], sub)
        elif kind == 'array':
            if not isinstance(node, list) or len(node) > 30:
                raise ValueError('Handoff list exceeds 30 entries')
            for item in node:
                validate(item, schema['items'])
        elif not isinstance(node, str) or len(node) > 2000:
            raise ValueError('Invalid handoff text')
        if 'enum' in schema and node not in schema['enum']:
            raise ValueError('Invalid handoff approach status')
    validate(value, DELTA_SCHEMA)
    for item in value['attempts']:
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', item['approach_id']):
            raise ValueError('Invalid approach ID')
        if item['status'] in {'rejected', 'blocked'} and not item['reason'].strip():
            raise ValueError('Rejected/blocked approaches require a reason')
    ids = [item['approach_id'] for item in value['attempts']]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate approach ID in handoff')
    next_id = value['next_action']['approach_id']
    if next_id and not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', next_id):
        raise ValueError('Invalid next approach ID')
    for name in value['next_action']['files']:
        if not name or name.startswith(('/', '\\')) or ':' in name or '..' in name.replace('\\', '/').split('/'):
            raise ValueError('Handoff file must be repository relative')
    if len(json.dumps(value)) > 18000:
        raise ValueError('Structured handoff too large; summarize it')
    return value


def next_role(state):
    # Older snapshots lacked the explicit target role. Recover the normal phase
    # boundary, never treat planner tool restrictions as the worker's permissions.
    return state.get('next_action', {}).get('role') or {
        'plan': 'implement', 'implement': 'verify', 'verify': 'review', 'review': 'implement'
    }.get(state.get('last_observation', {}).get('phase'))


def guard(handoff, current_fingerprint=None, role=None):
    state = handoff.get('checkpoint', {})
    target_role = next_role(state)
    if role and target_role and role != target_role:
        return
    rejected = {x['approach_id'] for x in state.get('attempts', []) if x['status'] == 'rejected'}
    selected = state.get('next_action', {}).get('approach_id')
    allowance = handoff.get('approach_allowance', {})
    approved = (current_fingerprint is not None and allowance.get('approach_id') == selected
                and allowance.get('fingerprint') == current_fingerprint
                and allowance.get('role') == target_role
                and allowance.get('revision') == state.get('revision'))
    if selected in rejected and not approved:
        raise ValueError('Next action repeats a rejected approach; operator must choose a different approach. '
                         'Or review changed conditions and use ma handoff ID --allow-approach APPROACH --reason REASON, then ma retry ID.')


def allow_approach(store, workflow_id, approach_id, reason):
    """Explicit local operator action; not exposed as an MCP/worker capability."""
    import os
    from .workspace import fingerprint
    if os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot approve a rejected approach')
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise ValueError('Operator must explain the new evidence or changed conditions')
    flow = store.workflow(workflow_id)
    if not flow.get('workspace'):
        raise ValueError('No saved worktree to review')
    source_hash = fingerprint(flow['workspace'], store)
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        flow = dict(db.execute('SELECT * FROM workflows WHERE id=?', (workflow_id,)).fetchone())
        handoff = json.loads(flow['handoff'])
        state = handoff.get('checkpoint', {})
        selected = state.get('next_action', {}).get('approach_id')
        if flow['status'] != 'blocked' or selected != approach_id or not any(
                x['approach_id'] == approach_id and x['status'] == 'rejected' for x in state.get('attempts', [])):
            raise ValueError('Only the blocked next action can receive an operator allowance')
        allowance = {'approach_id': approach_id, 'reason': reason.strip(),
                     'revision': state['revision'], 'fingerprint': source_hash, 'role': next_role(state)}
        handoff['approach_allowance'] = allowance
        db.execute('UPDATE workflows SET handoff=?,updated=? WHERE id=?',
                   (json.dumps(handoff, ensure_ascii=False), time.time(), workflow_id))
        db.execute('INSERT INTO events(workflow_id,kind,data,created) VALUES(?,?,?,?)',
                   (workflow_id, 'approach_allowed_by_operator', json.dumps(allowance), time.time()))
    return 'Approved for one attempt on the reviewed source. Run ma retry ' + workflow_id + ' within the existing call budget.'


def checkpoint(db, flow, attempt, report=None, error='', observation=None):
    """Call inside the attempt-result transaction; fence old/cancelled writers."""
    if flow['generation'] != attempt['generation'] or flow['status'] in {'cancelled', 'blocked'}:
        return
    handoff = json.loads(flow['handoff'])
    old = handoff.get('checkpoint', {})
    allowance = handoff.pop('approach_allowance', None)
    delta = (report or {}).get('handoff')
    if delta is not None:
        validate_delta(delta)
    ledger = {x['approach_id']: x for x in old.get('attempts', [])}
    for item in (delta or {}).get('attempts', []):
        # A model may add observations, but cannot erase a recorded rejection.
        prior = ledger.get(item['approach_id'])
        if not prior or prior['status'] != 'rejected':
            ledger[item['approach_id']] = dict(item, reported_by=attempt['provider'], attempt_id=attempt['id'])
    if len(ledger) > 100:
        raise ValueError('Approach ledger full; operator review required, history retained')
    progress = (delta or {}).get('progress', old.get('progress', {
        'completed': [], 'in_progress': [], 'unknowns': ['Legacy report: detailed progress was not supplied.']}))
    progress = {key: list(items) for key, items in progress.items()}
    if error and not report:
        progress['unknowns'] = list(dict.fromkeys(progress['unknowns'] + [
            'Attempt ' + attempt['id'] + ' failed/interrupted; unreported work and rationale are unknown.']))
    decisions = list({json.dumps(item, sort_keys=True): item for item in
                      old.get('decisions', []) + (delta or {}).get('decisions', [])}.values())
    state = {'version': 2, 'revision': old.get('revision', 0) + 1,
             'generation': flow['generation'], 'workflow_id': flow['id'],
             'intent': {'goal': flow['objective'],
                        'rationale': (delta or {}).get('intent', old.get('intent', {})).get('rationale', 'UNKNOWN; not reported'),
                        'acceptance': (report or {}).get('acceptance',
                        old.get('intent', {}).get('acceptance', json.loads(flow['plan']).get('acceptance', [])))},
             'progress': progress, 'attempts': list(ledger.values()), 'decisions': decisions,
             'next_action': (delta or {}).get('next_action', old.get('next_action', {
                 'action': 'Continue the recorded workflow phase; inspect current diff and verification.',
                 'approach_id': '', 'role': {'plan': 'implement', 'implement': 'verify', 'verify': 'review'}.get(attempt['phase'], 'implement'),
                 'files': [], 'stop_conditions': []})),
             'last_observation': {'attempt_id': attempt['id'], 'provider': attempt['provider'],
                                  'phase': attempt['phase'], 'error': error[-2000:]},
             'hub_observation': observation or old.get('hub_observation', {}),
             'claims_are_unverified': True}
    handoff['checkpoint'] = state
    # A worker allowance must not be spent by a preceding read-only planner.
    # Keep it only for the same action/role and unchanged independently observed source.
    if (allowance and attempt['phase'] != allowance.get('role')
            and state['next_action'].get('approach_id') == allowance['approach_id']
            and next_role(state) == allowance.get('role')
            and (observation or {}).get('fingerprint_before') == allowance['fingerprint']
            and (observation or {}).get('fingerprint_after') == allowance['fingerprint']):
        handoff['approach_allowance'] = dict(allowance, revision=state['revision'])
    encoded = json.dumps(handoff, ensure_ascii=False)
    updated = db.execute("UPDATE workflows SET handoff=?,updated=? WHERE id=? AND generation=? AND status NOT IN ('cancelled','blocked')",
                         (encoded, time.time(), flow['id'], flow['generation'])).rowcount
    if not updated:
        return
    db.execute('INSERT INTO events(workflow_id,kind,data,created) VALUES(?,?,?,?)',
               (flow['id'], 'handoff_checkpoint', json.dumps(state, ensure_ascii=False), time.time()))
