#!/bin/sh
set -eu
cd "$(dirname "$0")"
docker compose down
if [ -f .bridge.pid ]; then
  kill "$(cat .bridge.pid)" 2>/dev/null || true
  rm -f .bridge.pid
fi
echo "Mac classifier and Docker detector stopped"
