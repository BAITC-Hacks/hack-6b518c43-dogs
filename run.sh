#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/public frontend/index.html frontend/package.json frontend/package-lock.json -type f -newer frontend/dist/index.html -print -quit)" ]; then
  npm --prefix frontend run build
fi
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m backend.server "$@"
fi
exec python3 -m backend.server "$@"
