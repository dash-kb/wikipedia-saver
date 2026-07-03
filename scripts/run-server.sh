#!/bin/sh
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec /usr/bin/env python3 -m wiki_saver.cli --repo "$ROOT/../local-wiki" serve
