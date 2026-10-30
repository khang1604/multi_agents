"""Plain-text views derived exclusively from persisted workflow evidence."""
import json
import time
from .presentation import brief, text


def changed_files(changes):
    """Display actual per-file additions/deletions without inventing binary or legacy counts."""
    rows = changes.get('stats', [])
    if not rows:
        return []
    visible = rows[:20]
    names = [text(row['path'], 90) for row in visible]
    width = max(map(len, names))
    lines = ['Files changed:']
    for name, row in zip(names, visible):
        counts = ('binary' if row.get('binary') else 'stats unavailable' if row.get('unavailable')
                  else '+' + str(row['added']) + '  -' + str(row['removed']))
        lines.append(f'  {name:<{width}}  {counts}')
    total = changes.get('total_files', len(rows))
    if total > len(visible):
        lines.append('  ... ' + str(total - len(visible)) + ' more files; use ma review --json for details')
    return lines


def outcome(state, include_files=True):
    """Render the saved agent answer and distinguish delivered from applied files."""
    lines = []
    response = state.get('agent_response', {}).get('summary') or state.get('summary')
    if response:
        lines.extend(['', 'Agent response:' if state['status'] == 'completed' else 'Last agent response:',
                      text(response, limit=4000)])
    if include_files:
        lines.extend(changed_files(state.get('file_changes', {})))
    if state['status'] == 'completed':
        acceptance = state.get('acceptance', {})
        if acceptance.get('status') == 'accepted':
            lines.append('Files: applied to project' + (' automatically.' if acceptance.get('automatic') else '.'))
        elif acceptance.get('status') == 'partial':
            lines.append('Files: partially applied. Remaining: ' + brief(acceptance.get('remaining_files', [])))
            lines.append('Next: ma accept ' + state['id'])
        else:
            lines.append('Files: ready to apply. Next: ma review ' + state['id'] + '; ma accept ' + state['id'])
    elif ('call budget exhausted' in state.get('error', '').lower()
          and state.get('calls', 0) >= state.get('max_calls', 0)):
        lines.append('Files: not applied; the protected workflow is incomplete.')
        lines.append('Next: ma retry ' + state['id'] + ' --extra-calls N; after completion, run ma accept ' + state['id'])
    return lines


