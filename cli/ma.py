#!/usr/bin/env python3
"""V2 terminal-first entrypoint; legacy hub.py remains available."""
import sys
import subprocess
# Direct invocation must work from any current directory without installation.
from pathlib import Path as _EntryPath
sys.path.insert(0, str(_EntryPath(__file__).resolve().parents[1]))

from agenthub.cli import main

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    try:
        main()
    except KeyboardInterrupt:
        print('\nStopped viewing/input; workflow state retained.')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('Multi Agents: ' + str(error), file=sys.stderr)
        sys.exit(1)
