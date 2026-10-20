"""Apply reviewed file changes locally; no Git commit, merge or provider bypass."""
import hashlib
import json
from pathlib import Path
import zipfile

from .platforms import FileLock
from .settings import atomic_json, project_settings_path
from . import workspace as ws


def mode(store, project, enabled=None):
    import os
    if enabled is not None and os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot change acceptance preferences')
    row = store.project(project)
    path = project_settings_path(store.home, row['id']).parent / 'acceptance.json'
    if enabled is not None:
        if type(enabled) is not bool:
            raise ValueError('auto accept must be a boolean')
        atomic_json(path, {'auto_accept': enabled})
    return json.loads(path.read_text()) if path.exists() else {'auto_accept': False}


def state(store, workflow_id):
    path = store.home / 'acceptance' / (workflow_id + '.json')
    return json.loads(path.read_text()) if path.exists() else {'status': 'pending'}


def accept(store, workflow_id, automatic=False):
    import os
    if os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot accept their own changes')
    flow = store.workflow(workflow_id)
    project = store.project(flow['project_id'])
    root = Path(project['path'])
    with FileLock(store.home / 'acceptance.lock'):
        saved = state(store, workflow_id)
        if saved['status'] == 'accepted':
            return saved
        if saved['status'] == 'applying':
            raise ValueError('Interrupted apply: inspect saved checkpoint before continuing')
        if automatic and not mode(store, project['id'])['auto_accept']:
            raise ValueError('Auto accept is disabled for this project')
        if flow['status'] != 'completed' or not flow.get('delivery'):
            raise ValueError('Only completed, verified changes can be accepted')
        if ws.git(root, 'rev-parse', 'HEAD') != flow['base_commit'] or ws.git(root, 'status', '--porcelain'):
            raise ValueError('Project changed since the task started; changes were not applied')
        payload, modes = {}, {}
        with zipfile.ZipFile(flow['delivery']) as archive:
            if archive.testzip():
                raise ValueError('Saved changes failed checksum verification')
            manifest = json.loads(archive.read('manifest.json'))
            if manifest['workflow_id'] != flow['id'] or manifest['base_commit'] != flow['base_commit']:
                raise ValueError('Saved changes do not match workflow')
            for item in manifest['changed_files']:
                data = archive.read('files/' + item['path'])
                if hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError('Saved file hash mismatch')
                payload[item['path']] = data
                if 'mode' in item:
                    if type(item['mode']) is not int or not 0 <= item['mode'] <= 0o777:
                        raise ValueError('Invalid saved file permissions')
                    modes[item['path']] = item['mode']
            for name in manifest['deleted_files']:
                if name in payload: raise ValueError('Conflicting saved file entries')
                payload[name] = None
        backups, old_modes = {}, {}
        for name in payload:
            rel = Path(name)
            target = root / rel
            sensitive = (rel.suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.sqlite', '.sqlite3', '.db', '.dump', '.bak'}
                         or rel.name.lower() in {'appsettings.json', 'appsettings.development.json', 'auth.json', 'credentials.json', 'secrets.json'}
                         or rel.stem.lower() in {'secret', 'secrets', 'credentials', 'token', 'tokens'})
            if (sensitive or not name or '\\' in name or ':' in name or rel.is_absolute()
                    or '..' in rel.parts or any(p in ws.EXCLUDED or p.startswith('.env') for p in rel.parts)
                    or target.is_symlink() or not target.resolve().is_relative_to(root.resolve())
                    or any(parent.is_symlink() for parent in target.parents if parent != root)):
                raise ValueError('Unsafe changed file path')
            if target.exists() and not ws.git(root, 'ls-files', '--error-unmatch', '--', name, check=False):
                raise ValueError('Existing untracked or ignored file would be overwritten')
            if target.exists() and not target.is_file(): raise ValueError('File conflicts with directory')
            backups[name] = target.read_bytes() if target.exists() else None
            old_modes[name] = target.stat().st_mode & 0o777 if target.exists() else None
        journal = store.home / 'acceptance' / (flow['id'] + '.json')
        atomic_json(journal, {'status': 'applying', 'files': list(payload), 'automatic': automatic})
        created = []
        try:
            for name, data in payload.items():
                target = root / name
                if data is None:
                    target.unlink(missing_ok=True)
                else:
                    missing = []
                    parent = target.parent
                    while not parent.exists(): missing.append(parent); parent = parent.parent
                    target.parent.mkdir(parents=True, exist_ok=True)
                    created.extend(reversed(missing))
                    target.write_bytes(data)
                    if name in modes: target.chmod(modes[name])
        except Exception:
            for name, data in backups.items():
                target = root / name
                if data is None: target.unlink(missing_ok=True)
                else:
                    target.write_bytes(data)
                    target.chmod(old_modes[name])
            for folder in reversed(created):
                try: folder.rmdir()
                except OSError: pass
            atomic_json(journal, {'status': 'pending', 'error': 'Apply rolled back'})
            raise
        result = {'status': 'accepted', 'workflow_id': flow['id'], 'files': list(payload), 'automatic': automatic}
        atomic_json(journal, result)
        store.event(flow['id'], 'changes_accepted', result)
        return result
