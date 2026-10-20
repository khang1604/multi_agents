"""Plain-text views derived exclusively from persisted workflow evidence."""
import json
import time


def render(state):
    lines = ['MULTI AGENTS — LIVE MONITOR',
             'Workflow: ' + state['id'] + '   Project: ' + state.get('project_id', 'Unknown'),
             'State: ' + state['status'] + ' / ' + state['phase'],
             'Task: ' + state.get('objective', '')[:300],
             f"Calls: {state['calls']}/{state['max_calls']}   Repairs: {state['repairs']}/{state['max_repairs']}",
             f"Elapsed: {max(0, int((state['updated'] if state['status'] in {'completed','blocked','cancelled','needs_review'} else time.time()) - state['created']))}s"]
    for attempt in state.get('attempts', []):
        usage = attempt.get('usage', {})
        if isinstance(usage, str):
            usage = json.loads(usage)
        lines.append(f"{attempt['provider']:12} {attempt['status']:12} {attempt['phase']:10} model={usage.get('actual_model', 'Unknown')}")
    for check in state.get('verification', {}).get('checks', []):
        lines.append(f"Check exit={check['exit_code']}: " + ' '.join(check['command']))
    for event in reversed(state.get('events', [])):
        data = event['data'] if isinstance(event['data'], dict) else json.loads(event['data'])
        lines.append(time.strftime('[%H:%M:%S]', time.localtime(event['created'])) + ' ' + event['kind'] + ' ' + json.dumps(data, ensure_ascii=False)[:300])
    if state.get('error'):
        lines.append('Reason: ' + state['error'][-1000:])
    if state.get('delivery'):
        lines.append('Delivery: ' + state['delivery'])
    lines.append('Ctrl+C exits monitoring; it does not cancel the workflow.')
    return '\n'.join(lines)
