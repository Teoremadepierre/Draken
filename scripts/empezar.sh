#!/usr/bin/env bash
#
# Draken on your own computer, in one command.
#
#   bash scripts/empezar.sh
#
# It creates the virtual environment, installs the dependencies, writes a .env
# with a freshly generated secret key, prepares the database with the 355-source
# catalog, opens the browser and starts the server. Running it again is safe: it
# reuses what is already there and never overwrites your .env.
#
# The server listens on 127.0.0.1 only, so it is reachable from this computer and
# nowhere else. That is also why it starts with the login turned off. To publish
# it, see docs/PUBLICAR.md - that path turns authentication on.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8000}"
URL="http://127.0.0.1:${PORT}"

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$1"; }
die() { printf '\n\033[1;31mError:\033[0m %s\n\n' "$1" >&2; exit 1; }

# --- 1. Python ------------------------------------------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done
[ -n "$PY" ] || die "Draken needs Python 3.11 or newer.
  macOS:   brew install python@3.12
  Ubuntu:  sudo apt install python3.12 python3.12-venv
  Windows: install it from python.org, or use Docker (see docs/EMPEZAR.md)."
say "Python: $($PY --version)"

# --- 2. Virtual environment ----------------------------------------------
if [ ! -x .venv/bin/python ]; then
    say "Creating the virtual environment (.venv)"
    "$PY" -m venv .venv || die "could not create .venv. On Debian/Ubuntu: sudo apt install python3-venv"
fi
VENV_PY=".venv/bin/python"

if ! "$VENV_PY" -c 'import draken' >/dev/null 2>&1; then
    say "Installing dependencies (a couple of minutes the first time)"
    "$VENV_PY" -m pip install --quiet --upgrade pip
    "$VENV_PY" -m pip install --quiet -e "backend"
fi

# --- 3. Configuration -----------------------------------------------------
if [ ! -f .env ]; then
    say "Writing .env with a generated secret key"
    SECRET="$("$VENV_PY" -c 'import secrets; print(secrets.token_hex(32))')"
    # Local use: no login, because the port is not reachable from outside this
    # machine. Publishing is a different setup - docs/PUBLICAR.md.
    sed -e "s|^DRAKEN_SECRET_KEY=.*|DRAKEN_SECRET_KEY=${SECRET}|" \
        -e "s|^DRAKEN_AUTH_ENABLED=.*|DRAKEN_AUTH_ENABLED=false|" \
        .env.example > .env
    chmod 600 .env
else
    say "Keeping your existing .env"
fi

mkdir -p data

# --- 4. Database ----------------------------------------------------------
say "Preparing the database and the source catalog"
.venv/bin/draken init-db >/dev/null

# --- 5. Browser -----------------------------------------------------------
open_browser() {
    sleep 3
    if command -v open >/dev/null 2>&1; then open "$URL"
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
    fi
}
open_browser >/dev/null 2>&1 &

printf '\n  \033[1;32mDraken is starting\033[0m\n'
printf '  Open this in your browser:  \033[4m%s\033[0m\n' "$URL"
printf '  Stop it with Ctrl+C\n\n'

# --- 6. Run ---------------------------------------------------------------
DRAKEN_PORT="$PORT" exec .venv/bin/draken serve
