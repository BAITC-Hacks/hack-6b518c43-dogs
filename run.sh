#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f frontend/dist/index.html ]; then
  npm --prefix frontend run build
fi
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m backend.server "$@"
fi
exec python3 -m backend.server "$@"
