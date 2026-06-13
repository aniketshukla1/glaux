#!/usr/bin/env bash
# One-command setup for Athena.
#
#   ./install.sh
#
# Creates a virtualenv, builds the native ledger kernel (and AthenaDB if the
# sibling repo is present), installs the package + the `athena` command, and
# builds the dashboard. When it finishes:  ./venv/bin/athena up
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/venv"

say() { printf "\033[1;36m▸ %s\033[0m\n" "$1"; }

# --- python ---------------------------------------------------------------
PY=""
for c in python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.11+ is required but was not found." >&2; exit 1; }

if [ ! -d "$VENV" ]; then
  say "Creating virtualenv ($PY)"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

say "Installing Python dependencies"
pip install --quiet --upgrade pip maturin
pip install --quiet -r requirements.txt

# --- native modules (maturin) --------------------------------------------
say "Building native ledger kernel (athena_ledger)"
( cd native/athena_ledger && VIRTUAL_ENV="$VENV" maturin develop --release )

if [ -d "$ROOT/../athenadb" ]; then
  say "Building AthenaDB from sibling repo"
  ( cd "$ROOT/../athenadb" && VIRTUAL_ENV="$VENV" maturin develop --release )
else
  echo "  (AthenaDB sibling repo not found at ../athenadb — skipping; memory features need it)"
fi

# --- the athena CLI -------------------------------------------------------
say "Installing the 'athena' command"
pip install --quiet -e .

# --- dashboard ------------------------------------------------------------
if command -v npm >/dev/null 2>&1; then
  say "Building the dashboard"
  ( cd frontend && npm install --silent && npm run build --silent )
else
  echo "  (npm not found — skipping the dashboard build; the API still runs)"
fi

cat <<EOF

$(say "Done.")
  Start Athena:   $VENV/bin/athena up
  Then open:      http://127.0.0.1:8000
  Run a task:     $VENV/bin/athena run "summarize how transformers work"
  Stop it:        $VENV/bin/athena down

  (activate the venv with 'source venv/bin/activate' to drop the path prefix)
EOF
