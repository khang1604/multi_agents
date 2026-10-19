"""Identify only the current Git root and tracked filenames; never read file bodies."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def repository_root(cwd):
    result = subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--show-toplevel'],
                            capture_output=True, encoding='utf-8', errors='replace', timeout=20)
    if result.returncode:
        raise ValueError('Not inside a Git project. Enter its folder first; Hub will not run git init automatically.')
    return Path(result.stdout.strip()).resolve()


def detect_checks(root):
    result = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(root), 'ls-files', '-z'],
                            capture_output=True, encoding='utf-8', errors='replace', timeout=20, check=True)
    files = set(result.stdout.split('\0')) - {''}
    candidates = []
    if 'pytest.ini' in files or 'conftest.py' in files or 'tests/conftest.py' in files:
        candidates.append(('pytest', [['{python}', '-m', 'pytest']]))
    elif any(p.startswith('tests/test') and p.endswith('.py') for p in files):
        candidates.append(('python-unittest (heuristic)', [['{python}', '-m', 'unittest', 'discover', '-s', 'tests', '-v']]))
    if 'go.mod' in files:
        candidates.append(('go', [['go', 'test', './...']]))
    if 'Cargo.toml' in files:
        candidates.append(('rust', [['cargo', 'test']]))
    if any('/' not in p and p.endswith(('.sln', '.slnx', '.csproj')) for p in files):
        candidates.append(('dotnet', [['dotnet', 'test']]))
    if 'package.json' in files:
        # package scripts may run arbitrary commands; require the operator to select them.
        candidates.append(('node (explicit --verify required)', None))
    if len(candidates) != 1 or candidates[0][1] is None:
        raise ValueError('Cannot safely choose a test command for this project. Pass --verify with JSON argument arrays (see README). No files were read or tests executed.')
    return candidates[0]


def identify(hub, cwd, name=None, verify=None):
    root = repository_root(cwd)
    for project in hub.store.all('SELECT * FROM projects'):
        if os.path.normcase(str(Path(project['path']).resolve())) == os.path.normcase(str(root)):
            if name and name != project['name']:
                raise ValueError('This folder is already registered as ' + project['name'])
            if verify is not None and verify != json.loads(project['verify']):
                raise ValueError('Existing test commands differ; here will not overwrite registered settings')
            return {'created': False, 'project': project, 'test_detection': 'existing registration',
                    'context': hub.recover(project['id']), 'ai_calls': 0}
    if verify is None:
        detected, verify = detect_checks(root)
    else:
        detected = 'explicit --verify; not executed'
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', root.name).strip('-')[:48] or 'project'
    key = os.path.normcase(str(root)).encode('utf-8')
    project = hub.store.add_project(name or slug + '-' + hashlib.sha256(key).hexdigest()[:8],
                                    root, verify, ['README.md', 'app', 'src', 'tests'])
    return {'created': True, 'project': project, 'test_detection': detected,
            'context': hub.recover(project['id']), 'ai_calls': 0,
            'note': 'Test command is a suggestion, not executed or validated. Review it before starting AI. Security flags unchanged.'}
