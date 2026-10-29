import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def default_home():
    """Resolve the legacy data home without migrating existing configuration."""
    return Path(os.environ.get('AGENT_HUB_HOME', ROOT / 'data')).resolve()


def defaults():
    """Build the default provider, budget, security, and retention configuration."""
    return {
        'schema_version': 1,
        'security': {'require_isolation': False, 'isolated_test_environment': False,
                     'synthetic_data_only': False, 'isolation_description': ''},
        'leader_priority': ['antigravity', 'claude', 'codex', 'copilot'],
        'worker_priority': ['codex', 'claude'],
        'reviewer_priority': ['claude', 'copilot', 'codex', 'antigravity'],
        'providers': {
            'antigravity': {'command': ['agy'], 'enabled': True, 'roles': ['plan', 'review']},
            'codex': {'command': ['codex'], 'enabled': True, 'roles': ['plan', 'implement', 'review']},
            'claude': {'command': ['claude'], 'enabled': True, 'roles': ['plan', 'implement', 'review']},
            'copilot': {'command': ['copilot'], 'enabled': True, 'roles': ['plan', 'review']},
        },
        'auto': {'small': {'max_calls': 2, 'max_repairs': 0, 'reviewers': 0},
                 'standard': {'max_calls': 6, 'max_repairs': 3, 'reviewers': 1},
                 'complex': {'max_calls': 9, 'max_repairs': 3, 'reviewers': 2}},
        'permissions': {'mcp_config_write': False},
        'max_context_chars': 40000,
        'agent_timeout_seconds': 600,
        'verify_timeout_seconds': 120,
        'quota_cooldown_seconds': 1800,
        'temporary_cooldown_seconds': 120,
        'max_workflow_age_hours': 24,
        'poll_seconds': 2,
        'max_log_bytes': 4 * 1024 * 1024,
        'retention': {'enabled': True, 'archive_completed_worktrees': True, 'failed_logs_days': 7,
                      'cache_max_bytes': 64 * 1024 * 1024, 'cache_max_entries': 20000, 'history_days': 90,
                      'sweep_interval_seconds': 3600,
                      'max_delivery_bytes': 256 * 1024 * 1024},
    }


def load(home):
    """Load existing configuration or create defaults and validate bounded settings."""
    path = Path(home) / 'config.json'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(defaults(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    config = json.loads(path.read_text(encoding='utf-8'))
    for key, value in defaults().items():
        config.setdefault(key, value)
    if not 2000 <= config['max_context_chars'] <= 200000:
        raise ValueError('max_context_chars must be between 2000 and 200000')
    for level in ['small', 'standard', 'complex']:
        item = config['auto'][level]
        if not 1 <= item['max_calls'] <= 50 or not 0 <= item['max_repairs'] <= 5:
            raise ValueError('Invalid Auto budget')
    if config['poll_seconds'] < 0.2 or config['agent_timeout_seconds'] <= 0:
        raise ValueError('Invalid timeout/poll configuration')
    return config
