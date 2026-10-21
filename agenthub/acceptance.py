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


def target_path(root, name):
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
    return target


def load_changes(store, flow):
    if flow['status'] != 'completed' or not flow.get('delivery'):
        raise ValueError('Only completed, verified changes can be accepted')
    root = Path(store.project(flow['project_id'])['path'])
    payload, modes = {}, {}
    with zipfile.ZipFile(flow['delivery']) as archive:
        if archive.testzip():
            raise ValueError('Saved changes failed checksum verification')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest['workflow_id'] != flow['id'] or manifest['base_commit'] != flow['base_commit']:
            raise ValueError('Saved changes do not match workflow')
        for item in manifest['changed_files']:
            name = item['path']
            target_path(root, name)  # Validate before any payload/base-file access.
            if name in payload:
                raise ValueError('Conflicting saved file entries')
            data = archive.read('files/' + name)
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('Saved file hash mismatch')
            payload[name] = data
            if 'mode' in item:
                if type(item['mode']) is not int or not 0 <= item['mode'] <= 0o777:
                    raise ValueError('Invalid saved file permissions')
                modes[name] = item['mode']
        for name in manifest['deleted_files']:
            target_path(root, name)
            if name in payload:
                raise ValueError('Conflicting saved file entries')
            payload[name] = None
    return root, payload, modes


def preview(store, workflow_id):
    """Read-only diff material from verified delivery + base Git objects, never the source tree."""
    import subprocess
    flow = store.workflow(workflow_id)
    root, payload, _ = load_changes(store, flow)
    accepted = set(state(store, workflow_id).get('files', []))
    files, total = [], 0
    for name, after in payload.items():
        # Check existence through Git's tree so a missing base is not confused with deletion.
        exists = ws.git(root, 'ls-tree', '--name-only', flow['base_commit'], '--', name)
        before = b''
        if exists:
            result = subprocess.run(['git', '-C', str(root), 'show', flow['base_commit'] + ':' + name],
                                    capture_output=True, timeout=30)
            if result.returncode:
                raise ValueError('Cannot read saved baseline; no preview available')
            before = result.stdout
        pair, binary = [], False
        for data in (before, after or b''):
            if len(data) > 512 * 1024:
                pair.append('[Large file: text preview omitted]')
                binary = True
                continue
            try:
                text = data.decode('utf-8')
                if '\0' in text:
                    raise UnicodeError()
                pair.append(text)
            except UnicodeError:
                binary = True
                pair.append('[Binary file: text preview unavailable]')
        total += sum(len(text) for text in pair)
        if total > 2 * 1024 * 1024:
            raise ValueError('Review exceeds preview capacity; inspect a smaller delivery')
        files.append({'path': name, 'before': pair[0], 'after': pair[1], 'binary': binary,
                      'kind': 'deleted' if after is None else 'modified' if exists else 'added',
                      'accepted': name in accepted})
    return {'workflow_id': workflow_id, 'project_id': flow['project_id'], 'project_path': str(root),
            'base_commit': flow['base_commit'], 'files': files, 'acceptance': state(store, workflow_id)}


def accept(store, workflow_id, automatic=False, files=None):
    import os
    if os.environ.get('MULTI_AGENTS_WORKER'):
        raise ValueError('Workers cannot accept their own changes')
    if files is not None and (not isinstance(files, list) or not files or not all(isinstance(x, str) for x in files)):
        raise ValueError('Choose at least one delivery file')
    flow = store.workflow(workflow_id)
    project = store.project(flow['project_id'])
    with FileLock(store.home / 'acceptance.lock'):
        saved = state(store, workflow_id)
        if saved['status'] == 'accepted':
            if files and not set(files).issubset(saved.get('files', [])):
                raise ValueError('Requested file is not part of this delivery')
            return saved
        if saved['status'] == 'applying':
            raise ValueError('Interrupted apply: inspect saved checkpoint before continuing')
        if automatic and not mode(store, project['id'])['auto_accept']:
            raise ValueError('Auto accept is disabled for this project')
        root, payload, modes = load_changes(store, flow)
        selected = set(payload) if files is None else set(files)
        if not selected.issubset(payload):
            raise ValueError('Requested file is not part of this delivery')
        prior = set(saved.get('files', [])) if saved['status'] == 'partial' else set()
        if not prior.issubset(payload) or ws.git(root, 'rev-parse', 'HEAD') != flow['base_commit']:
            raise ValueError('Project changed since the task started; changes were not applied')
        changed = set(ws.git(root, 'diff', '--name-only', '--no-renames', 'HEAD').splitlines())
        changed.update(ws.git(root, 'ls-files', '--others', '--exclude-standard').splitlines())
        if changed - prior:
            raise ValueError('Project changed since the task started; changes were not applied')
        for name in prior:
            target = target_path(root, name)
            if (target.read_bytes() if target.is_file() else None) != payload[name]:
                raise ValueError('Previously accepted file was edited; preserve user changes')
        pending = {name: data for name, data in payload.items() if name in selected - prior}
        if not pending and prior:
            return saved
        backups, old_modes = {}, {}
        for name in pending:
            target = target_path(root, name)
            if target.exists() and not ws.git(root, 'ls-files', '--error-unmatch', '--', name, check=False):
                raise ValueError('Existing untracked or ignored file would be overwritten')
            if target.exists() and not target.is_file():
                raise ValueError('File conflicts with directory')
            backups[name] = target.read_bytes() if target.exists() else None
            old_modes[name] = target.stat().st_mode & 0o777 if target.exists() else None
        journal = store.home / 'acceptance' / (flow['id'] + '.json')
        atomic_json(journal, {'status': 'applying', 'files': sorted(prior), 'pending_files': list(pending),
                             'automatic': automatic, 'previous_state': saved})
        created, written = [], []
        try:
            for name, data in pending.items():
                target = target_path(root, name)
                if (target.read_bytes() if target.exists() else None) != backups[name]:
                    raise ValueError('Concurrent source edit; changes were not applied')
                written.append(name)
                if data is None:
                    target.unlink(missing_ok=True)
                else:
                    missing, parent = [], target.parent
                    while not parent.exists():
                        missing.append(parent)
                        parent = parent.parent
                    target.parent.mkdir(parents=True, exist_ok=True)
                    created.extend(reversed(missing))
                    target.write_bytes(data)
                    if name in modes:
                        target.chmod(modes[name])
        except Exception:
            for name in written:
                target, data = root / name, backups[name]
                if data is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(data)
                    target.chmod(old_modes[name])
            for folder in reversed(created):
                try:
                    folder.rmdir()
                except OSError:
                    pass
            atomic_json(journal, saved)
            raise
        accepted = prior | selected
        result = {'status': 'accepted' if accepted == set(payload) else 'partial', 'workflow_id': flow['id'],
                  'files': sorted(accepted), 'remaining_files': sorted(set(payload) - accepted), 'automatic': automatic}
        atomic_json(journal, result)
        store.event(flow['id'], 'changes_accepted', result)
        return result
