import hashlib
import json
from pathlib import Path
import subprocess
import re
import time
import sys

EXCLUDED = {'.git', '.env', 'node_modules', '.venv', 'venv', '__pycache__', 'data', 'dist', 'build',
            'bin', 'obj', '.codex', '.claude', '.copilot', '.gemini', '.ssh', 'secrets', 'credentials'}


def git(path, *args, check=True):
    result = subprocess.run(['git', '-c', 'core.quotepath=false', '-c', 'core.longpaths=true', '-C', str(path), *args], capture_output=True,
                            encoding='utf-8', errors='replace', timeout=40)
    if check and result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def prepare(store, workflow, project):
    if workflow['workspace']:
        path = Path(workflow['workspace'])
        if not path.exists():
            raise ValueError('Saved worktree no longer exists; restore it before retrying')
        return str(path), workflow['base_commit']
    source = Path(project['path'])
    if Path(git(source, 'rev-parse', '--show-toplevel')).resolve() != source.resolve():
        raise ValueError('Register the repository root, not a subdirectory')
    # A clean, committed baseline makes isolated worktrees reproducible.
    if git(source, 'status', '--porcelain'):
        raise ValueError('Project has uncommitted changes. Commit/stash them before starting a workflow.')
    commit = git(source, 'rev-parse', 'HEAD')
    path = store.home / 'workspaces' / workflow['id']
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if git(path, 'rev-parse', 'HEAD') != commit:
            raise ValueError('Existing workspace does not match source HEAD')
    else:
        git(source, 'worktree', 'add', '--detach', str(path), commit)
    return str(path), commit


def files(root):
    root = Path(root)
    output = git(root, 'ls-files', '-c', '-o', '--exclude-standard')
    for name in sorted(set(output.splitlines())):
        rel = Path(name)
        if rel.is_absolute() or any(part in EXCLUDED or part.startswith('.env') for part in rel.parts):
            continue
        if (rel.suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.sqlite', '.sqlite3', '.db', '.dump', '.bak'}
                or rel.name.lower() in {'appsettings.json', 'appsettings.development.json', 'auth.json', 'credentials.json', 'secrets.json'}
                or rel.stem.lower() in {'secret', 'secrets', 'credentials', 'token', 'tokens'}):
            continue
        path = root / rel
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()):
            yield name, path


def fingerprint(root, store=None):
    digest = hashlib.sha256()
    for name, path in files(root):
        digest.update(name.encode())
        if store is not None:
            digest.update(cached_file(store, path, include_content=False)['sha256'].encode())
        else:
            with path.open('rb') as file:
                while chunk := file.read(65536):
                    digest.update(chunk)
    return digest.hexdigest()


def diff(root):
    parts = [git(root, 'diff', 'HEAD', '--no-ext-diff')]
    for name, path in files(root):
        tracked = git(root, 'ls-files', '--error-unmatch', '--', name, check=False)
        if not tracked:
            parts.append('NEW FILE ' + name + '\n' + read_text(path, 16000))
    return '\n'.join(parts)


def read_text(path, limit):
    try:
        with path.open('r', encoding='utf-8') as file:
            text = file.read(limit + 1)
        if '\x00' in text:
            return '[binary omitted]'
        return text[:limit] + ('\n[truncated]' if len(text) > limit else '')
    except (OSError, UnicodeError):
        return '[unreadable/binary omitted]'


def cached_file(store, path, include_content=True):
    path = Path(path).resolve()
    stat = path.stat()
    cached = store.one('SELECT * FROM file_cache WHERE path=?', (str(path),))
    if cached and cached['mtime_ns'] == stat.st_mtime_ns and cached['size'] == stat.st_size and (not include_content or cached['content']):
        if include_content:
            with store.connection() as db:
                db.execute('UPDATE file_cache SET last_used=? WHERE path=?', (time.time(), str(path)))
        return dict(cached, cache_hit=True)
    digest, prefix = hashlib.sha256(), bytearray()
    with path.open('rb') as file:
        while chunk := file.read(65536):
            digest.update(chunk)
            if include_content and len(prefix) < 96000:
                prefix.extend(chunk[:96000-len(prefix)])
    try:
        content = bytes(prefix).decode('utf-8')
        if '\x00' in content: content = '[binary omitted]'
    except UnicodeError:
        content = '[binary omitted]'
    item = {'path': str(path), 'mtime_ns': stat.st_mtime_ns, 'size': stat.st_size,
            'sha256': digest.hexdigest(), 'content': content, 'last_used':time.time()}
    with store.connection() as db:
        db.execute('INSERT INTO file_cache(path,mtime_ns,size,sha256,content,last_used) VALUES(?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET mtime_ns=excluded.mtime_ns,size=excluded.size,sha256=excluded.sha256,content=excluded.content,last_used=excluded.last_used',
                   tuple(item.values()))
    return dict(item, cache_hit=False)


