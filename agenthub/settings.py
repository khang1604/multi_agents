"""Bounded local settings, atomic writes, backups and project overlays."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import uuid

from .platforms import FileLock


def application_home():
    """Resolve the external per-user V2 application home."""
    if os.environ.get('AGENT_HUB_HOME'):
        return Path(os.environ['AGENT_HUB_HOME']).expanduser().resolve()
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return (base / 'MultiAgents').resolve()


def atomic_json(path, value, backup=True):
    """Write JSON atomically with optional backups and symlink protection."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Refusing a symlink settings file')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    previous = None
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if path.exists() and backup:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            previous = path.with_name(path.name + '.backup-' + stamp)
            shutil.copy2(path, previous)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return str(previous) if previous else None


def ensure_idle(store):
    """Reject global configuration/auth changes while a workflow is active."""
    if store.one("SELECT id FROM workflows WHERE status IN ('queued','running','waiting','recovering') LIMIT 1"):
        raise ValueError('Configuration is locked while a workflow is active; stop or finish it first')


def project_settings_path(home, project_id):
    """Resolve an external project-settings path without allowing traversal."""
    if not project_id or not all(c.isalnum() or c in '-_' for c in project_id):
        raise ValueError('Invalid local project id')
    root = Path(home).resolve()
    target = root / 'projects' / project_id / 'settings.json'
    if not target.resolve().is_relative_to(root):
        raise ValueError('Project metadata path escapes the local home')
    return target


def effective_config(config, home, project_id):
    """Merge validated project overrides while preserving global security and disabled providers."""
    result = deepcopy(config)
    path = project_settings_path(home, project_id)
    if path.exists():
        value = json.loads(path.read_text(encoding='utf-8'))
        for name, entry in value.get('providers', {}).items():
            if name not in result['providers']:
                raise ValueError('Unknown project provider: ' + name)
            if set(entry) - {'enabled', 'roles', 'model_policy', 'model', 'model_catalog', 'model_fallback'}:
                raise ValueError('Project settings cannot override commands or security')
            globally_enabled = result['providers'][name].get('enabled', False)
            result['providers'][name].update(entry)
            result['providers'][name]['enabled'] = globally_enabled and entry.get('enabled', globally_enabled)
            from .registry import validate_entry
            validate_entry(name, result['providers'][name])
    scope_path = path.parent / 'scope.json'
    if scope_path.exists():
        scope = json.loads(scope_path.read_text(encoding='utf-8'))
        # Only an explicit operator attestation for this exact registration can
        # grant synthetic data scope; isolation policy and network stay intact.
        from .store import Store
        project = Store(home).project(project_id)
        if (scope.get('source') != project['path'] or scope.get('confirmation_source') != 'operator'
                or scope.get('synthetic_data_only') is not True or scope.get('application_apis') != []):
            raise ValueError('Invalid project scope; initialize interactively again')
        result['security']['synthetic_data_only'] = True
    from .readiness import execution_environment
    result['_execution_environment'] = execution_environment(home, project_id)
    return result


def update_provider(hub, name, changes, project=None):
    """Apply validated provider/model changes under the settings lock with backups."""
    from .registry import validate_entry
    if name not in hub.config['providers']:
        raise ValueError('Unknown agent: ' + name)
    allowed = {'enabled', 'roles', 'model_policy', 'model', 'model_catalog', 'model_fallback'}
    if set(changes) - allowed:
        raise ValueError('Unsupported agent setting')
    with FileLock(hub.store.home / 'settings.lock'):
        ensure_idle(hub.store)
        if project:
            row = hub.store.project(project)
            path = project_settings_path(hub.store.home, row['id'])
            value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'providers': {}}
            target = value['providers'].setdefault(name, {})
            entry = {**hub.config['providers'][name], **target, **changes}
            validate_entry(name, entry)
            target.update(changes)
        else:
            path = hub.store.home / 'config.json'
            # Read the current on-disk config inside the lock, not a stale Hub object.
            value = json.loads(path.read_text(encoding='utf-8'))
            entry = {**value['providers'][name], **changes}
            validate_entry(name, entry)
            value['providers'][name] = entry
        backup = atomic_json(path, value)
        if not project:
            hub.config = value
        # A manual model/policy choice is an explicit operator decision to try a
        # different model.  Keep quota cooldowns for ordinary configuration edits,
        # but clear a stale model/temporary provider cooldown so the new choice can
        # be evaluated once.  The next failed attempt records a fresh cooldown.
        reset_health = bool({'model_policy', 'model', 'model_fallback'} & set(changes))
        if reset_health:
            hub.store.health(name, 0, '')
    return {'agent': name, 'scope': project or 'global', 'updated': changes, 'backup': backup,
            'provider_cooldown_cleared': reset_health}
