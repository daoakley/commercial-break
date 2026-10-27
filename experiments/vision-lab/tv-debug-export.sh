#!/bin/sh
# Read-only export of the existing debug stream. No capture or playback commands.
# Settings in a root-private directory: upload.curl, destination, expires, start-after.
set -u
umask 077
export_dir=/run/commercial-vision-export
debug_dir=/opt/usr/home/owner/commercial-block/debug-records
control=/opt/usr/home/owner/commercial-block/control.curl
mkdir "$export_dir/lock" 2>/dev/null || exit 0
trap 'rm -f "$export_dir/source.json" "$export_dir/status.json" "$export_dir/guard.json" "$export_dir/list"; rmdir "$export_dir/lock" 2>/dev/null' EXIT
destination=$(cat "$export_dir/destination")
expires=$(cat "$export_dir/expires")
last=$(cat "$export_dir/start-after" 2>/dev/null)
failures=0
while [ "$(date +%s)" -lt "$expires" ]; do
    [ -f "$export_dir/stop" ] && break
    now=$(date +%s)
    app=$(/usr/bin/vconftool get memory/appfw/current_fullscreen_appid 2>/dev/null | awk -F 'value = ' '{print $2}' | cut -d ' ' -f 1 | tr -cd 'A-Za-z0-9._-')
    nav=$(cat /run/commercial-block/navigation 2>/dev/null)
    case "$nav" in ''|*[!0-9]*) nav=0 ;; esac
    generation=
    for process in $(pidof dotnet); do
        case "$(tr '\000' ' ' < /proc/$process/cmdline 2>/dev/null)" in
            *'/CommercialBlock.dll'*) generation="$process-$(awk '{print $22}' /proc/$process/stat 2>/dev/null)"; break ;;
        esac
    done
    [ -n "$generation" ] || { sleep 3; continue; }
    printf '{"observed_unix":%s,"source_app":"%s","navigation_epoch":%s,"generation":"%s"}' "$now" "$app" "$nav" "$generation" > "$export_dir/source.json"
    if ! curl --fail --silent --max-time 2 --config "$control" http://127.0.0.1:18764/status > "$export_dir/status.json"; then sleep 3; continue; fi
    curl --fail --silent --max-time 2 http://127.0.0.1:47791/status > "$export_dir/guard.json" || printf '{}' > "$export_dir/guard.json"
    answer=$(curl --fail --silent --connect-timeout 2 --max-time 5 --config "$export_dir/upload.curl" -F "source=@$export_dir/source.json" -F "status=@$export_dir/status.json" -F "guard=@$export_dir/guard.json" "$destination/tv-state")
    if [ "$answer" = STOP ]; then break; fi
    if [ "$answer" != CONTINUE ]; then failures=$((failures+1)); [ "$failures" -ge 10 ] && break; sleep 3; continue; fi
    failures=0
    ls "$debug_dir"/*.json 2>/dev/null | sort > "$export_dir/list"
    count=0
    while IFS= read -r path; do
        name=${path##*/}
        [ -n "$last" ] && [ "$name" \< "$last" ] && continue
        [ "$name" = "$last" ] && continue
        image=${path%.json}.png
        if [ ! -s "$image" ]; then last=$name; continue; fi
        # JSON is committed after the PNG; both can still be evicted by the TV cap.
        result=$(curl --fail --silent --connect-timeout 2 --max-time 8 --config "$export_dir/upload.curl" -F "record=@$path" -F "image=@$image" "$destination/tv-record")
        [ "$result" = OK ] || break
        last=$name
        count=$((count+1))
        [ "$count" -ge 8 ] && break
    done < "$export_dir/list"
    printf '%s' "$last" > "$export_dir/start-after"
    sleep 2
done
