#!/bin/sh
# Run on the TV from a temporary root shell. No boot hooks or system files.
set -u
umask 077

: "${FRAME_URL:?Set FRAME_URL to the Docker service /v1/frame URL}"
: "${FRAME_TOKEN:?Set FRAME_TOKEN to match the Docker service}"

PROBE_DLL=${PROBE_DLL:-/home/owner/share/tmp/sdk_tools/DisplayCaptureProbe.dll}
PATCHED_LIB=${PATCHED_LIB:-/run/libtzcapturec-probe.so}
CAPTURE_FILE=/home/owner/share/tmp/sdk_tools/codex-display-sample.png.png
STATE_DIR=/run/codex-commercial-muter
INTERVAL_SECONDS=${INTERVAL_SECONDS:-3}
TV_ID=${TV_ID:-frame-tv}
TV_APP=${TV_APP:-unknown}
TV_CHANNEL=${TV_CHANNEL:-}
TV_TITLE=${TV_TITLE:-}
MAX_FRAMES=${MAX_FRAMES:-0}
MAX_RUNTIME_SECONDS=${MAX_RUNTIME_SECONDS:-0}
MAX_MUTE_EXTENSION_SECONDS=${MAX_MUTE_EXTENSION_SECONDS:-300}
STARTED_AT=$(date +%s)

mkdir -p "$STATE_DIR" || exit 1
chmod 700 "$STATE_DIR"
rm -f "$STATE_DIR/stop"
OWNED="$STATE_DIR/owned-mute"
OVERRIDE="$STATE_DIR/manual-override"
HEARTBEAT="$STATE_DIR/heartbeat"
RESPONSE_HEADERS="$STATE_DIR/response-headers"
WATCHDOG_PID=
AGENT_DIR=${AGENT_DIR:-$(dirname "$0")}
. "$AGENT_DIR/tv-backlight.sh"
. "$AGENT_DIR/tv-overlay.sh"

get_mute() {
  /usr/bin/busctl --system --timeout=2 call org.tizen.speakermanager \
    /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager GetSpeakerMute 2>/dev/null
}

set_mute() {
  /usr/bin/busctl --system --timeout=2 call org.tizen.speakermanager \
    /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager SetSpeakerMute b "$1" >/dev/null
}

release_owned_mute() {
  if [ -f "$OWNED" ]; then
    case "$(get_mute)" in
      'ii 1 0') set_mute false || true ;;
    esac
    rm -f "$OWNED"
  fi
}

cleanup() {
  overlay_release
  release_owned_mute
  release_owned_backlight || true
  rm -f "$CAPTURE_FILE" "$HEARTBEAT" "$OVERRIDE" "$RESPONSE_HEADERS"
  if [ -n "$WATCHDOG_PID" ] && [ ! -f "$BACKLIGHT_STATE" ]; then
    kill "$WATCHDOG_PID" 2>/dev/null || true
  fi
}
trap cleanup 0
trap 'exit 0' HUP INT TERM

if [ ! -f "$PROBE_DLL" ] || [ ! -f "$PATCHED_LIB" ]; then
  echo "Capture probe or temporary process-local library is missing" >&2
  exit 1
fi

release_owned_backlight || true
/bin/sh -c "$(cat "$AGENT_DIR/tv-watchdog.sh")" -- "$STATE_DIR" "$AGENT_DIR" &
WATCHDOG_PID=$!

