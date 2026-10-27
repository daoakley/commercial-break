#!/bin/sh
# Independent guard; only releases controls owned by this isolated project.
S=/run/commercial-block
release_owned() {
 rm -f "$S/overlay-lease" "$S/overlay-pause"
 if [ -f "$S/owned-mute" ]; then
  /usr/bin/busctl --system --timeout=2 call org.tizen.speakermanager /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager SetSpeakerMute b false >/dev/null 2>&1 && rm -f "$S/owned-mute"
 fi
}
while :; do
 sleep 1
 now=$(date +%s)
 last=$(cat "$S/heartbeat" 2>/dev/null || echo 0)
 if [ $(( now - last )) -gt 12 ]; then
  release_owned
  [ -f "$S/owned-mute" ] || exit 0
 fi
 lease=$(cat "$S/overlay-lease" 2>/dev/null || echo 0)
 case "$lease" in ''|*[!0-9]*) lease=0;; esac
 if [ "$lease" -gt 0 ] && [ $(( now * 1000 - lease )) -ge 8000 ]; then
  release_owned
 fi
done
