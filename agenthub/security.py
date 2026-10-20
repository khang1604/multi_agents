"""Fail-closed operator attestation; this module does not create an OS sandbox."""
from pathlib import Path


def preflight(config, network=False):
    scope = config.get('security', {})
    if scope.get('synthetic_data_only') is not True:
        raise ValueError('SECURITY BLOCKED: operator must confirm synthetic-only data; see docs/SECURITY.md')
    # Legacy configurations retain their isolation requirement until the operator
    # explicitly selects the new policy. Never invent an isolation attestation.
    require_isolation = scope.get('require_isolation', True)
    if type(require_isolation) is not bool:
        raise ValueError('SECURITY BLOCKED: require_isolation must be a JSON boolean')
    if require_isolation:
        description = scope.get('isolation_description')
        if (scope.get('isolated_test_environment') is not True
                or not isinstance(description, str) or not description.strip()):
            raise ValueError('SECURITY BLOCKED: operator requested isolation; confirm the isolated environment and describe its boundary; see docs/SECURITY.md')
    if network:
        raise ValueError('SECURITY BLOCKED: unrestricted tool network is forbidden; use an externally enforced test allowlist with network flag disabled')


def runtime_rules():
    return (Path(__file__).resolve().parents[1] / 'GLOBAL_RULES.md').read_text(encoding='utf-8')