count=0
while [ "$MAX_FRAMES" -eq 0 ] || [ "$count" -lt "$MAX_FRAMES" ]; do
  if [ -f "$STATE_DIR/stop" ]; then
    echo "stop requested"
    break
  fi
  if [ "$MAX_RUNTIME_SECONDS" -gt 0 ]; then
    elapsed=$(( $(date +%s) - STARTED_AT ))
    if [ "$elapsed" -ge "$MAX_RUNTIME_SECONDS" ]; then
      if { [ ! -f "$OWNED" ] && [ ! -f "$BACKLIGHT_STATE" ]; } || [ "$elapsed" -ge $((MAX_RUNTIME_SECONDS + MAX_MUTE_EXTENSION_SECONDS)) ]; then
        echo "session time limit reached"
        break
      fi
    fi
  fi
  date +%s > "$HEARTBEAT"
  capture_pause=
  capture_ack=
  if overlay_running; then
    capture_pause=$OVERLAY_PAUSE
    capture_ack=$OVERLAY_PAUSED_ACK
  fi
  capture_output=$(CAPTURE_OVERLAY_PAUSE_FILE="$capture_pause" \
    CAPTURE_OVERLAY_ACK_FILE="$capture_ack" \
    LD_PRELOAD="/lib/libcapi-system-info.so.0:$PATCHED_LIB" \
    /usr/bin/dotnet "$PROBE_DLL" 2>&1) || capture_output=
  case "$capture_output" in
    *'rc=0 width='*) ;;
    *) echo "capture unavailable" >&2; overlay_release; release_owned_mute; release_owned_backlight || true; sleep "$INTERVAL_SECONDS"; continue ;;
  esac
  if [ ! -s "$CAPTURE_FILE" ]; then
    echo "capture file missing" >&2
    overlay_release
    release_owned_mute
    release_owned_backlight || true
    sleep "$INTERVAL_SECONDS"
    continue
  fi

  request_ok=1
  action=$(curl -fsS --connect-timeout 2 --max-time 38 -D "$RESPONSE_HEADERS" -X POST \
    -H "Authorization: Bearer $FRAME_TOKEN" \
    -H "Content-Type: image/png" \
    -H "X-TV-ID: $TV_ID" \
    -H "X-TV-App: $TV_APP" \
    -H "X-TV-Channel: $TV_CHANNEL" \
    -H "X-TV-Title: $TV_TITLE" \
    -H "X-TV-Local-Time: $(date '+%Y-%m-%dT%H:%M:%S%z')" \
    --data-binary "@$CAPTURE_FILE" "$FRAME_URL") || { action=UNMUTE; request_ok=0; }
  rm -f "$CAPTURE_FILE"
  next_interval=$INTERVAL_SECONDS
  if [ "$request_ok" -eq 1 ] && [ -f "$RESPONSE_HEADERS" ]; then
    suggested=$(awk 'tolower($1)=="x-next-capture-seconds:" {gsub("\r", "", $2); print $2}' "$RESPONSE_HEADERS" | tail -1)
    case "$suggested" in 2|3|5|8|15) next_interval=$suggested ;; esac
  fi
  rm -f "$RESPONSE_HEADERS"

  case "$action" in
    MUTE)
      if [ -f "$OWNED" ]; then
        case "$(get_mute)" in
          'ii 0 0') rm -f "$OWNED"; touch "$OVERRIDE" ;;
        esac
      elif [ ! -f "$OVERRIDE" ]; then
        case "$(get_mute)" in
          'ii 0 0') if set_mute true; then touch "$OWNED"; fi ;;
        esac
      fi
      if [ -f "$OWNED" ] && [ -n "${AD_BACKLIGHT:-}" ]; then
        dim_for_ad "$AD_BACKLIGHT" || echo "backlight dim unavailable" >&2
      else
        release_owned_backlight || true
      fi
      if [ -f "$OWNED" ]; then
        overlay_start_or_renew || echo "commercial overlay unavailable" >&2
      else
        overlay_release
      fi
      ;;
    UNMUTE)
      overlay_release
      release_owned_mute
      release_owned_backlight || true
      rm -f "$OVERRIDE"
      rm -f "$BACKLIGHT_OVERRIDE"
      ;;
    *)
      # An invalid reply must never leave the TV muted by this agent.
      overlay_release
      release_owned_mute
      release_owned_backlight || true
      ;;
  esac
  echo "$(date '+%H:%M:%S') decision=$action"
  count=$((count + 1))
  date +%s > "$HEARTBEAT"
  if [ "$request_ok" -eq 0 ]; then
    # Keep playback untouched and reduce capture work while the computer is off.
    sleep 15
  else
    sleep "$next_interval"
  fi
done
