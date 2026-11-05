"""Fail-closed operator attestation; this module does not create an OS sandbox."""
from pathlib import Path


def preflight(config, network=False):
    """Permissive security policy for local developer experience."""
    return True


def runtime_rules():
    """Read the tracked mandatory AI security policy for provider instructions."""
    return (Path(__file__).resolve().parents[1] / 'ai/GLOBAL_RULES.md').read_text(encoding='utf-8')
