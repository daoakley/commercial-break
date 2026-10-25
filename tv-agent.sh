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
TV_APP=${TV_APP:-com.samsung.tv.cobalt-yttv}
TV_CHANNEL=${TV_CHANNEL:-}
TV_TITLE=${TV_TITLE:-}
MAX_FRAMES=${MAX_FRAMES:-0}
MAX_RUNTIME_SECONDS=${MAX_RUNTIME_SECONDS:-0}
MAX_MUTE_EXTENSION_SECONDS=${MAX_MUTE_EXTENSION_SECONDS:-300}
PANEL_MASK_ON_CAPTURE=${PANEL_MASK_ON_CAPTURE:-0}
CAPTURE_PERSISTENT=${CAPTURE_PERSISTENT:-0}
CAPTURE_BACKEND=${CAPTURE_BACKEND:-display}
ACR_PROBE_DLL=${ACR_PROBE_DLL:-/home/owner/share/tmp/sdk_tools/AcrFrameProbe.dll}
FAST_MODE=${FAST_MODE:-0}
NAVIGATION_OBSERVER=${NAVIGATION_OBSERVER:-0}
NAVIGATION_DLL=${NAVIGATION_DLL:-/home/owner/share/tmp/sdk_tools/NavigationObserver.dll}
NAVIGATION_PID=
NAVIGATION_FILE="$STATE_DIR/navigation"
WAKE_URL=${WAKE_URL:-${FRAME_URL%/v1/frame}/v1/wake}
TV_SESSION=${TV_SESSION:-$(date +%s)-$$}
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
if [ "$CAPTURE_PERSISTENT" = 1 ]; then . "$AGENT_DIR/tv-capture.sh"; fi

uptime_now() { awk '{print $1}' /proc/uptime; }
navigation_generation() {
  value=0
  if [ -f "$NAVIGATION_FILE" ]; then read -r value < "$NAVIGATION_FILE" || true; fi
  case "$value" in ''|*[!0-9]*) value=0 ;; esac
  printf '%s\n' "$value"
}

get_mute() {
  /usr/bin/busctl --system --timeout=2 call org.tizen.speakermanager \
    /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager GetSpeakerMute 2>/dev/null
}

