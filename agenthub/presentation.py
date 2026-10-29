"""Compact terminal views; structured data stays available through --json."""


def text(value, limit=180):
    """Sanitize and bound one value for plain-text presentation."""
    clean = ' '.join(''.join(c if c.isprintable() else ' ' for c in str(value)).split())
    return clean if len(clean) <= limit else clean[:limit - 3] + '...'


def brief(value):
    """Summarize a nested result without dumping full source or histories."""
    if value is None:
        return '-'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return text(', '.join(str(item) for item in value)) or '(empty)'
        return str(len(value)) + ' items'
    if isinstance(value, dict):
        preferred = ('name', 'id', 'provider', 'phase', 'status', 'error', 'path')
        keys = [key for key in preferred if key in value]
        if not keys:
            keys = list(value)[:4]
        return text(' | '.join(key + '=' + brief(value[key]) for key in keys)) or '(empty)'
    return text(value)


def command_line(command):
    """Render an argument array for display without executing it."""
    import os
    import shlex
    import subprocess
    import sys
    values = [sys.executable if arg == '{python}' else text(arg) for arg in command]
    return subprocess.list2cmdline(values) if os.name == 'nt' else shlex.join(values)


def compact(value):
    """Build a short human-readable CLI result from structured state."""
    if isinstance(value, list):
        lines = [brief(row) for row in value[-8:]]
        if len(value) > 8:
            lines.insert(0, f'{len(value)} entries; showing last 8 (--json for all)')
        return '\n'.join(lines) or 'No entries.'
    if not isinstance(value, dict):
        return brief(value)
    command = value.get('command')
    if isinstance(command, list):
        quoted = command_line(command)
        return '\n'.join((brief(value.get('status', 'Command')), quoted))
    if 'id' in value and 'phase' in value and 'status' in value:
        lines = [f"Workflow: {text(value['id'])}",
                 f"State: {brief(value['status'])} / {brief(value['phase'])} | Leader: {brief(value.get('leader'))}",
                 f"Calls: {value.get('calls', 0)}/{value.get('max_calls', '?')}"]
        for key in ('error', 'delivery'):
            if value.get(key):
                lines.append(key.title() + ': ' + brief(value[key]))
        return '\n'.join(lines)
    if 'project' in value and 'context_changed' in value:
        project = value['project']
        lines = [f"Project: {brief(project.get('name'))}",
                          f"Path: {brief(project.get('path'))}",
                          f"Context updated: {brief(value['context_changed'])} | Tests configured: {brief(value['verification_configured'])} | Tests run: {brief(value.get('verification_executed', False))} | AI calls: {value['ai_calls']}"]
        if value.get('readiness', {}).get('ready'):
            lines.append('Baseline verifier: PASS | Hub MCP: OK')
            lines.append('Next: Copilot Chat → @hub PROMPT' if value['readiness'].get('chat_bridge_configured')
                         else 'Next: setup global → install @hub, or ma integrations chat --apply')
        for command in value.get('verification_command', []):
            lines.append('Check: ' + command_line(command))
        if not value['verification_configured']:
            lines.append('Next: ma init --verify-command EXECUTABLE ARGS')
        return '\n'.join(lines)
    # Do not dump source excerpts, manifests or complete workflow payloads.
    hidden = {'documents', 'files', 'plan', 'review', 'handoff', 'events', 'attempts'}
    lines = []
    for key, item in value.items():
        if key in hidden:
            lines.append(f'{key}: {len(item) if item else 0} items')
        else:
            lines.append(text(key) + ': ' + brief(item))
        if len(lines) == 8:
            if len(value) > 8:
                lines.append('More details: --json')
            break
    return '\n'.join(lines) or 'Done.'
