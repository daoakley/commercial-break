#!/bin/sh
# One attempt per systemd invocation. systemd cleans the entire process group
# before restarting; this prevents orphaned capture/render/navigation helpers.
set -u
umask 077
H=${CB_HOME:-/opt/usr/home/owner/commercial-block}
S=${CB_STATE:-/run/commercial-block}
DOTNET=${CB_DOTNET:-/usr/bin/dotnet}
LIMIT=${CB_STALL_SECONDS:-45}
TICK=${CB_POLL_SECONDS:-2}
mkdir -p "$S" "$H/diagnostics"
chmod 700 "$S" "$H/diagnostics"
exec 9>"$S/supervisor.lock"
flock -n 9 || exit 0
uptime_s() { read -r up rest </proc/uptime; echo "${up%%.*}"; }
log() {
 f="$H/diagnostics/recovery.jsonl"
 if [ -f "$f" ] && [ "$(wc -c <"$f")" -ge 65536 ]; then
  [ ! -f "$f.1" ] || mv -f "$f.1" "$f.2"
  mv -f "$f" "$f.1"
 fi
 available=0; swapfree=0
 while read -r key value rest; do
  case "$key" in MemAvailable:) available=$value;; SwapFree:) swapfree=$value;; esac
 done </proc/meminfo
 printf '{"at":%s,"kind":"%s","pid":%s,"code":%s,"age":%s,"memoryAvailableKiB":%s,"swapFreeKiB":%s}\n' "$(date +%s)" "$1" "${child:-0}" "${2:-0}" "${3:-0}" "$available" "$swapfree" >>"$f"
}
# Cool down repeated failures, but retry indefinitely. State is RAM-only.
now=$(uptime_s); previous=0; failures=0; count=0
if [ -f "$S/restart-state" ]; then read -r previous failures count <"$S/restart-state"; fi
case "$previous:$failures:$count" in *[!0-9:]*|::*|*::*) previous=0;failures=0;count=0;; esac
if [ "$count" -gt 0 ] && [ $((now-previous)) -lt 120 ]; then failures=$((failures+1)); else failures=0; fi
[ "$failures" -le 5 ] || failures=5
count=$((count+1))
printf '%s %s %s\n' "$now" "$failures" "$count" >"$S/restart-state"
delay=0
if [ "$failures" -gt 0 ]; then delay=$((2 << failures)); [ "$delay" -le 60 ] || delay=60; fi
if [ "$delay" -gt 0 ]; then log cooldown "$delay"; sleep "$delay"; fi
rm -f "$S/engine-health"
# No unbounded console logs or accidental credential-bearing exceptions.
"$DOTNET" "$H/CommercialBlock.dll" </dev/null >/dev/null 2>&1 9>&- &
child=$!; started=$(uptime_s)
printf '{"supervisorPid":%s,"enginePid":%s,"starts":%s,"stallSeconds":%s,"cooldownSeconds":%s}\n' "$$" "$child" "$count" "$LIMIT" "$delay" >"$S/supervisor.json.tmp"
mv -f "$S/supervisor.json.tmp" "$S/supervisor.json"
log start
trap 'log stopped; exit 1' TERM INT
while kill -0 "$child" 2>/dev/null; do
 sleep "$TICK"
 now=$(uptime_s); hp=0; beat=$started
 if [ -f "$S/engine-health" ]; then read -r hp beat <"$S/engine-health"; fi
 case "$hp:$beat" in *[!0-9:]*|:*) hp=0;beat=$started;; esac
 [ "$hp" = "$child" ] || beat=$started
 age=$((now-beat))
 if [ "$age" -gt "$LIMIT" ]; then log stalled 0 "$age"; kill -KILL "$child" 2>/dev/null || :; break; fi
done
wait "$child"; code=$?
log exit "$code"
# Parent service performs owned-control release and terminates remaining helpers.
exit 1
