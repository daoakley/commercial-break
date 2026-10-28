#!/bin/sh
# Run through stdin in your authorized TV root shell; not from the Mac shell.
set -eu
umask 077
[ "$(id -u)" = 0 ] || { echo 'Root required'; exit 1; }
[ -x /usr/bin/dotnet ] || { echo 'TV .NET runtime unavailable'; exit 1; }
H=/opt/usr/home/owner/commercial-block
P=/run/commercial-break-install
ARCHIVE=/home/owner/share/tmp/sdk_tools/commercial-break-engine.tar.gz
[ ! -e "$P" ] || { echo 'Staging path exists; inspect it before retrying'; exit 1; }
mkdir -p "$P" "$H/backups"
chmod 700 "$H" "$H/backups"
tar -xzf "$ARCHIVE" -C "$P"
for f in CommercialBlock.dll AcrFrameProbe.dll CommercialOverlayProbe.dll NavigationObserver.dll libtzcapturec-probe.so device.json control.curl engine-supervisor.sh release-owned.sh commercial-break-engine.service; do
 [ -s "$P/$f" ] || { echo "Missing bundle file: $f"; exit 1; }
done
# Do not overlap an older manually launched engine.
if ! systemctl is-active --quiet commercial-break-engine.service; then
 for proc in /proc/[0-9]*; do
  [ -r "$proc/cmdline" ] || continue
  case "$(tr '\000' ' ' <"$proc/cmdline")" in *"$H/CommercialBlock.dll"*) echo 'Stop the unmanaged engine before installing'; exit 1;; esac
 done
fi
# Updating with a new token would leave the old installed controller unusable.
if [ -f "$H/device.json" ] && ! cmp -s "$H/device.json" "$P/device.json"; then
 echo 'Existing device.json differs: rebuild with the exact installed private configuration'; exit 1
fi
B="$H/backups/release-$(date +%Y%m%d-%H%M%S)"
mkdir "$B"
for f in "$H"/*.dll "$H"/*.json "$H"/*.sh "$H"/*.service "$H"/*.so "$H"/control.curl; do
 [ ! -f "$f" ] || cp -p "$f" "$B/"
done
[ ! -d "$H/themes" ] || cp -R "$H/themes" "$B/themes"
if systemctl is-active --quiet commercial-break-engine.service; then systemctl stop commercial-break-engine.service; fi
cp -R "$P/." "$H/"
# On/Off, appearance and debug settings are intentionally absent from the bundle.
[ -f "$H/enabled" ] || printf '0\n' >"$H/enabled"
cp "$H/commercial-break-engine.service" /run/systemd/system/
systemctl daemon-reload
systemctl start commercial-break-engine.service
systemctl show commercial-break-engine.service -p ActiveState -p SubState -p MainPID
printf 'Backup: %s\n' "$B"
# Only this fixed installation staging path is removed.
rm -rf "$P"
