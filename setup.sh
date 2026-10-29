#!/bin/sh
# Terminal-only Ubuntu/POSIX setup; no sudo and no shell profile edits.
set -eu
if ! command -v python3 >/dev/null 2>&1; then
    echo 'Python 3.11+ is required. Install it before running setup.' >&2
    exit 1
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else "Python 3.11+ is required")'
exec python3 "$(dirname "$0")/cli/ma.py" setup "$@"