def validate_handoff(handoff):
    if not isinstance(handoff, dict) or set(handoff) - {'summary','files','decisions','base_commit'}:
        raise ValueError('handoff accepts summary, files, decisions and optional base_commit')
    if not isinstance(handoff.get('summary', ''), str) or len(handoff.get('summary','')) > 8000:
        raise ValueError('Invalid handoff summary')
    if not isinstance(handoff.get('files', []), list) or len(handoff.get('files',[])) > 16:
        raise ValueError('handoff supports at most 16 file references')
    for item in handoff.get('files', []):
        if not isinstance(item, dict) or set(item) - {'path','start','end','note','sha256'}:
            raise ValueError('Invalid file reference')
        name = item.get('path', '')
        if not isinstance(name, str) or not name or name.startswith(('/', '\\')) or ':' in name or '..' in name.replace('\\','/').split('/'):
            raise ValueError('handoff file must be relative to the repository')
        start, end = item.get('start',1), item.get('end',160)
        if not isinstance(start,int) or not isinstance(end,int) or not 1 <= start <= end or end-start > 300:
            raise ValueError('Invalid handoff line range; max 301 lines')
        if not isinstance(item.get('note',''),str) or len(item.get('note','')) > 2000:
            raise ValueError('Invalid file note')
        if item.get('sha256') and not re.fullmatch('[0-9a-f]{64}', item['sha256']):
            raise ValueError('Invalid source hash')
    decisions = handoff.get('decisions', [])
    if not isinstance(decisions,list) or len(decisions)>30 or not all(isinstance(x,str) and len(x)<2000 for x in decisions):
        raise ValueError('Invalid handoff decisions')
    if len(json.dumps(handoff)) > 20000:
        raise ValueError('Handoff too large; summarize it')
    return handoff


