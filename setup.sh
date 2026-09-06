#!/usr/bin/env bash
# Blast Radius — setup. Creates an isolated venv, because recent Pythons are
# PEP 668 externally-managed and a bare `pip install` fails on them.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "ready. run:  ./.venv/bin/python -m blastradius.cli impact --help"
