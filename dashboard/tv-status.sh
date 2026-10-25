for fd in 3 4 5 6 7 8 9; do eval "exec $fd>&-"; done
umask 077
S=/run/codex-commercial-muter
F=/run/cb-study-__SID__.json
R=/run/cb-study-__SID__.reply
trap 'rm -f "$F" "$R"' EXIT
end=$(( $(date +%s) + 3630 ))
failures=0
while [ "$(date +%s)" -lt "$end" ]; do
 now=$(date +%s)
 cover=false
 paused=false
 if [ -e "$S/overlay-pause" ] || [ -e "$S/overlay-paused-ack" ]; then paused=true; fi
 pid=$(cat "$S/overlay-pid" 2>/dev/null)
 lease=$(stat -c %Y "$S/overlay-lease" 2>/dev/null)
 case "$pid:$lease" in *[!0-9:]*|:|:*|*:) ;; *)
  if kill -0 "$pid" 2>/dev/null && [ "$paused" = false ] && [ $((now-lease)) -ge 0 ] && [ $((now-lease)) -le 50 ]; then
   case "$(tr '\000' ' ' < /proc/$pid/cmdline 2>/dev/null)" in *CommercialOverlayProbe.dll*) cover=true ;; esac
  fi ;;
 esac
 heartbeat=$(cat "$S/heartbeat" 2>/dev/null)
 case "$heartbeat" in ''|*[!0-9]*) age=-1 ;; *) age=$((now-heartbeat));; esac
 printf '{"session_id":"__SID__","tv_unix_seconds":%s,"cover_active":%s,"paused":%s,"heartbeat_age_seconds":%s}' "$now" "$cover" "$paused" "$age" > "$F"
 if curl -sS --connect-timeout 1 --max-time 1 -K __CONFIG__ --data-binary @"$F" > "$R" 2>/dev/null; then
   failures=0
   [ "$(cat "$R")" = OK ] || break
 else
   failures=$((failures+1))
   [ "$failures" -lt 3 ] || break
 fi
 sleep 1
done
