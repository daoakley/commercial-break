#!/bin/sh
# Optional serial capture worker. One process owns both named pipes.
CAPTURE_PID=
CAPTURE_REQUEST="$STATE_DIR/capture-request"
CAPTURE_RESPONSE="$STATE_DIR/capture-response"

capture_worker_stop() {
  if [ -n "$CAPTURE_PID" ]; then kill "$CAPTURE_PID" 2>/dev/null || true; fi
  exec 3>&- 4<&-
  rm -f "$CAPTURE_REQUEST" "$CAPTURE_RESPONSE"
  CAPTURE_PID=
}

capture_worker_start() {
  capture_worker_stop
  mkfifo "$CAPTURE_REQUEST" "$CAPTURE_RESPONSE" || return 1
  CAPTURE_OVERLAY_PAUSE_FILE="$OVERLAY_PAUSE" CAPTURE_OVERLAY_ACK_FILE="$OVERLAY_PAUSED_ACK" \
    LD_PRELOAD="/lib/libcapi-system-info.so.0:$PATCHED_LIB" \
    /usr/bin/dotnet "$PROBE_DLL" --serve < "$CAPTURE_REQUEST" > "$CAPTURE_RESPONSE" \
      2> "$STATE_DIR/capture-worker.log" &
  CAPTURE_PID=$!
  exec 3>"$CAPTURE_REQUEST" 4<"$CAPTURE_RESPONSE"
  while read -r reply <&4; do
    [ "$reply" = capture_ready ] && return 0
  done
  return 1
}

capture_worker_frame() {
  printf '%s\n' "$1" >&3 || return 1
  while read -r reply <&4; do
    case "$reply" in *'rc='*) printf '%s\n' "$reply"; return 0 ;; esac
  done
  return 1
}
