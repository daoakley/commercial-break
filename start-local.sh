#!/bin/sh
# Start the Mac-side Claude bridge and Docker detector. The TV agent is separate.
set -eu
cd "$(dirname "$0")"
[ -f .env ] || { echo "Copy .env.example to .env and set both tokens first" >&2; exit 1; }
set -a
. ./.env
set +a
: "${VISION_SERVICE_TOKEN:?Set VISION_SERVICE_TOKEN in .env}"
: "${FRAME_TOKEN:?Set FRAME_TOKEN in .env}"
if command -v claude >/dev/null 2>&1; then
  CLAUDE_BIN=$(command -v claude)
else
  echo "Install the official Claude Code CLI first" >&2
  exit 1
fi
export CLAUDE_BIN
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL
if [ -f .bridge.pid ] && kill -0 "$(cat .bridge.pid)" 2>/dev/null; then
  echo "Claude bridge already running"
else
  CLAUDE_BRIDGE_HOST=0.0.0.0 PYTHONDONTWRITEBYTECODE=1 \
    nohup python3 claude_bridge.py > .bridge.log 2>&1 &
  echo $! > .bridge.pid
  sleep 2
  if ! kill -0 "$(cat .bridge.pid)" 2>/dev/null; then
    cat .bridge.log >&2
    rm -f .bridge.pid
    exit 1
  fi
fi
docker compose up --build -d
echo "Mac classifier and Docker detector started"
