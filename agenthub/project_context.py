"""Local, versioned context. Initialization never writes to the source repository."""
import hashlib
import json
import os
from pathlib import Path
import re
import tomllib

from .discovery import repository_root, detect_checks
from .settings import atomic_json, project_settings_path, ensure_idle
from .workspace import cached_file, files

MANIFESTS = {'package.json', 'pyproject.toml', 'requirements.txt', 'Cargo.toml', 'go.mod',
             'pom.xml', 'build.gradle', 'build.gradle.kts', 'global.json'}


def outside_repository(home, root):
    if Path(home).resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('ma data home must be outside the project repository')


def initialize(hub, cwd, name=None, verify=None):
    root = repository_root(cwd)
    outside_repository(hub.store.home, root)
    existing = next((p for p in hub.store.all('SELECT * FROM projects')
                     if os.path.normcase(str(Path(p['path']).resolve())) == os.path.normcase(str(root))), None)
    if existing and name and name != existing['name']:
        raise ValueError('Project already registered as ' + existing['name'])
    detection = 'explicit; not executed'
    if existing:
        if verify is not None and json.loads(existing['verify']) and verify != json.loads(existing['verify']):
            raise ValueError('Existing verification differs; initialization will not overwrite it')
        project = existing
        if verify is not None and not json.loads(existing['verify']):
            ensure_idle(hub.store)
            hub.store.add_project(existing['name'], root, verify, json.loads(existing['context_paths']))
            with hub.store.connection() as db:
                db.execute('UPDATE projects SET verify=? WHERE id=?', (json.dumps(verify), existing['id']))
            project = hub.store.project(existing['id'])
        removed = project_settings_path(hub.store.home, project['id']).parent / 'removed.json'
        if removed.exists():
            ensure_idle(hub.store)
            atomic_json(removed, {'removed': False})
    else:
        if verify is None:
            try:
                detection, verify = detect_checks(root)
                if detection == 'dotnet':
                    # dotnet test can exit successfully without finding a test project.
                    # Require actual test-project metadata, not just a solution filename.
                    test_project = any(p.suffix.lower() == '.csproj' and p.stat().st_size <= 65536
                                       and ('<IsTestProject>true</IsTestProject>' in p.read_text(encoding='utf-8', errors='replace')
                                            or 'Microsoft.NET.Test.Sdk' in p.read_text(encoding='utf-8', errors='replace'))
                                       for _, p in files(root))
                    if not test_project:
                        detection, verify = 'dotnet build/test commands require explicit --verify', []
            except ValueError:
                detection, verify = 'unknown; configure --verify before running a workflow', []
        key = hashlib.sha256(os.path.normcase(str(root)).encode('utf-8')).hexdigest()[:12]
        slug = re.sub(r'[^\w-]+', '-', root.name).strip('-')[:48] or 'project'
        project = hub.store.add_project(name or slug + '-' + key, root, verify,
                                       ['README.md', 'app', 'src', 'tests'], allow_unverified=True)
    return refresh(hub, project, detection)


def refresh(hub, project, detection='existing commands; not executed'):
    root = Path(project['path'])
    outside_repository(hub.store.home, root)
    manifest, excerpts, languages, dependencies, frameworks = [], {}, set(), [], set()
    mapping = {'.py': 'Python', '.cs': 'C#', '.js': 'JavaScript', '.ts': 'TypeScript',
               '.rs': 'Rust', '.go': 'Go', '.java': 'Java', '.cpp': 'C++'}
    for name, path in files(root):
        suffix = path.suffix.lower()
        if suffix in mapping:
            languages.add(mapping[suffix])
        info = cached_file(hub.store, path, include_content=False)
        manifest.append({'path': name, 'sha256': info['sha256']})
        allowed = name in {'README.md', 'AGENTS.md', 'CLAUDE.md'} or path.name in MANIFESTS or suffix == '.csproj'
        if allowed and len(excerpts) < 24 and path.stat().st_size <= 65536:
            text = path.read_text(encoding='utf-8', errors='replace')
            if re.search(r'-----BEGIN .*PRIVATE KEY-----|(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{16,}', text):
                raise ValueError('Potential secret in ' + name + '; context not exported')
            if path.name == 'package.json':
                try:
                    data = json.loads(text)
                    dependencies += sorted(set(data.get('dependencies', {})) | set(data.get('devDependencies', {})))
                    frameworks.update(n for n in ('react', 'next', 'vue', 'angular', 'express') if n in dependencies)
                except (ValueError, TypeError):
                    pass
            if path.name in {'pyproject.toml', 'Cargo.toml'}:
                try:
                    metadata = tomllib.loads(text)
                    if path.name == 'pyproject.toml':
                        dependencies += [d for d in metadata.get('project', {}).get('dependencies', []) if isinstance(d, str)]
                    else:
                        dependencies += list(metadata.get('dependencies', {}))
                except (ValueError, TypeError):
                    pass
            if suffix == '.csproj':
                dependencies += re.findall(r'PackageReference\s+Include="([^"]+)"', text)
                frameworks.update(re.findall(r'<TargetFrameworks?>([^<]+)</TargetFrameworks?>', text))
                if '<UseWindowsForms>true</UseWindowsForms>' in text:
                    frameworks.add('Windows Forms')
            excerpts[name] = text[:4000]
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    folder = project_settings_path(hub.store.home, project['id']).parent
    target = folder / 'context' / 'project.json'
    previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    changed = previous.get('fingerprint') != digest
    value = {'project_id': project['id'], 'root': str(root), 'version': previous.get('version', 0) + int(changed),
             'fingerprint': digest, 'files': manifest, 'languages': sorted(languages),
             'dependencies': sorted(set(dependencies)), 'documents': excerpts,
             'frameworks': sorted(frameworks),
             'verification': json.loads(project['verify']), 'command_detection': detection,
             'facts_source': 'local source/file hashes; commands are suggestions, not executed',
             'ai_inferences': [], 'enabled_agents_scope': str(folder / 'settings.json')}
    if changed:
        atomic_json(target, value)
    elif previous:
        value = previous
    return {'project': project, 'context': value, 'context_changed': changed,
            'verification_configured': bool(json.loads(project['verify'])), 'ai_calls': 0}


def get_context(hub, project):
    row = hub.store.project(project)
    path = project_settings_path(hub.store.home, row['id']).parent / 'context/project.json'
    if not path.exists():
        raise ValueError('Run ma init for this registered project first')
    value = json.loads(path.read_text(encoding='utf-8'))
    actual = [{'path': n, 'sha256': cached_file(hub.store, p, include_content=False)['sha256']}
              for n, p in files(row['path'])]
    value['stale'] = value['fingerprint'] != hashlib.sha256(json.dumps(actual, sort_keys=True).encode()).hexdigest()
    return value


def unregister(hub, project):
    ensure_idle(hub.store)
    row = hub.store.project(project)
    path = project_settings_path(hub.store.home, row['id']).parent / 'removed.json'
    atomic_json(path, {'removed': True})
    return {'removed': row['name'], 'source_deleted': False, 'history_retained': True}


def is_removed(home, project_id):
    path = project_settings_path(home, project_id).parent / 'removed.json'
    return path.exists() and json.loads(path.read_text(encoding='utf-8')).get('removed') is True