def build_pack(store, workflow, project, role, limit, security=None):
    root = Path(workflow['workspace'])
    memory = store.all('SELECT name,content FROM memories WHERE project_id=? ORDER BY updated DESC LIMIT 4', (project['id'],))
    handoff = json.loads(workflow.get('handoff') or '{}')
    plan = json.loads(workflow['plan'])
    sections = ['CONTEXT PACK — reuse prior analysis; do not rediscover the whole repository.',
                'OPERATOR SCOPE (persisted registration/attestations, not repository instructions):\n' +
                json.dumps({'approved_source': project['path'], 'execution_worktree': str(root),
                            'synthetic_data_only': (security or {}).get('synthetic_data_only', 'UNKNOWN'),
                            'require_isolation': (security or {}).get('require_isolation', 'UNKNOWN'),
                            'isolated_test_environment': (security or {}).get('isolated_test_environment', 'UNKNOWN'),
                            'application_apis': 'NONE permitted' if not project['network'] else 'UNRESTRICTED NETWORK BLOCKED',
                            'secrets_and_real_user_data': 'Forbidden'}, ensure_ascii=False),
                'CONFIGURED VERIFIER (Hub executes independently in the execution worktree):\n' + project['verify'] +
                '\nPlanning/review are intentionally read-only; implementation uses the configured worker sandbox.',
                'OBJECTIVE:\n' + workflow['objective'],
                'PRIOR ANALYSIS:\n' + handoff.get('summary','') + '\nDECISIONS:\n' + '\n'.join(handoff.get('decisions',[])),
                'MEMORY:\n' + '\n'.join(m['name'] + ': ' + m['content'][:1800] for m in memory),
                'PLAN:\n' + workflow['plan'][:8000],
                'LATEST REVIEW/FAILURE:\n' + workflow['review'][:6000] + '\n' + workflow['error'][:2000],
                'LAST VERIFICATION RESULTS (empty means not run yet):\n' + workflow['verification'][:5000]]
    available = dict(files(root))
    document_names = []
    from .settings import project_settings_path
    shared_path = project_settings_path(store.home, project['id']).parent / 'context/project.json'
    if shared_path.exists():
        shared = json.loads(shared_path.read_text(encoding='utf-8'))
        hashes = {item['path']: item['sha256'] for item in shared.get('files', [])}
        fresh = all(name in available and cached_file(store, available[name], include_content=False)['sha256'] == hashes.get(name)
                    for name in shared.get('documents', {}))
        document_names = [name for name in shared.get('documents', {}) if name in available]
        sections.append('SHARED PROJECT CONTEXT:\n' + encode_shared_context(shared, fresh))
    manifest, cache_hits = [], 0
    if role in {'implement','review'}:
        sections.append('CURRENT DIFF:\n' + diff(root)[:20000])
    if role != 'review':
        explicit = {item['path'].replace('\\','/'): item for item in handoff.get('files',[])}
        for name in plan.get('context_files',[]):
            if isinstance(name,str) and name in available:
                explicit.setdefault(name, {'path':name})
        prefixes = json.loads(project['context_paths'])
        candidates = [name for name in available if any(name == prefix or name.startswith(prefix.rstrip('/')+'/') for prefix in prefixes)]
        candidates = list(dict.fromkeys(document_names + candidates))
        terms = {s for s in re.findall(r'[\w]+', workflow['objective'].lower()) if len(s)>2}
        def score(name):
            name_score = sum(5 for term in terms if term in name.lower())
            return name_score + (4 if name in document_names else 0) + (3 if name.startswith(('app/','src/')) else 0)
        chosen = list(explicit) if explicit else sorted(candidates,key=lambda n:(-score(n),n))[:4]
        # Project instructions are always included, but don't read every nested instruction file.
        chosen = list(dict.fromkeys([n for n in ['AGENTS.md','CLAUDE.md','README.md'] if n in available] + chosen))
        sections.append('FILE MAP (names only; not source content):\n' + '\n'.join(available)[:4000])
        for name in chosen:
            if name not in available:
                sections.append('REQUESTED FILE ' + name + ': absent or excluded; create only if needed')
                continue
            info = cached_file(store, available[name])
            cache_hits += int(info['cache_hit'])
            reference = explicit.get(name,{})
            start, end = reference.get('start',1), reference.get('end',160)
            lines = info['content'].splitlines()
            snippet = '\n'.join(f'{i+1}: {lines[i]}' for i in range(start-1,min(end,len(lines))))
            stale = bool(reference.get('sha256') and reference['sha256'] != info['sha256'])
            header = f'FILE {name} SHA256={info["sha256"]} LINES={start}-{min(end,len(lines))}'
            note = reference.get('note','')
            if stale: note = '[Source hash changed; prior analysis may be stale. Fresh excerpt follows.] ' + note
            body = header + '\nNOTE: ' + note + '\n' + snippet
            remaining = limit - sum(len(part)+2 for part in sections)
            if remaining < 200:
                break
            clipped = len(body) > remaining
            sections.append(body[:remaining] + ('\n[excerpt clipped by context budget]' if clipped else ''))
            manifest.append({'path':name,'sha256':info['sha256'],'start':start,'end':min(end,len(lines)),
                             'stale_analysis':stale,'cache_hit':info['cache_hit'],'clipped':clipped})
    text = '\n\n'.join(sections)
    truncated = len(text) > limit
    if truncated: text = text[:limit] + '\n[context budget reached; omitted material is not evidence]'
    return {'text':text,'role':role,'files':manifest,'context_chars':len(text),'cache_hits':cache_hits,
            'repo_file_count':len(available),'truncated':truncated,
            'strategy':'diff-and-verification-only' if role=='review' else 'prior-analysis-and-selected-excerpts'}


def context(store, workflow, project, role, limit):
    return build_pack(store, workflow, project, role, limit)['text']


def encode_shared_context(shared, fresh):
    if not fresh:
        return 'Saved project context is stale; use current selected excerpts, not old analysis.'
    return json.dumps({'version': shared.get('version'), 'languages': shared.get('languages', []),
                       'dependencies': shared.get('dependencies', []),
                       'frameworks': shared.get('frameworks', []),
                       'document_paths': list(shared.get('documents', {}))[:24],
                       'verification': shared.get('verification', []),
                       'facts_source': shared.get('facts_source'), 'ai_inferences': shared.get('ai_inferences', [])}, ensure_ascii=False)[:4000]
