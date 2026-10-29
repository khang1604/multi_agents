"""Conservative janitor: archive verified deliveries before retiring owned worktrees."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

from . import workspace as ws
from .store import encode

TEMP_PARTS = {'__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'node_modules', '.venv', 'venv', 'dist', 'build', 'coverage'}


def git_bytes(root, *args):
    """Read bounded binary Git output for an owned workflow archive."""
    result = subprocess.run(['git','-C',str(root),*args],capture_output=True,timeout=60)
    if result.returncode: raise ValueError(result.stderr.decode('utf-8',errors='replace'))
    return result.stdout


def git_names(root, *args):
    """Read Git path lists without losing filename boundaries."""
    return [value.decode('utf-8') for value in git_bytes(root,*args).split(b'\0') if value]


def owned_workspace(store, flow):
    """Validate that a worktree belongs to the expected Hub workflow."""
    if not flow.get('workspace'): return None
    root = store.home / 'workspaces'
    path = Path(flow['workspace'])
    if path.is_symlink() or path.resolve() != (root / flow['id']).resolve():
        raise ValueError('Refusing cleanup outside the exact managed worktree')
    return path


def archive_completed(store, flow, policy):
    """Verify completed code, export an integrity-checked delivery, then clean only its owned worktree."""
    if flow['status'] != 'completed': return {'skipped':'not completed'}
    path = owned_workspace(store,flow)
    if path is None or not path.exists(): return {'delivery':flow.get('delivery'),'retired':True}
    verification = json.loads(flow['verification'])
    before = ws.fingerprint(path,store)
    if verification.get('fingerprint_after') != before:
        return {'skipped':'Worktree changed after verification; code and logs retained'}
    ignored = git_names(path,'ls-files','--others','--ignored','--exclude-standard','-z')
    unexpected = [name for name in ignored if not any(p in TEMP_PARTS for p in Path(name).parts)
                  and not name.endswith(('.pyc','.pyo')) and Path(name).name not in {'.coverage'}]
    if unexpected:
        return {'skipped':'Unknown ignored files exist; preserve worktree: '+', '.join(unexpected[:5])}
    changed = sorted(set(git_names(path,'diff','--name-only','--no-renames','HEAD','-z') +
                         git_names(path,'ls-files','--others','--exclude-standard','-z')))
    entries, deleted = [], []
    total = 0
    for name in changed:
        candidate = path / name
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(path.resolve()):
            return {'skipped':'Changed symlink/out-of-tree path; preserve worktree'}
        if not candidate.exists():
            deleted.append(name)
        elif candidate.is_file():
            total += candidate.stat().st_size
            entries.append((name,candidate))
    if total > policy['max_delivery_bytes']:
        return {'skipped':'Delivery too large for automatic archive; worktree retained'}
    target = store.home / 'deliverables' / (flow['id']+'.zip')
    target.parent.mkdir(parents=True,exist_ok=True)
    temp = target.with_suffix('.zip.tmp')
    manifest = {'workflow_id':flow['id'],'base_commit':flow['base_commit'],'fingerprint':before,
                'deleted_files':deleted,'changed_files':[],'format':'changed-files-overlay-v1',
                'instruction':'Apply files/ over a checkout of base_commit and remove deleted_files. changes.patch covers tracked changes; files/ also includes untracked additions.'}
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for name,candidate in entries:
                archive.write(candidate,'files/'+name)
                manifest['changed_files'].append({'path':name,'sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),
                                                  'mode':candidate.stat().st_mode & 0o777})
            archive.writestr('changes.patch',git_bytes(path,'diff','--binary','--no-ext-diff','HEAD'))
            archive.writestr('workflow.json',json.dumps(flow,ensure_ascii=False,indent=2))
            archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            runs = store.home / 'runs' / flow['id']
            if runs.exists():
                for report in runs.glob('*/report.json'):
                    if report.stat().st_size < 2*1024*1024:
                        archive.write(report,'reports/'+report.parent.name+'.json')
        with zipfile.ZipFile(temp) as archive:
            if archive.testzip(): raise ValueError('Delivery ZIP checksum failed')
            for item in manifest['changed_files']:
                if hashlib.sha256(archive.read('files/'+item['path'])).hexdigest() != item['sha256']:
                    raise ValueError('Delivery file hash mismatch')
        if ws.fingerprint(path,store) != before:
            return {'skipped':'Worktree changed during export; preserved'}
        temp.replace(target)
        store.update(flow['id'],delivery=str(target))
        # Destructive action only after a verified, self-contained code delivery exists.
        project = store.project(flow['project_id'])
        ws.git(project['path'],'worktree','remove','--force',str(path))
        prefix = str(path.resolve())
        with store.connection() as db:
            db.execute('DELETE FROM file_cache WHERE path=? OR substr(path,1,?)=?',
                       (prefix,len(prefix+os.sep),prefix+os.sep))
        if runs.exists():
            shutil.rmtree(runs)
            runs.mkdir()
            (runs/'CLEANED.json').write_text(encode({'delivery':str(target),'cleaned_at':time.time()}),encoding='utf-8')
        store.event(flow['id'],'cleaned',{'delivery':str(target),'worktree_retired':True})
        return {'delivery':str(target),'retired':True}
    finally:
        temp.unlink(missing_ok=True)


def sweep(store, config):
    """Apply retention limits while preserving active work and unverified code."""
    policy = config['retention']
    if not policy.get('enabled'): return {'disabled':True}
    result = {'archived':[],'retained':[],'old_log_folders_removed':0,'cache_entries_evicted':0,'histories_compacted':0}
    if policy.get('archive_completed_worktrees'):
        for flow in store.all("SELECT * FROM workflows WHERE status='completed' ORDER BY updated"):
            try:
                action = archive_completed(store,flow,policy)
                if action.get('skipped'):
                    result['retained'].append({'workflow_id':flow['id'],**action})
                elif action.get('delivery'):
                    result['archived'].append({'workflow_id':flow['id'],**action})
            except (OSError,ValueError,subprocess.SubprocessError,zipfile.BadZipFile) as error:
                result['retained'].append({'workflow_id':flow['id'],'reason':str(error)})
    cutoff = time.time()-policy['failed_logs_days']*86400
    for flow in store.all("SELECT * FROM workflows WHERE status IN ('blocked','cancelled','needs_review') AND updated<?",(cutoff,)):
        folder = store.home/'runs'/flow['id']
        if folder.exists() and folder.resolve().parent == (store.home/'runs').resolve() and not folder.is_symlink():
            shutil.rmtree(folder)
            result['old_log_folders_removed'] += 1
    with store.connection() as db:
        total = db.execute('SELECT COALESCE(SUM(length(CAST(content AS BLOB))),0) FROM file_cache').fetchone()[0]
        rows = db.execute('SELECT path,length(CAST(content AS BLOB)) AS bytes FROM file_cache ORDER BY last_used').fetchall()
        remaining_count = len(rows)
        for row in rows:
            if total <= policy['cache_max_bytes'] and remaining_count <= policy.get('cache_max_entries',20000): break
            db.execute('DELETE FROM file_cache WHERE path=?',(row['path'],))
            total -= row['bytes']; remaining_count -= 1; result['cache_entries_evicted'] += 1
    history_cutoff = time.time()-policy.get('history_days',90)*86400
    for flow in store.all("SELECT * FROM workflows WHERE status='completed' AND delivery IS NOT NULL AND updated<? AND (plan!='{}' OR review!='{}' OR verification!='{}' OR EXISTS(SELECT 1 FROM attempts WHERE workflow_id=workflows.id))",(history_cutoff,)):
        delivery = Path(flow['delivery'])
        try:
            with zipfile.ZipFile(delivery) as archive:
                if archive.testzip(): continue
                archive.getinfo('workflow.json')
        except (OSError,zipfile.BadZipFile,KeyError):
            continue
        with store.connection() as db:
            db.execute('DELETE FROM attempts WHERE workflow_id=?',(flow['id'],))
            db.execute('DELETE FROM events WHERE workflow_id=?',(flow['id'],))
            db.execute("UPDATE workflows SET plan='{}',review='{}',handoff='{}',verification='{}' WHERE id=?",(flow['id'],))
        result['histories_compacted'] += 1
    if result['histories_compacted'] and not store.one("SELECT id FROM workflows WHERE status IN ('queued','running','waiting','recovering') LIMIT 1"):
        with store.connection() as db:
            db.execute('VACUUM')
    (store.home/'cleanup-last.json').write_text(encode(dict(result,at=time.time())),encoding='utf-8')
    return result
