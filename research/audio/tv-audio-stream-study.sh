#!/bin/sh
# Bounded continuous PCM tap, uploaded as short private slices. Never mutes.
set -u
umask 077
: "${FRAME_TOKEN:?}"
: "${AUDIO_STUDY_URL:?Set the private receiver URL ending in /pcm}"
limit=${AUDIO_STUDY_CHUNKS:-300}
chunk_seconds=${AUDIO_STUDY_CHUNK_SECONDS:-2}
case "$chunk_seconds" in 2|3) ;; *) exit 2 ;; esac
bytes=$((48000 * 4 * chunk_seconds))
duration=$((limit * chunk_seconds))

arecord -D hw:0,5 -f S16_LE -r 48000 -c 2 -d "$duration" -t raw - 2>/dev/null |
(
  i=0
  pid0= pid1= pid2=
  while [ "$i" -lt "$limit" ]; do
    tmp=/run/codex-commercial-muter/audio-stream-$i.raw
    started=$(date +%s)
    head -c "$bytes" > "$tmp" || break
    actual=$(wc -c < "$tmp")
    if [ "$actual" -ne "$bytes" ]; then rm -f "$tmp"; break; fi
    slot=$((i % 3))
    case "$slot" in
      0) if [ -n "$pid0" ]; then wait "$pid0" || true; fi ;;
      1) if [ -n "$pid1" ]; then wait "$pid1" || true; fi ;;
      2) if [ -n "$pid2" ]; then wait "$pid2" || true; fi ;;
    esac
    (curl -fsS --connect-timeout 1 --max-time 5 -X POST \
       -H "Authorization: Bearer $FRAME_TOKEN" \
       -H "Content-Type: application/octet-stream" \
       -H "X-Capture-Start-Unix: $started" \
       --data-binary "@$tmp" "$AUDIO_STUDY_URL" >/dev/null 2>&1 || true
     rm -f "$tmp") &
    case "$slot" in 0) pid0=$! ;; 1) pid1=$! ;; 2) pid2=$! ;; esac
    i=$((i + 1))
  done
  if [ -n "$pid0" ]; then wait "$pid0" || true; fi
  if [ -n "$pid1" ]; then wait "$pid1" || true; fi
  if [ -n "$pid2" ]; then wait "$pid2" || true; fi
)
