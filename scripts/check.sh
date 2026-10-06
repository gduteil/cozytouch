#!/bin/bash
# The three checks CI runs, in the order that fails fastest. Run it before a
# push ; it needs the venv CLAUDE.md describes.
set -euo pipefail
cd "$(dirname "$0")/.."

.venv/bin/ruff check .
.venv/bin/pyright
.venv/bin/pytest tests/ -q "$@"
