#!/bin/sh
# systemd runs this after ALL engine/capture children are stopped, even SIGKILL.
# This complements the eight-second lease guard; never changes user brightness.
S=/run/commercial-block
rm -f "$S/overlay-lease" "$S/overlay-pause" "$S/heartbeat"
if [ -f "$S/owned-mute" ]; then
 /usr/bin/busctl --system --timeout=2 call org.tizen.speakermanager /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager SetSpeakerMute b false >/dev/null 2>&1 && rm -f "$S/owned-mute"
fi
if [ -f "$S/owned-panel-mask" ]; then
 /usr/bin/busctl --system --timeout=2 call org.tizen.tv.avoc /org/tizen/tv/avoc org.tizen.tv.avoc.AvOutputControl SetLfdPanelMute i 0 >/dev/null 2>&1 && rm -f "$S/owned-panel-mask"
fi
