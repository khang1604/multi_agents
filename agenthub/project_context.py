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
from .platforms import FileLock

MANIFESTS = {'package.json', 'pyproject.toml', 'requirements.txt', 'Cargo.toml', 'go.mod',
             'pom.xml', 'build.gradle', 'build.gradle.kts', 'global.json'}


def outside_repository(home, root):
    """Require application metadata to remain outside registered source repositories."""
    if Path(home).resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('ma data home must be outside the project repository')


def validate_wrappers(root, commands):
    """Check only named Gradle paths; never launch a build during initialization."""
    for command in commands:
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command):
            raise ValueError('verify must contain executable argument arrays')
        position = 0
        if Path(command[0]).name.lower() in {'cmd', 'cmd.exe'} and '/c' in command:
            position = command.index('/c') + 1
            if position < len(command) and command[position].lower() == 'call':
                position += 1
        if position >= len(command):
            continue
        wrapper = command[position].replace('\\', '/')
        if Path(wrapper).name not in {'gradlew', 'gradlew.bat'}:
            continue
        target = (root / wrapper).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError('Gradle wrapper not found inside project: ' + wrapper + '; correct the path with ma init --replace-verify --verify-command ...')
        for flag in ('-p', '--project-dir'):
            if flag in command:
                index = command.index(flag) + 1
                folder = (root / command[index].replace('\\', '/')).resolve() if index < len(command) else None
                if folder is None or not folder.is_relative_to(root) or not folder.is_dir():
                    raise ValueError('Gradle project directory is missing or outside the repository')


def initialize(hub, cwd, name=None, verify=None, replace_verify=False):
    """Register or refresh approved project metadata without writing into its source."""
    root = repository_root(cwd)
    outside_repository(hub.store.home, root)
    existing = next((p for p in hub.store.all('SELECT * FROM projects')
                     if os.path.normcase(str(Path(p['path']).resolve())) == os.path.normcase(str(root))), None)
    if existing and name and name != existing['name']:
        raise ValueError('Project already registered as ' + existing['name'])
    detection = 'explicit; not executed'
    if verify is None and (not existing or not json.loads(existing['verify']) or replace_verify):
        try:
            detection, verify = detect_checks(root, include_untracked=True)
            if detection == 'dotnet':
                test_project = any(p.suffix.lower() == '.csproj' and p.stat().st_size <= 65536
                                   and ('<IsTestProject>true</IsTestProject>' in p.read_text(encoding='utf-8', errors='replace')
                                        or 'Microsoft.NET.Test.Sdk' in p.read_text(encoding='utf-8', errors='replace'))
                                   for _, p in files(root))
                if not test_project:
                    detection, verify = 'dotnet build/test commands require explicit --verify-command', []
        except ValueError as error:
            detection, verify = str(error), []
        if replace_verify and not verify:
            raise ValueError(detection + '; existing verification was preserved')
    if verify is not None:
        validate_wrappers(root, verify)
    if existing:
        if verify is not None and json.loads(existing['verify']) and verify != json.loads(existing['verify']) and not replace_verify:
            raise ValueError('Existing verification differs; use --replace-verify with the intended command')
        project = existing
        if verify and verify != json.loads(existing['verify']):
            # Validate first; add_project preserves the existing registration.
            hub.store.add_project(existing['name'], root, verify, json.loads(existing['context_paths']))
            with FileLock(hub.store.home / 'settings.lock'), hub.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute("SELECT id FROM workflows WHERE status IN ('queued','running','waiting','recovering') LIMIT 1").fetchone():
                    raise ValueError('Verification cannot change while a workflow is active')
                current = db.execute('SELECT verify FROM projects WHERE id=?', (existing['id'],)).fetchone()[0]
                if current != existing['verify']:
                    raise ValueError('Verification changed concurrently; initialize again')
                if json.loads(current):
                    folder = project_settings_path(hub.store.home, existing['id']).parent
                    atomic_json(folder / 'verification-previous.json', {'commands': json.loads(current)})
                db.execute('UPDATE projects SET verify=? WHERE id=?', (json.dumps(verify), existing['id']))
            project = hub.store.project(existing['id'])
        removed = project_settings_path(hub.store.home, project['id']).parent / 'removed.json'
        if removed.exists():
            ensure_idle(hub.store)
            atomic_json(removed, {'removed': False})
    else:
        key = hashlib.sha256(os.path.normcase(str(root)).encode('utf-8')).hexdigest()[:12]
        slug = re.sub(r'[^\w-]+', '-', root.name).strip('-')[:48] or 'project'
        project = hub.store.add_project(name or slug + '-' + key, root, verify,
                                       ['README.md', 'app', 'src', 'tests'], allow_unverified=True)
    validate_wrappers(root, json.loads(project['verify']))
    return refresh(hub, project, detection)


def refresh(hub, project, detection='existing commands; not executed'):
    """Update versioned project context and hashes from approved source."""
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
    changed = previous.get('fingerprint') != digest or previous.get('verification') != json.loads(project['verify'])
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
            'verification_configured': bool(json.loads(project['verify'])),
            'verification_executed': False, 'verification_command': json.loads(project['verify']),
            'verification_hint': detection, 'ai_calls': 0}


def get_context(hub, project):
    """Read saved context and report whether source evidence is stale."""
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
    """Mark a project removed while retaining source and historical workflow data."""
    ensure_idle(hub.store)
    row = hub.store.project(project)
    path = project_settings_path(hub.store.home, row['id']).parent / 'removed.json'
    atomic_json(path, {'removed': True})
    return {'removed': row['name'], 'source_deleted': False, 'history_retained': True}


def is_removed(home, project_id):
    """Check the external project-removal marker."""
    path = project_settings_path(home, project_id).parent / 'removed.json'
    return path.exists() and json.loads(path.read_text(encoding='utf-8')).get('removed') is True
