#!/usr/bin/env bash
#
# One-shot deploy: pull latest code, (re)build the image, and (re)start the
# bot in the background. Run this on the server after `git pull` works there.
#
#   ./deploy.sh          # pull + build + run
#   ./deploy.sh --logs   # ...then tail the logs
#
set -euo pipefail

cd "$(dirname "$0")"

# --- compose command (v2 plugin or legacy binary) ---
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "ERROR: docker compose is not installed." >&2
  exit 1
fi

# --- make sure an env file exists ---
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "No .env found — created one from .env.example."
    echo "Edit .env and set DISCORD_TOKEN, then re-run ./deploy.sh"
    exit 1
  fi
  echo "ERROR: no .env file. Create one (see .env.example)." >&2
  exit 1
fi

# --- data dir for the SQLite DB + caches (mounted into the container) ---
mkdir -p data

# --- pull latest if this is a git checkout with a remote ---
if [[ -d .git ]] && git remote >/dev/null 2>&1 && [[ -n "$(git remote)" ]]; then
  echo "==> Pulling latest code..."
  git pull --ff-only || echo "WARN: git pull skipped/failed; using local code."
fi

# --- build and (re)start ---
echo "==> Building image..."
$COMPOSE build

echo "==> Starting container..."
$COMPOSE up -d

echo
echo "==> Status:"
$COMPOSE ps

echo
echo "Done. The DB lives at ./data/foxhole.db on this host."
echo "Logs:    $COMPOSE logs -f"
echo "Stop:    $COMPOSE down"

if [[ "${1:-}" == "--logs" ]]; then
  echo
  exec $COMPOSE logs -f
fi
