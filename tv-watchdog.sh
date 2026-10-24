#!/bin/sh
# Releases TV settings owned by tv-agent.sh when it stops heartbeating.
set -u
STATE_DIR=$1
AGENT_DIR=$2
. "$AGENT_DIR/tv-backlight.sh"
. "$AGENT_DIR/tv-overlay.sh"
OWNED="$STATE_DIR/owned-mute"
HEARTBEAT="$STATE_DIR/heartbeat"

while :; do
  sleep 5
  last=$(cat "$HEARTBEAT" 2>/dev/null || echo 0)
  now=$(date +%s)
  if [ $((now - last)) -gt 45 ]; then
    overlay_release
    if [ -f "$OWNED" ]; then
      /usr/bin/busctl --system --timeout=2 call org.tizen.speakermanager \
        /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager SetSpeakerMute b false >/dev/null 2>&1 || true
      rm -f "$OWNED"
    fi
    release_owned_backlight || true
    if [ ! -f "$BACKLIGHT_STATE" ]; then
      rm -f "$HEARTBEAT"
      exit 0
    fi
  fi
done
