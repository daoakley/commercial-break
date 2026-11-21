#!/bin/sh
# Restore the TV state saved by firmware-update-lock.sh.
set -eu
[ "$(id -u)" = 0 ] || exit 1
H=${CB_HOME:-/opt/usr/home/owner/commercial-block}
B="$H/backups/firmware-update-lock"
test -f "$B/original-state"
test -f "$B/commercial-break-engine.service.before"

read_value() {
  sed -n "s/^$1=.*value = \([0-9][0-9]*\) .*/\1/p" "$B/original-state" | head -1
}
AUTO=$(read_value autoupdate)
FW=$(read_value firmware_service)
case "$AUTO:$FW" in 0:0|0:1|1:0|1:1) :;; *) exit 2;; esac
FLAG=$(sed -n 's/^os_upgrade_flag=//p' "$B/original-state" | head -1)
case "$FLAG" in present|absent) :;; *) exit 2;; esac

rm -f "$H/firmware-update-lock-enabled" /run/commercial-block/firmware-update-lock-applied
for unit in swu-auto-upgrade.timer swu-auto-upgrade.path swu-auto-upgrade.service fw-update-service.path fw-update-service.service fw-usb-update-service.path fw-usb-update-service.service vdsystem-update-manager.timer vdsystem-update-manager.service; do
  ORIGINAL_MASK=$(sed -n "s/^unitmask:$unit=//p" "$B/original-state" | head -1)
  case "$ORIGINAL_MASK" in masked|masked-runtime) :;; *) systemctl unmask --runtime "$unit";; esac
done
vconftool set -f -t int db/menu/support/softwareupdate/autoupdate "$AUTO"
vconftool set -f -t int db/fw-update-service/service_onoff "$FW"
if [ "$FLAG" = absent ]; then rm -f /mnt/backup/OS_UPGRADE_FLAG; else touch /mnt/backup/OS_UPGRADE_FLAG; fi

cp -p "$B/commercial-break-engine.service.before" "$H/commercial-break-engine.service"
cp -p "$H/commercial-break-engine.service" /run/systemd/system/commercial-break-engine.service
systemctl daemon-reload

# Recreate only the units recorded as active before the lock.
for unit in swu-auto-upgrade.timer swu-auto-upgrade.path swu-auto-upgrade.service fw-update-service.path fw-update-service.service fw-usb-update-service.path fw-usb-update-service.service vdsystem-update-manager.timer vdsystem-update-manager.service; do
  if grep -q "^$unit active$" "$B/original-state"; then systemctl start "$unit"; fi
done
printf 'Original firmware update state restored\n'
