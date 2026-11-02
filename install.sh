#!/usr/bin/env bash
# One-command setup for Glaux.
#
#   ./install.sh
#
# Creates a virtualenv, builds the native ledger kernel (and AthenaDB if the
# sibling repo is present), installs the package + the `glaux` command, and
# builds the dashboard. When it finishes:  ./venv/bin/glaux up
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/venv"
ATHENADB="$ROOT/../athenadb"

say() { printf "\033[1;36m▸ %s\033[0m\n" "$1"; }

# --- preflight ------------------------------------------------------------
# AthenaDB backs the memory layers and the skill library, and core.api imports
# them at module scope — so without it the server cannot start at all. Check now
# rather than after a multi-minute Rust build.
if [ ! -d "$ATHENADB" ]; then
  PARENT="$(cd "$ROOT/.." && pwd)"
  cat >&2 <<MSG
AthenaDB is required, and was not found next to this repo.

  expected at:  $PARENT/athenadb

Glaux's memory layers and skill library are built on it. Clone it beside this
repo and run this script again:

  git clone https://github.com/athena-swarm/athenadb $PARENT/athenadb
  ./install.sh

MSG
  exit 1
fi

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
# maturin refuses to run when a conda env is active alongside the venv
# ("Both VIRTUAL_ENV and CONDA_PREFIX are set"), so drop conda for these builds.
say "Building native ledger kernel (glaux_ledger)"
( cd native/glaux_ledger && env -u CONDA_PREFIX VIRTUAL_ENV="$VENV" maturin develop --release )

say "Building AthenaDB (sibling repo)"
( cd "$ATHENADB" && env -u CONDA_PREFIX VIRTUAL_ENV="$VENV" maturin develop --release )

# --- the glaux CLI -------------------------------------------------------
say "Installing the 'glaux' command"
pip install --quiet -e .

# --- dashboard ------------------------------------------------------------
# The API and CLI are fully usable without the dashboard, so anything wrong here
# is a warning, never a failed install. Notably: `apt install nodejs` on Ubuntu
# 22.04 still gives Node 12, which dies inside Vite on a top-level await with a
# bare "SyntaxError: Unexpected reserved word" — no hint that Node is the problem.
NODE_MAJOR=0
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
fi

if ! command -v npm >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1; then
  echo "  (Node.js/npm not found — skipping the dashboard; the API and CLI still work)"
elif [ "$NODE_MAJOR" -lt 18 ]; then
  echo "  (Node $(node -v) is too old to build the dashboard — Vite needs 18+.)"
  echo "   Install a newer Node with nvm or NodeSource, then:"
  echo "     npm --prefix frontend install && npm --prefix frontend run build"
  echo "   The API and CLI work without it."
else
  say "Building the dashboard"
  if ! ( cd frontend && npm install --silent && npm run build --silent ); then
    echo "  (the dashboard build failed — the API and CLI still work.)"
    echo "   Retry with:  npm --prefix frontend install && npm --prefix frontend run build"
  fi
fi

cat <<EOF

$(say "Done.")
  Start Glaux:   $VENV/bin/glaux up
  Then open:      http://127.0.0.1:8000
  Run a task:     $VENV/bin/glaux run "summarize how transformers work"
  Stop it:        $VENV/bin/glaux down

  (activate the venv with 'source venv/bin/activate' to drop the path prefix)
EOF
