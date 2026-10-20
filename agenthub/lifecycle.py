"""Explicit per-user installation ownership; updates and migration never discard data."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing

from .settings import atomic_json


def path_entries(value):
    result, seen = [], set()
    for item in value.split(';'):
        if not item.strip():
            continue
        key = os.path.normcase(os.path.normpath(item.rstrip('\\/')))
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result


def user_path(value=None):
    if os.name != 'nt':
        raise ValueError('Use the ma shell launcher or your shell PATH on non-Windows hosts')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
        try:
            previous, kind = winreg.QueryValueEx(key, 'Path')
        except FileNotFoundError:
            previous, kind = '', winreg.REG_EXPAND_SZ
        if value is not None:
            winreg.SetValueEx(key, 'Path', 0, kind, value)
            import ctypes
            # Notify future terminals without changing system PATH.
            ctypes.windll.user32.SendMessageTimeoutW(0xffff, 0x001A, 0, 'Environment', 2, 1000, None)
        return previous


def install_command(home, get_path=None, set_path=None, which=None):
    home = Path(home).resolve()
    root = Path(__file__).resolve().parents[1]
    target = home / 'runtime/bin/ma.cmd'
    if '%' in str(root) + sys.executable + str(home):
        raise ValueError('CMD launcher paths cannot contain percent signs')
    which = which or shutil.which
    collision = which('ma')
    if collision and Path(collision).resolve() != target:
        raise ValueError('ma already exists at ' + str(collision) + '; no command was overwritten')
    body = '@echo off\r\n"' + sys.executable + '" "' + str(root / 'ma.py') + '" --home "' + str(home) + '" %*\r\nexit /b %errorlevel%\r\n'
    if target.is_symlink() or (target.exists() and target.read_bytes() != body.encode('utf-8')):
        raise ValueError('Unrecognized existing launcher; not overwritten')
    old = (get_path or user_path)()
    entries = path_entries(old)
    binpath = str(target.parent)
    added = os.path.normcase(os.path.normpath(binpath)) not in {os.path.normcase(os.path.normpath(p.rstrip('\\/'))) for p in entries}
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    record = home / 'runtime/installation.json'
    prior_ownership = json.loads(record.read_text(encoding='utf-8')) if record.exists() else {}
    try:
        target.write_bytes(body.encode('utf-8'))
        if added:
            (set_path or user_path)(';'.join(entries + [binpath]))
        atomic_json(record, {'launcher': str(target),
                    'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'path_added': added or prior_ownership.get('path_added', False),
                    'bin': binpath, 'source': str(root)})
    except BaseException:
        if added:
            (set_path or user_path)(old)
        if not existed:
            target.unlink(missing_ok=True)
        raise
    return {'installed': str(target), 'user_path_added': added, 'note': 'Open a new terminal. Existing hub commands remain unchanged.'}


def uninstall(home, get_path=None, set_path=None):
    home = Path(home).resolve()
    record = home / 'runtime/installation.json'
    if not record.exists():
        return {'status': 'no owned launcher found', 'data_retained': True}
    owned = json.loads(record.read_text(encoding='utf-8'))
    target = Path(owned['launcher'])
    if target.resolve() != home / 'runtime/bin/ma.cmd' or target.is_symlink():
        raise ValueError('Invalid installation ownership')
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != owned['sha256']:
        raise ValueError('Launcher changed; not removed')
    if owned['path_added']:
        entries = path_entries((get_path or user_path)())
        keep = [p for p in entries if os.path.normcase(os.path.normpath(p.rstrip('\\/'))) != os.path.normcase(os.path.normpath(owned['bin']))]
        (set_path or user_path)(';'.join(keep))
    target.unlink(missing_ok=True)
    record.unlink()
    return {'status': 'owned launcher/PATH entry removed', 'data_retained': True,
            'note': 'No project, workflow, provider, startup task or client configuration deleted'}


def update_source(root, apply=False, run=subprocess.run):
    def git(*args):
        result = run(['git', '-C', str(root), *args], capture_output=True, encoding='utf-8', timeout=60)
        if result.returncode:
            raise ValueError('Update Git command failed; working files and settings retained')
        return result.stdout.strip()
    if git('status', '--porcelain'):
        raise ValueError('Source has local changes; update refused without reset/stash')
    if not apply:
        return {'status': 'clean source; run ma update --apply to fetch and fast-forward explicitly'}
    git('pull', '--ff-only')
    return {'status': 'fast-forward update completed', 'config_retained': True}


def migrate_legacy(source, destination):
    """Copy, never move. Reject live/owned-worktree state rather than break its paths."""
    from .platforms import FileLock
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Migration paths must be disjoint')
    if not (source / 'hub.sqlite3').is_file():
        raise ValueError('Legacy Hub database not found; source not modified')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Migration destination must be empty; existing data is never overwritten')
    with FileLock(source / 'daemon.lock'):
        names = ('config.json', 'deliverables', 'projects', 'runs', 'agent-registry.json')
        for name in names:
            path = source / name
            if path.is_symlink() or (path.is_dir() and any(p.is_symlink() for p in path.rglob('*'))):
                raise ValueError('Migration refuses symlinks; source and destination unchanged')
        database = source / 'hub.sqlite3'
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute("SELECT 1 FROM workflows WHERE status IN ('queued','running','waiting','recovering') LIMIT 1").fetchone():
                raise ValueError('Finish/cancel active workflows before migration')
            if any(Path(r[0]).exists() for r in db.execute('SELECT workspace FROM workflows WHERE workspace IS NOT NULL')):
                raise ValueError('Existing worktrees require explicit handoff; migration refused')
            staging = destination.with_name(destination.name + '.migration-' + uuid.uuid4().hex)
            staging.mkdir(parents=True)
            with closing(sqlite3.connect(staging / 'hub.sqlite3')) as output:
                db.backup(output)
        for name in names:
            path = source / name
            if not path.exists():
                continue
            if path.is_dir():
                shutil.copytree(path, staging / name)
            else:
                shutil.copy2(path, staging / name)
        with closing(sqlite3.connect(staging / 'hub.sqlite3')) as copied:
            for workflow_id, delivery in copied.execute('SELECT id,delivery FROM workflows WHERE delivery IS NOT NULL').fetchall():
                old_path = Path(delivery)
                if old_path.parent == source / 'deliverables' and (staging / 'deliverables' / old_path.name).is_file():
                    copied.execute('UPDATE workflows SET delivery=? WHERE id=?', (str(destination / 'deliverables' / old_path.name), workflow_id))
            copied.commit()
        # Only an explicitly named empty destination is replaced. Source is untouched.
        if destination.exists(): destination.rmdir()
        staging.replace(destination)
    return {'copied_to': str(destination), 'source_retained': True,
            'note': 'Original data is the backup. Historical artifact paths are retained; no live worktrees migrated.'}