current_app_id() {
  # Read the actual foreground app. An unavailable identity fails open rather
  # than substituting the configured app and inheriting its old ad state.
  /usr/bin/vconftool get memory/appfw/current_fullscreen_appid 2>/dev/null |
    sed -n 's/^[^,]*, value = \([A-Za-z0-9._-]*\) (String)$/\1/p' |
    head -n 1
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
  if [ -n "$NAVIGATION_PID" ]; then kill "$NAVIGATION_PID" 2>/dev/null || true; fi
  rm -f "$STATE_DIR/panel-mask-enabled"
  if [ "$CAPTURE_PERSISTENT" = 1 ]; then capture_worker_stop; fi
  overlay_shutdown
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
if [ "$PANEL_MASK_ON_CAPTURE" = 1 ]; then
  touch "$STATE_DIR/panel-mask-enabled"
else
  rm -f "$STATE_DIR/panel-mask-enabled"
fi
/bin/sh -c "$(cat "$AGENT_DIR/tv-watchdog.sh")" -- "$STATE_DIR" "$AGENT_DIR" &
WATCHDOG_PID=$!
date +%s > "$HEARTBEAT"
if [ "$NAVIGATION_OBSERVER" = 1 ] && [ -f "$NAVIGATION_DLL" ]; then
  /usr/bin/dotnet "$NAVIGATION_DLL" > "$STATE_DIR/navigation.log" 2>&1 &
  NAVIGATION_PID=$!
fi
if [ "${OVERLAY_WARM:-0}" = 1 ]; then overlay_prepare || true; fi

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
  cycle_started=$(uptime_now)
  captured_navigation=$(navigation_generation)
  observed_app=$(current_app_id)
  if [ -z "$observed_app" ]; then
    overlay_release; release_owned_mute; release_owned_backlight || true
    sleep 1
    continue
  fi
  capture_pause=
  capture_ack=
  if [ -f "$OVERLAY_LEASE" ] && overlay_running; then
    capture_pause=$OVERLAY_PAUSE
    capture_ack=$OVERLAY_PAUSED_ACK
  fi
  capture_backend=display
  if [ "$CAPTURE_BACKEND" = acr ] && [ -f "$ACR_PROBE_DLL" ]; then
    # Content-recognition capture reads the decoded video beneath the card:
    # no hide/blank/restore handshake, so covered checks can run often without
    # a visible blink. A failed call falls back to the display path below.
    capture_output=$(CAPTURE_OVERLAY_PAUSE_FILE="$capture_pause" \
      CAPTURE_OVERLAY_ACK_FILE="$capture_ack" \
      LD_PRELOAD="/lib/libcapi-system-info.so.0:$PATCHED_LIB" \
      /usr/bin/dotnet "$ACR_PROBE_DLL" 2>&1) || capture_output=
    case "$capture_output" in
      *'rc=0 width='*) capture_backend=acr ;;
      *) echo "acr capture failed; using display capture" >&2; capture_output= ;;
    esac
  fi
  if [ "$capture_backend" = acr ]; then
    :
  elif [ "$CAPTURE_PERSISTENT" = 1 ]; then
    if [ -z "$CAPTURE_PID" ] || ! kill -0 "$CAPTURE_PID" 2>/dev/null; then
      capture_worker_start || { overlay_release; release_owned_mute; release_owned_backlight || true; sleep 3; continue; }
    fi
    mode=clear
    if [ -n "$capture_pause" ]; then mode=covered; fi
    capture_output=$(capture_worker_frame "$mode") || capture_output=
  else
    capture_output=$(CAPTURE_OVERLAY_PAUSE_FILE="$capture_pause" \
    CAPTURE_OVERLAY_ACK_FILE="$capture_ack" \
    LD_PRELOAD="/lib/libcapi-system-info.so.0:$PATCHED_LIB" \
    /usr/bin/dotnet "$PROBE_DLL" 2>&1) || capture_output=
  fi
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
  captured_at=$(uptime_now)
  request_timeout=38
  if [ "$FAST_MODE" = 1 ]; then request_timeout=3; fi
  # Bind the frame to the foreground app before capture, not after it.
  # A transition during capture must not label the old picture as the new app.
  if [ "$(current_app_id)" != "$observed_app" ] ||
     [ "$(navigation_generation)" != "$captured_navigation" ]; then
    overlay_release; release_owned_mute; release_owned_backlight || true
    rm -f "$CAPTURE_FILE"
    sleep 1
    continue
  fi
  action=$(curl -fsS --connect-timeout 2 --max-time "$request_timeout" -D "$RESPONSE_HEADERS" -X POST \
    -H "Expect:" \
    -H "Authorization: Bearer $FRAME_TOKEN" \
    -H "Content-Type: image/png" \
    -H "X-TV-ID: $TV_ID" \
    -H "X-TV-Session: $TV_SESSION-$captured_navigation" \
    -H "X-TV-Frame-Sequence: $((count + 1))" \
    -H "X-TV-Capture-Backend: $capture_backend" \
    -H "X-TV-App: $observed_app" \
    -H "X-TV-Channel: $TV_CHANNEL" \
    -H "X-TV-Title: $TV_TITLE" \
    -H "X-TV-Local-Time: $(date '+%Y-%m-%dT%H:%M:%S%z')" \
    --data-binary "@$CAPTURE_FILE" "$FRAME_URL") || { action=UNMUTE; request_ok=0; }
  rm -f "$CAPTURE_FILE"
  response_at=$(uptime_now)
  next_interval=$INTERVAL_SECONDS
  if [ "$request_ok" -eq 1 ] && [ -f "$RESPONSE_HEADERS" ]; then
    if command -v overlay_update_info >/dev/null 2>&1; then overlay_update_info "$RESPONSE_HEADERS"; fi
    suggested=$(awk 'tolower($1)=="x-next-capture-seconds:" {gsub("\r", "", $2); print $2}' "$RESPONSE_HEADERS" | tail -1)
    case "$suggested" in 1|2|3|4|5|8|15) next_interval=$suggested ;; esac
  fi
  rm -f "$RESPONSE_HEADERS"

  observed_action=
  current_navigation=$(navigation_generation)
  # A remote action invalidates even a conclusive answer to an older frame.
  # Leave a short grace period for the app's guide/channel transition.
  if [ "$(current_app_id)" != "$observed_app" ] ||
     [ "$current_navigation" != "$captured_navigation" ] ||
     { [ "$current_navigation" -gt 0 ] && [ $(( $(date +%s) - current_navigation / 1000 )) -lt 3 ]; }; then
    action=UNMUTE
    next_interval=1
  fi
  if [ "${OBSERVE_ONLY:-0}" = 1 ]; then
    observed_action=$action
    action=UNMUTE
  fi
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
      # Show a warmed card before slower brightness readbacks.
      if [ -f "$OWNED" ]; then
        overlay_start_or_renew || echo "commercial overlay unavailable" >&2
      else
        overlay_release
      fi
      if [ -f "$OWNED" ] && [ -n "${AD_BACKLIGHT:-}" ]; then
        dim_for_ad "$AD_BACKLIGHT" || echo "backlight dim unavailable" >&2
      else
        release_owned_backlight || true
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
  # Navigation can race slow mute/backlight operations, too. Recheck after
  # actuation and release only controls this helper owns if identity changed.
  if [ "$(navigation_generation)" != "$captured_navigation" ] ||
     [ "$(current_app_id)" != "$observed_app" ]; then
    overlay_release; release_owned_mute; release_owned_backlight || true
    action=UNMUTE
    next_interval=1
  fi
  cycle_finished=$(uptime_now)
  timings=$(awk -v a="$cycle_started" -v b="$captured_at" -v c="$response_at" -v d="$cycle_finished" 'BEGIN {printf "capture_ms=%.0f request_ms=%.0f actuation_ms=%.0f", (b-a)*1000,(c-b)*1000,(d-c)*1000}')
  echo "$(date '+%H:%M:%S') decision=$action${observed_action:+ observed=$observed_action} $timings"
  count=$((count + 1))
  date +%s > "$HEARTBEAT"
  if [ "$request_ok" -eq 0 ]; then
    # Keep playback untouched and reduce capture work while the computer is off.
    sleep 15
  else
    if [ "$FAST_MODE" = 1 ]; then
      delay=$(awk -v a="$cycle_started" -v b="$cycle_finished" -v n="$next_interval" 'BEGIN {d=n-(b-a); printf "%.3f", (d>0.1?d:0.1)}') || delay=1
      if [ -z "$delay" ]; then delay=1; fi
      sleep "$delay"
    elif [ -f "$OWNED" ] && [ "$next_interval" -gt 2 ] && [ "${WAKE_POLL:-1}" = 1 ]; then
      # Covered: a long idle gap, but the detector may learn that the app's
      # inserted-ad pod just ended. Ask once a second whether to look now.
      # Uncovered sleeps are untouched; nothing here changes the picture.
      slept=0
      while [ "$slept" -lt "$next_interval" ]; do
        sleep 1
        slept=$((slept + 1))
        [ -f "$STATE_DIR/stop" ] && break
        # The viewer's unmute is the manual escape: honour it within a second,
        # not at the next screenshot. The override holds until the break ends.
        case "$(get_mute)" in
          'ii 0 0')
            rm -f "$OWNED"; touch "$OVERRIDE"
            overlay_release; release_owned_backlight || true
            echo "$(date '+%H:%M:%S') viewer unmuted: cover released, override set"
            break ;;
        esac
        wake=$(curl -fsS --connect-timeout 1 --max-time 2 \
          -H "Authorization: Bearer $FRAME_TOKEN" \
          -H "X-TV-ID: $TV_ID" \
          -H "X-TV-Session: $TV_SESSION-$captured_navigation" \
          "$WAKE_URL" 2>/dev/null) || wake=0
        if [ "$wake" = 1 ]; then echo "$(date '+%H:%M:%S') wake=native_end after ${slept}s"; break; fi
      done
    else
      sleep "$next_interval"
    fi
  fi
done
