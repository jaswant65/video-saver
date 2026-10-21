#!/bin/sh
# Run in the foreground so Ctrl+C cleanly stops this copy of the app.
set -eu
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$APP_DIR"
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python server.py "$@"
fi
printf '%s\n' 'First run: python3 setup_local.py' 'Then run: sh start.sh'
exit 1
