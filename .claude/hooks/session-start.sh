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

# `gh pr comment --attach`, how verify-cozytouch posts its screenshots, needs
# gh 2.99 ; the container ships an older one. Not fatal : a session that
# cannot fetch it still works, it only cannot attach images.
install_gh() {
  local current
  current=$(gh --version 2>/dev/null | sed -n 's/^gh version \([0-9.]*\).*/\1/p')
  if [ -n "$current" ] \
      && [ "$(printf '%s\n2.99.0\n' "$current" | sort -V | head -1)" = "2.99.0" ]; then
    return 0
  fi
  local arch version dir
  case "$(uname -m)" in
    x86_64) arch=amd64 ;;
    aarch64 | arm64) arch=arm64 ;;
    *) return 1 ;;
  esac
  version=$(curl -fsSLI -o /dev/null -w '%{url_effective}' \
    https://github.com/cli/cli/releases/latest | sed 's#.*/tag/v##')
  dir="$HOME/.local/gh"
  mkdir -p "$dir"
  curl -fsSL "https://github.com/cli/cli/releases/download/v$version/gh_${version}_linux_$arch.tar.gz" \
    | tar -xz -C "$dir" --strip-components=1
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    echo "export PATH=\"$dir/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  fi
}
install_gh || echo "session-start: could not install gh 2.99+; --attach unavailable" >&2