class ProgressView:
    """Append concise, deduplicated milestones without repeatedly printing snapshots."""

    def __init__(self):
        """Track only progress already shown in this terminal monitoring session."""
        self.started = False
        self.attempts = {}
        self.events = set()
        self.verification = None
        self.lifecycle = None
        self.finished = False
        self.file_stats = None

    def render(self, state):
        """Return only newly observed user-facing milestones and the final response."""
        lines = []
        if not self.started:
            lines = ['Workflow: ' + text(state['id']), 'Task: ' + text(state.get('objective', ''), 1000), '']
            self.started = True
        timestamp = time.strftime('%H:%M:%S', time.localtime(state['updated']))

        def milestone(message):
            """Add one bounded, timestamped progress line without terminal control codes."""
            lines.append('[' + timestamp + '] ' + message)

        for attempt in state.get('attempts', [])[-3:]:
            if attempt['phase'] == 'verify':
                continue
            key = attempt.get('id') or (attempt['provider'], attempt['phase'], attempt.get('generation'))
            status = attempt['status']
            if self.attempts.get(key) == status:
                continue
            self.attempts[key] = status
            label = 'started' if status == 'running' else status
            milestone(text(attempt['provider']) + ' · ' + text(attempt['phase']) + ' ' + text(label))

        for event in reversed(state.get('events', [])):
            if event['kind'] not in {'files_changed', 'leader_changed', 'auto_accept_blocked'}:
                continue
            data = event['data'] if isinstance(event['data'], dict) else json.loads(event['data'])
            key = (event['kind'], event['created'], json.dumps(data, sort_keys=True))
            if key in self.events:
                continue
            self.events.add(key)
            if event['kind'] == 'files_changed':
                milestone(str(data.get('total_files', len(data.get('files', [])))) + ' files changed')
            elif event['kind'] == 'leader_changed':
                milestone('Leader changed: ' + brief(data))
            else:
                milestone('Automatic file application blocked: ' + text(data.get('reason', 'Review required'), 400))

        changes = state.get('file_changes', {})
        if changes.get('stats'):
            signature = json.dumps(changes, sort_keys=True)
            if signature != self.file_stats:
                lines.extend(changed_files(changes))
                self.file_stats = signature

        verification = state.get('verification', {})
        checks = verification.get('checks', [])
        signature = json.dumps(verification, sort_keys=True)
        if checks and signature != self.verification:
            passed = sum(check['exit_code'] == 0 and not check.get('reason') for check in checks)
            milestone(f'Tests: {passed}/{len(checks)} passed')
            self.verification = signature

        status = state['status']
        lifecycle = (status, state['phase'], state.get('error'), state.get('next_run'))
        if status in {'completed', 'blocked', 'cancelled', 'needs_review'}:
            if not self.finished:
                elapsed = max(0, int(state['updated'] - state['created']))
                milestone(status.replace('_', ' ').capitalize() + f" · {elapsed}s · {state['calls']}/{state['max_calls']} calls")
                if state.get('error'):
                    lines.append('Reason: ' + text(state['error'], 1000))
                lines.extend(outcome(state, include_files=self.file_stats is None))
                self.finished = True
        elif lifecycle != self.lifecycle:
            if status == 'waiting':
                milestone('Waiting: ' + text(state.get('error') or 'Provider is unavailable', 400))
                if state.get('next_run'):
                    lines.append('Next retry: ' + time.strftime('%Y-%m-%d %H:%M:%S %z', time.localtime(state['next_run'])))
            elif status == 'queued':
                milestone('Queued · ' + text(state['phase']))
            elif not state.get('attempts'):
                milestone(text(status.capitalize()) + ' · ' + text(state['phase']))
        self.lifecycle = lifecycle
        return '\n'.join(lines)


def render(state):
    """Render a bounded progress view from actual persisted workflow evidence."""
    lines = ['Workflow: ' + state['id'] + '   Project: ' + state.get('project_id', 'Unknown'),
             'State: ' + state['status'] + ' / ' + state['phase'],
             'Task: ' + text(state.get('objective', '')),
             f"Calls: {state['calls']}/{state['max_calls']}   Repairs: {state['repairs']}/{state['max_repairs']}",
             f"Elapsed: {max(0, int((state['updated'] if state['status'] in {'completed','blocked','cancelled','needs_review'} else time.time()) - state['created']))}s"]
    for attempt in state.get('attempts', [])[-3:]:
        usage = attempt.get('usage', {})
        if isinstance(usage, str):
            usage = json.loads(usage)
        lines.append(f"{attempt['provider']:12} {attempt['status']:12} {attempt['phase']:10} model={usage.get('actual_model', 'Unknown')}")
    checks = state.get('verification', {}).get('checks', [])
    if checks:
        lines.append(f"Tests: {sum(check['exit_code'] == 0 for check in checks)}/{len(checks)} passed")
    for event in reversed(state.get('events', [])[:2]):
        data = event['data'] if isinstance(event['data'], dict) else json.loads(event['data'])
        lines.append(time.strftime('[%H:%M:%S]', time.localtime(event['created'])) + ' ' + text(event['kind']) + ' ' + brief(data))
    if state.get('error'):
        lines.append('Reason: ' + text(state['error']))
    if state.get('next_run') and state['status'] == 'waiting':
        lines.append('Next retry: ' + time.strftime('%Y-%m-%d %H:%M:%S %z', time.localtime(state['next_run'])))
    if state.get('delivery'):
        lines.append('Delivery: ' + state['delivery'])
    if state['status'] in {'completed', 'blocked', 'cancelled', 'needs_review'}:
        lines.extend(outcome(state))
    return '\n'.join(lines)
