#!/bin/sh
# Optional, temporary on-TV commercial card. The overlay process expires when
# its lease stops refreshing and never changes the underlying playback app.
OVERLAY_LEASE="$STATE_DIR/overlay-lease"
OVERLAY_PAUSE="$STATE_DIR/overlay-pause"
OVERLAY_PAUSED_ACK="$STATE_DIR/overlay-paused-ack"
OVERLAY_PID="$STATE_DIR/overlay-pid"
OVERLAY_INFO="$STATE_DIR/overlay-info.json"
OVERLAY_DLL=${OVERLAY_DLL:-/home/owner/share/tmp/sdk_tools/CommercialOverlayProbe.dll}
OVERLAY_SCENE=${OVERLAY_SCENE:-/home/owner/share/tmp/sdk_tools/commercial-break-scene.json}

overlay_release() {
  rm -f "$OVERLAY_LEASE" "$OVERLAY_PAUSE" "$OVERLAY_PAUSED_ACK" "$OVERLAY_INFO"
  if [ "${OVERLAY_WARM:-0}" != 1 ]; then rm -f "$OVERLAY_PID"; fi
}

overlay_shutdown() {
  overlay_release
  if [ "${OVERLAY_WARM:-0}" = 1 ] && overlay_running; then
    read -r pid < "$OVERLAY_PID"
    kill "$pid" 2>/dev/null || true
  fi
  rm -f "$OVERLAY_PID"
}

overlay_running() {
  [ -f "$OVERLAY_PID" ] || return 1
  read -r pid < "$OVERLAY_PID" || return 1
  case "$pid" in ''|*[!0-9]*) return 1 ;; esac
  kill -0 "$pid" 2>/dev/null || return 1
  case "$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null)" in
    *CommercialOverlayProbe.dll*) return 0 ;;
    *) return 1 ;;
  esac
}

overlay_prepare() {
  [ "${AD_OVERLAY:-0}" = 1 ] || return 0
  [ -f "$OVERLAY_DLL" ] && [ -f "$OVERLAY_SCENE" ] || return 1
  if overlay_running; then return 0; fi
  rm -f "$OVERLAY_PAUSE" "$OVERLAY_PAUSED_ACK"
  set --
  if [ "${OVERLAY_WARM:-0}" = 1 ]; then set -- --standby-file "$HEARTBEAT"; fi
  /usr/bin/dotnet "$OVERLAY_DLL" --seconds 0 --scene "$OVERLAY_SCENE" "$@" \
    --navigation-file "$STATE_DIR/navigation" \
    --info-file "$OVERLAY_INFO" \
    --lease-file "$OVERLAY_LEASE" --pause-file "$OVERLAY_PAUSE" \
    --paused-ack-file "$OVERLAY_PAUSED_ACK" > "$STATE_DIR/overlay.log" 2>&1 &
  echo "$!" > "$OVERLAY_PID"
}

overlay_update_info() {
  encoded=$(awk 'tolower($1)=="x-overlay-info:" {gsub("\r", "", $2); print $2}' "$1" | tail -1)
  case "$encoded" in ''|*[!A-Za-z0-9+/=]*) return 0 ;; esac
  [ "${#encoded}" -le 8192 ] || return 0
  if printf '%s' "$encoded" | base64 -d > "$OVERLAY_INFO.next" 2>/dev/null; then
    mv "$OVERLAY_INFO.next" "$OVERLAY_INFO"
  else
    rm -f "$OVERLAY_INFO.next"
  fi
}

overlay_start_or_renew() {
  [ "${AD_OVERLAY:-0}" = 1 ] || return 0
  touch "$OVERLAY_LEASE" || return 1
  overlay_prepare
}
