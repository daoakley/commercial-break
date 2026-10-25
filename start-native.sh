#!/bin/sh
set -eu
cd "$(dirname "$0")"
umask 077
set -a
. ./.env
set +a
: "${TV_HOST:?Set TV_HOST in the private .env file}"
if [ -f .native-events.pid ] && kill -0 "$(cat .native-events.pid)" 2>/dev/null; then
  echo 'Native onset relay already running'
  exit 0
fi
nohup python3 -u youtube_events.py --tv-host "$TV_HOST" >.native-events.log 2>&1 </dev/null &
echo "$!" >.native-events.pid
echo 'Native onset relay started'
