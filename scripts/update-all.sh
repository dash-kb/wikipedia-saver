#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ -n "${WIKIPEDIA_SAVER_REPO:-}" ]; then
  exec /usr/bin/env python3 -m wiki_saver.cli --repo "$WIKIPEDIA_SAVER_REPO" update-all
fi
exec /usr/bin/env python3 -m wiki_saver.cli update-all
