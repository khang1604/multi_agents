"""Deterministic routing and error classification: no model calls for supervision."""
import re
import time

RISK = re.compile(r'auth|login|password|security|payment|migration|database|schema|permission|encrypt|deploy|\u0111\u0103ng nh\u1eadp|b\u1ea3o m\u1eadt|thanh to\xe1n|ph\xe2n quy\u1ec1n|c\u01a1 s\u1edf d\u1eef li\u1ec7u', re.I)
TRIVIAL = re.compile(r'typo|spelling|ch\xednh t\u1ea3|readme|documentation|t\xe0i li\u1ec7u', re.I)


def classify(objective):
    """Choose task complexity using local rules without a model call."""
    if RISK.search(objective) or len(objective) > 2400:
        return 'complex'
    if TRIVIAL.search(objective) and len(objective) < 240:
        return 'small'
    return 'standard'


def failure(text):
    """Classify provider diagnostics into model, permission, auth, quota, transient, or result errors."""
    text = text.lower()
    if any(t in text for t in ['model_not_found', 'model not found', 'invalid model', 'unsupported model', 'model unavailable', 'model is not available']):
        return 'model'
    if any(t in text for t in ['bwrap:', 'permission denied', 'operation not permitted', 'blocked by policy', 'sandbox error']):
        return 'permissions'
    if any(t in text for t in ['not authenticated', 'authentication required', 'invalid api key', 'unauthorized', 'login required', 'expired credentials']):
        return 'auth'
    if any(t in text for t in ['usage limit', 'quota exceeded', 'quota_exceeded', 'individual quota reached',
                               'session limit', 'out of credits', 'insufficient_quota']):
        return 'quota'
    if any(t in text for t in ['429', 'rate limit', 'overloaded', '529', '503', '502', 'connection reset', 'connection refused', 'error sending request', 'network is unreachable', 'stream disconnected', 'temporary failure in name resolution', 'timed out']):
        return 'temporary'
    return 'invalid_result'


def reset_time(text, now=None):
    """Only trust unambiguous numeric timestamps or relative delays, never guessed local clocks."""
    now = time.time() if now is None else now
    match = re.search(r'(?:resetsAt|reset_at|resetAt)\s*["\x27]?\s*[:=]\s*["\x27]?(\d{10,13})', text)
    if match:
        value = int(match[1])
        if value > 10**12:
            value /= 1000
        if now < value < now + 8 * 86400:
            return value
    match = re.search(r'(?:retry.after|try again in)\s*["\x27]?\s*[:=]?\s*(\d+)\s*(seconds?|minutes?|hours?)?', text, re.I)
    if match:
        multiplier = {'s': 1, 'm': 60, 'h': 3600}.get((match[2] or 's')[0].lower(), 1)
        return now + min(int(match[1]) * multiplier, 8 * 86400)
    # Official CLI durations may span several days: "Resets in 124h1m3s".
    match = re.search(r'\bresets? in\s+((?:\d+[hms])+)(?=$|[\s.,"\x27)])', text, re.I)
    if match:
        parts = re.findall(r'(\d+)([hms])', match[1].lower())
        units = [unit for _, unit in parts]
        if len(set(units)) == len(units) and units == sorted(units, key='hms'.index):
            delay = sum(int(value) * {'h': 3600, 'm': 60, 's': 1}[unit] for value, unit in parts)
            if 0 < delay <= 8 * 86400:
                return now + delay
    return None


def choose(config, store, role, priority, excluded=(), now=None):
    """Choose the first enabled eligible provider for a role outside its cooldown."""
    from .platforms import resolve_command
    now = time.time() if now is None else now
    health = {r['provider']: r for r in store.all('SELECT * FROM health')}
    for name in priority:
        entry = config['providers'].get(name)
        if name in excluded or not entry or not entry.get('enabled') or role not in entry['roles']:
            continue
        from .registry import SPECS
        if name not in SPECS or role not in SPECS[name]['roles']:
            continue
        if health.get(name, {}).get('until', 0) > now:
            continue
        try:
            from .registry import execution_command
            execution_command(name, entry)
        except (OSError, ValueError):
            continue
        return name
    return None
