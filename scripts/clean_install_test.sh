#!/usr/bin/env bash
# Install Glaux on a pristine Linux box and prove it reaches first value.
#
#   scripts/clean_install_test.sh [--keep] [--image ubuntu:24.04]
#
# The launch-day spike is wasted if `./install.sh` fails on a fresh machine, and
# the failure mode is almost never our code — it is a system package we depend on
# without saying so. So this installs ONLY what the README claims you need, then
# runs install.sh and a smoke test that exercises the native kernel and the CLI.
#
# Anything in EXTRA_PREREQS below is a documentation bug: it is a package the
# install genuinely needs that a reader of the README would not know to install.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

IMAGE="ubuntu:22.04"
KEEP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=1 ;;
    --image) IMAGE="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say() { printf "\033[1;36m▸ %s\033[0m\n" "$1"; }
CONTAINER="glaux-clean-install-$$"

command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "the docker daemon is not running" >&2; exit 2; }

# Exactly what a user gets from `git clone` — tracked files at HEAD, so a local
# venv/, node_modules/ or .glaux/ cannot leak in and fake a passing install.
# Both repos, side by side, because that is the documented layout: AthenaDB backs
# the memory layers and core.api imports them at module scope.
ATHENADB_SRC="$ROOT/../athenadb"
[ -d "$ATHENADB_SRC" ] || { echo "need the athenadb sibling repo at $ATHENADB_SRC" >&2; exit 2; }

say "Exporting HEAD of both repos (tracked files only)"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/glaux" "$STAGE/athenadb"
git archive --format=tar HEAD | tar -x -C "$STAGE/glaux"
git -C "$ATHENADB_SRC" archive --format=tar HEAD | tar -x -C "$STAGE/athenadb"
printf '  glaux %s files · athenadb %s files\n' \
  "$(find "$STAGE/glaux" -type f | wc -l | tr -d ' ')" \
  "$(find "$STAGE/athenadb" -type f | wc -l | tr -d ' ')"

say "Starting a clean $IMAGE container"
docker run -d --name "$CONTAINER" -v "$STAGE:/src:ro" "$IMAGE" sleep infinity >/dev/null
cleanup() {
  if [ "$KEEP" = 1 ]; then
    echo "  container kept: docker exec -it $CONTAINER bash"
  else
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap 'cleanup; rm -rf "$STAGE"' EXIT

docker exec "$CONTAINER" bash -euo pipefail -c '
  export DEBIAN_FRONTEND=noninteractive

  # --- what the README tells you to have -----------------------------------
  DOCUMENTED_PREREQS="python3 nodejs npm"
  # --- what it actually also needs (each one is a README bug) --------------
  EXTRA_PREREQS="python3-venv python3-dev build-essential curl ca-certificates pkg-config"

  echo "::group::apt"
  apt-get update -qq
  apt-get install -y -qq $DOCUMENTED_PREREQS $EXTRA_PREREQS >/dev/null
  echo "::endgroup::"

  echo "--- versions on this clean box ---"
  python3 --version; node --version; npm --version

  # Rust toolchain, as the README says to install it
  curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --no-modify-path >/dev/null 2>&1
  export PATH="$HOME/.cargo/bin:$PATH"
  rustc --version

  # install.sh writes into the tree, so work on a copy of the read-only mount.
  # Keep the sibling layout: /work/glaux + /work/athenadb.
  cp -r /src /work && cd /work/glaux

  echo
  echo "=== ./install.sh ==="
  start=$(date +%s)
  ./install.sh
  echo "INSTALL_SECONDS=$(( $(date +%s) - start ))"
'

say "Smoke test — does a clean install actually reach first value?"
docker exec "$CONTAINER" bash -euo pipefail -c '
  cd /work/glaux
  export PATH="$HOME/.cargo/bin:$PATH"

  echo "--- the CLI is installed and self-describes ---"
  ./venv/bin/glaux version
  ./venv/bin/glaux --help >/dev/null && echo "glaux --help ok"

  # `glaux version` and `--help` never import the app, so they pass even when the
  # server cannot start at all. The README tells a new user to run `glaux up`
  # second — so that is what has to work here.
  echo
  echo "--- the API app imports (what glaux up actually does) ---"
  ./venv/bin/python -c "import sys; sys.path.insert(0, \"src\"); import core.api; print(\"  core.api imported\")"

  echo
  echo "--- and the server comes up and answers ---"
  ./venv/bin/glaux up >/tmp/up.log 2>&1 || true
  up=0
  for _ in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then up=1; break; fi
    sleep 1
  done
  if [ "$up" != 1 ]; then
    echo "FAIL: the server never became healthy" >&2; tail -20 /tmp/up.log >&2; exit 1
  fi
  curl -fsS http://127.0.0.1:8000/api/health | head -c 200; echo
  ./venv/bin/glaux down >/dev/null 2>&1 || true

  echo
  echo "--- the native ledger kernel signs a real chain ---"
  ./venv/bin/python - <<PY
import sys; sys.path.insert(0, "src")
from core.ledger import Ledger, Action
from identity.keypair import AgentIdentity
led = Ledger()
a, b = AgentIdentity.generate(), AgentIdentity.generate()
led.append(a, Action.PLAN, {"team": ["researcher"]})
led.append(b, Action.CALL_SKILL, {"skill": "http_get"})
led.append(b, Action.OBSERVATION, {"ok": True})
led.save("/tmp/ledger.jsonl")
print(f"  signed {len(led)} blocks")
PY

  echo
  echo "--- verify accepts the untouched chain ---"
  ./venv/bin/glaux verify --file /tmp/ledger.jsonl

  echo
  echo "--- and catches a forged one (the README demo, verbatim) ---"
  sed -i.bak "2s/\"agent_id\":\"[^\"]*\"/\"agent_id\":\"mallory\"/" /tmp/ledger.jsonl
  if ./venv/bin/glaux verify --file /tmp/ledger.jsonl; then
    echo "FAIL: a forged chain verified as valid" >&2; exit 1
  fi
  echo "  (correctly exited non-zero)"

  echo
  echo "--- the test suite passes on a clean box ---"
  ./venv/bin/python -m pytest -q 2>&1 | tail -3
'

say "PASS — clean $IMAGE install reaches a verified ledger"
