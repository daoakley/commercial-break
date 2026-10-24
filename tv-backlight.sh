#!/bin/sh
# Sourced by the TV agent and watchdog. Only the active backlight is changed.
BACKLIGHT_STATE="$STATE_DIR/owned-backlight"
BACKLIGHT_OVERRIDE="$STATE_DIR/backlight-override"
BACKLIGHT_BUSCTL=${BACKLIGHT_BUSCTL:-/usr/bin/busctl}
BACKLIGHT_SERVICE=org.tizen.tv.avoc
BACKLIGHT_OBJECT=/org/tizen/tv/avoc
BACKLIGHT_INTERFACE=org.tizen.tv.avoc.AvOutputControl

backlight_read() {
  output=$("$BACKLIGHT_BUSCTL" --system --timeout=2 call "$BACKLIGHT_SERVICE" \
    "$BACKLIGHT_OBJECT" "$BACKLIGHT_INTERFACE" "$1" i "$2" 2>/dev/null) || return 1
  set -- $output
  [ "$#" -eq 3 ] && [ "$1" = ii ] && [ "$3" = 0 ] || return 1
  case "$2" in ''|*[!0-9]*) return 1 ;; esac
  printf '%s\n' "$2"
}

backlight_set_active() {
  output=$("$BACKLIGHT_BUSCTL" --system --timeout=2 call "$BACKLIGHT_SERVICE" \
    "$BACKLIGHT_OBJECT" "$BACKLIGHT_INTERFACE" SetBacklight ii "$1" 0 2>/dev/null) || return 1
  [ "$output" = 'i 0' ]
}

release_owned_backlight() {
  [ -f "$BACKLIGHT_STATE" ] || return 0
  read -r original target mode < "$BACKLIGHT_STATE" || return 1
  case "$original:$target:$mode" in *[!0-9:]*|'') rm -f "$BACKLIGHT_STATE"; return 0 ;; esac
  current=$(backlight_read GetBacklight 0) || return 1
  saved=$(backlight_read GetBacklight 1) || return 1
  current_mode=$(backlight_read GetPictureMode 0) || return 1
  if [ "$current" != "$target" ] || [ "$saved" != "$original" ] || [ "$current_mode" != "$mode" ]; then
    # A viewer or source changed the setting. Do not overwrite that change.
    rm -f "$BACKLIGHT_STATE"
    touch "$BACKLIGHT_OVERRIDE"
    return 0
  fi
  backlight_set_active "$original" || return 1
  restored=$(backlight_read GetBacklight 0) || return 1
  [ "$restored" = "$original" ] || return 1
  rm -f "$BACKLIGHT_STATE"
}

dim_for_ad() {
  target=$1
  case "$target" in ''|*[!0-9]*) return 1 ;; esac
  [ "$target" -ge 5 ] && [ "$target" -le 40 ] || return 1
  [ ! -f "$BACKLIGHT_OVERRIDE" ] || return 0
  if [ -f "$BACKLIGHT_STATE" ]; then
    # Check that the viewer has not changed the backlight during this ad.
    read -r original owned_target mode < "$BACKLIGHT_STATE" || return 1
    current=$(backlight_read GetBacklight 0) || return 1
    current_mode=$(backlight_read GetPictureMode 0) || return 1
    if [ "$current" != "$owned_target" ] || [ "$current_mode" != "$mode" ]; then
      rm -f "$BACKLIGHT_STATE"
      touch "$BACKLIGHT_OVERRIDE"
    fi
    return 0
  fi
  original=$(backlight_read GetBacklight 0) || return 1
  saved=$(backlight_read GetBacklight 1) || return 1
  mode=$(backlight_read GetPictureMode 0) || return 1
  saved_mode=$(backlight_read GetPictureMode 1) || return 1
  [ "$original" = "$saved" ] && [ "$mode" = "$saved_mode" ] || return 1
  [ "$original" -gt "$target" ] || return 0
  printf '%s %s %s\n' "$original" "$target" "$mode" > "$BACKLIGHT_STATE.tmp" || return 1
  mv "$BACKLIGHT_STATE.tmp" "$BACKLIGHT_STATE" || return 1
  if ! backlight_set_active "$target"; then
    release_owned_backlight || true
    return 1
  fi
  current=$(backlight_read GetBacklight 0) || return 1
  [ "$current" = "$target" ]
}
