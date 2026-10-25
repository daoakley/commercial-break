#!/bin/sh
# Temporary, read-only 10-second PCM chunks for a bounded local study.
set -u
umask 077
: "${FRAME_TOKEN:?}"
: "${AUDIO_STUDY_URL:?Set the private receiver URL ending in /pcm}"
limit=${AUDIO_STUDY_CHUNKS:-120}
i=0
previous_upload=
while [ "$i" -lt "$limit" ]; do
  tmp=/run/codex-commercial-muter/audio-study-$i.raw
  started=$(date +%s)
  if arecord -D hw:0,5 -f S16_LE -r 48000 -c 2 -d 10 -t raw "$tmp" >/dev/null 2>&1; then
    if [ -n "$previous_upload" ]; then wait "$previous_upload" || true; fi
    (curl -fsS --connect-timeout 2 --max-time 15 -X POST \
       -H "Authorization: Bearer $FRAME_TOKEN" \
       -H "Content-Type: application/octet-stream" \
       -H "X-Capture-Start-Unix: $started" \
       --data-binary "@$tmp" "$AUDIO_STUDY_URL" >/dev/null 2>&1 || true
     rm -f "$tmp") &
    previous_upload=$!
  else
    rm -f "$tmp"
  fi
  i=$((i + 1))
done
if [ -n "$previous_upload" ]; then wait "$previous_upload" || true; fi
