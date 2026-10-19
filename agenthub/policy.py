"""Deterministic routing and error classification: no model calls for supervision."""
import re
import time

RISK = re.compile(r'auth|login|password|security|payment|migration|database|schema|permission|encrypt|deploy|đăng nhập|bảo mật|thanh toán|phân quyền|cơ sở dữ liệu', re.I)
TRIVIAL = re.compile(r'typo|spelling|chính tả|readme|documentation|tài liệu', re.I)


def classify(objective):
    if RISK.search(objective) or len(objective) > 2400:
        return 'complex'
    if TRIVIAL.search(objective) and len(objective) < 240:
        return 'small'
    return 'standard'


def failure(text):
    text = text.lower()
    if any(t in text for t in ['bwrap:', 'permission denied', 'operation not permitted', 'blocked by policy', 'sandbox error']):
        return 'permissions'
    if any(t in text for t in ['not authenticated', 'authentication required', 'invalid api key', 'unauthorized', 'login required', 'expired credentials']):
        return 'auth'
    if any(t in text for t in ['usage limit', 'quota exceeded', 'quota_exceeded', 'session limit', 'out of credits', 'insufficient_quota']):
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
    return None


def choose(config, store, role, priority, excluded=(), now=None):
    from .platforms import resolve_command
    now = time.time() if now is None else now
    health = {r['provider']: r for r in store.all('SELECT * FROM health')}
    for name in priority:
        entry = config['providers'].get(name)
        if name in excluded or not entry or not entry.get('enabled') or role not in entry['roles']:
            continue
        if health.get(name, {}).get('until', 0) > now:
            continue
        try:
            resolve_command(entry['command'])
        except (OSError, ValueError):
            continue
        return name
    return None
