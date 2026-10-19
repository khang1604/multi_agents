"""Fail-closed operator attestation; this module does not create an OS sandbox."""
from pathlib import Path


def preflight(config, network=False):
    scope = config.get('security', {})
    if scope.get('isolated_test_environment') is not True or scope.get('synthetic_data_only') is not True or not scope.get('isolation_description'):
        raise ValueError('SECURITY BLOCKED: operator must provision an isolated synthetic-only environment and declare security policy; see docs/SECURITY.md')
    if network:
        raise ValueError('SECURITY BLOCKED: unrestricted tool network is forbidden; use an externally enforced test allowlist with network flag disabled')


def runtime_rules():
    return (Path(__file__).resolve().parents[1] / 'GLOBAL_RULES.md').read_text(encoding='utf-8')
