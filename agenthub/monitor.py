"""Plain-text views derived exclusively from persisted workflow evidence."""
import json
import time
from .presentation import brief, text


def render(state):
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
    return '\n'.join(lines)
