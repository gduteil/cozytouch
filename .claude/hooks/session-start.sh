#!/bin/bash
# Builds the venv CLAUDE.md describes, in a Claude Code on the web session.
# The container's own uv may predate Python 3.14.2, which the pinned Home
# Assistant requires, so a newer one is installed beside it when needed.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

PYTHON=3.14.2
UV=uv
if ! uv python find "$PYTHON" >/dev/null 2>&1 \
    && ! uv python install "$PYTHON" >/dev/null 2>&1; then
  if [ ! -x "$HOME/.cache/cozytouch-uv/bin/uv" ]; then
    python3 -m venv "$HOME/.cache/cozytouch-uv"
    "$HOME/.cache/cozytouch-uv/bin/pip" install -q --disable-pip-version-check -U uv
  fi
  UV="$HOME/.cache/cozytouch-uv/bin/uv"
  "$UV" python install -q "$PYTHON"
fi

if [ "$(.venv/bin/python --version 2>/dev/null)" != "Python $PYTHON" ]; then
  "$UV" venv -q --clear --python "$PYTHON"
fi
"$UV" pip install -q -r requirements_test.txt -r requirements_lint.txt \
  -r requirements_typecheck.txt
