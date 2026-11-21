#!/bin/sh
# Optional, reversible firmware-update lock for owner-controlled TVs.
# The explicit marker keeps this dormant on other Commercial Break installs.
set -eu
H=${CB_HOME:-/opt/usr/home/owner/commercial-block}
ENABLED="$H/firmware-update-lock-enabled"
[ -f "$ENABLED" ] || exit 0
[ "$(id -u)" = 0 ] || exit 1

STATE=/run/commercial-block/firmware-update-lock-applied
[ -f "$STATE" ] && exit 0

# Never interrupt an active installer. A scheduler or update daemon is safe to
# stop only when none of these installation stages is running.
for unit in swu-core-tv.service swu-service.service bootmode-system-update.service; do
  if systemctl is-active --quiet "$unit"; then
    printf 'Firmware installation active: %s\n' "$unit" >&2
    exit 2
  fi
done

B="$H/backups/firmware-update-lock"
mkdir -p "$B" /run/commercial-block
chmod 700 "$B"
if [ ! -f "$B/original-state" ]; then
  {
    printf 'build='; grep '^BUILD_ID=' /etc/tizen-release | cut -d= -f2-
    printf 'autoupdate='; vconftool get db/menu/support/softwareupdate/autoupdate
    printf 'firmware_service='; vconftool get db/fw-update-service/service_onoff
    if [ -e /mnt/backup/OS_UPGRADE_FLAG ]; then printf 'os_upgrade_flag=present\n'; else printf 'os_upgrade_flag=absent\n'; fi
    for unit in swu-auto-upgrade.timer swu-auto-upgrade.path swu-auto-upgrade.service fw-update-service.path fw-update-service.service fw-usb-update-service.path fw-usb-update-service.service vdsystem-update-manager.timer vdsystem-update-manager.service; do
      printf '%s ' "$unit"
      systemctl is-active "$unit" 2>/dev/null || :
      printf 'unitmask:%s=' "$unit"
      systemctl is-enabled "$unit" 2>/dev/null || :
    done
  } > "$B/original-state.tmp"
  chmod 600 "$B/original-state.tmp"
  mv "$B/original-state.tmp" "$B/original-state"
fi

# Samsung's own SWU service checks that this persistent flag is absent.
touch /mnt/backup/OS_UPGRADE_FLAG
chmod 644 /mnt/backup/OS_UPGRADE_FLAG
vconftool set -f -t int db/menu/support/softwareupdate/autoupdate 1
vconftool set -f -t int db/fw-update-service/service_onoff 0

# Runtime masks avoid altering vendor unit files. Reapply after every boot.
for unit in swu-auto-upgrade.timer swu-auto-upgrade.path fw-update-service.path fw-usb-update-service.path vdsystem-update-manager.timer; do
  systemctl mask --runtime "$unit"
  systemctl stop "$unit"
done
for unit in swu-auto-upgrade.service fw-update-service.service fw-usb-update-service.service vdsystem-update-manager.service; do
  systemctl mask --runtime "$unit"
  systemctl stop "$unit"
done
systemctl reset-failed swu-auto-upgrade.service vdsystem-update-manager.service || :
touch "$STATE"
printf 'Firmware update lock applied\n'
