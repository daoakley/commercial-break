"""One bounded, read-only TV capture at a time. No secrets or frames on disk."""
import base64
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import threading
import time
import uuid

BASE = Path(__file__).resolve().parents[2]
COMMAND = r'''
umask 077
stage=/home/owner/share/tmp/sdk_tools
S=/run/codex-commercial-muter
image="$stage/dashboard-current-screen.png"
rm -f "$image"
now=$(date +%s)
app=$(/usr/bin/vconftool get memory/appfw/current_fullscreen_appid 2>/dev/null | awk -F 'value = ' '{print $2}' | cut -d ' ' -f 1 | tr -cd 'A-Za-z0-9._-')
heartbeat=$(cat "$S/heartbeat" 2>/dev/null)
case "$heartbeat" in ''|*[!0-9]*) age=-1 ;; *) age=$((now-heartbeat));; esac
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
muted=null
case "$(/usr/bin/busctl --system --timeout=1 call org.tizen.speakermanager /Org/Tizen/SpeakerManagerInternal org.tizen.speakermanager GetSpeakerMute 2>/dev/null)" in
 'ii 1 0') muted=true;; 'ii 0 0') muted=false;;
esac
echo DATA_BEGIN
printf '{"observed_unix":%s,"app":"%s","heartbeat_age_seconds":%s,"cover_active":%s,"capture_pause_active":%s,"muted":%s}' "$now" "$app" "$age" "$cover" "$paused" "$muted"
echo
echo DATA_END
# Independent name and no pause/ack paths: leave the visible card and playback alone.
CAPTURE_FILE_BASENAME=dashboard-current-screen CAPTURE_OVERLAY_PAUSE_FILE= CAPTURE_OVERLAY_ACK_FILE= LD_PRELOAD=/lib/libcapi-system-info.so.0:/run/libtzcapturec-probe.so /usr/bin/dotnet "$stage/DisplayCaptureProbe.dll" >/dev/null 2>&1 &
capture_pid=$!
(sleep 12; kill "$capture_pid" 2>/dev/null) >/dev/null 2>&1 &
guard=$!
wait "$capture_pid"
kill "$guard" 2>/dev/null
wait "$guard" 2>/dev/null
if [ -s "$image" ]; then
 echo IMAGE_BEGIN
 base64 "$image"
 echo IMAGE_END
fi
rm -f "$image"
'''


def stdout_text(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'stdout' and isinstance(child, str):
                yield child
            elif isinstance(child, (dict, list)):
                yield from stdout_text(child)
    elif isinstance(value, list):
        for child in value:
            yield from stdout_text(child)


def decode_capture(raw):
    text = '\n'.join(stdout_text(json.loads(raw)))
    payload = text.split('IMAGE_BEGIN', 1)[1].split('IMAGE_END', 1)[0]
    png = base64.b64decode(''.join(payload.split()), validate=True)
    if not 24 <= len(png) <= 2_000_000 or png[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid capture')
    width, height = struct.unpack('>II', png[16:24])
    if not (1 <= width <= 4096 and 1 <= height <= 2160):
        raise ValueError('Invalid dimensions')
    data = json.loads(text.split('DATA_BEGIN', 1)[1].split('DATA_END', 1)[0])
    data = {key: data.get(key) for key in ('observed_unix', 'app', 'heartbeat_age_seconds',
                                         'cover_active', 'capture_pause_active', 'muted')}
    return png, data, width, height


def capture_tv(tv_host):
    args = [os.environ.get('TVROOT', 'samsung-tv-root'),
            '--sdb', os.environ.get('SDB', 'sdb'), '-o', 'json',
            'archive-root', 'root', tv_host, '--command', COMMAND, '--command-timeout', '18']
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    try:
        output, _ = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise TimeoutError() from None
    return decode_capture(output)


class ScreenCapture:
    def __init__(self, tv_host, runner=capture_tv):
        self.tv_host, self.runner = tv_host, runner
        self.lock = threading.Lock()
        self.state = {'phase': 'idle', 'image_id': None}
        self.image = None

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def image_bytes(self):
        with self.lock:
            return self.image

    def start(self):
        with self.lock:
            if self.state['phase'] == 'capturing':
                return dict(self.state)
            if time.time() - self.state.get('finished_unix', 0) < 2:
                return dict(self.state)
            self.state.update(phase='capturing', started_unix=time.time(), error=None)
            threading.Thread(target=self._run, daemon=True).start()
            return dict(self.state)

    def _run(self):
        started = time.monotonic()
        try:
            png, data, width, height = self.runner(self.tv_host)
            with self.lock:
                self.image = png
                self.state.update(phase='ready', image_id=uuid.uuid4().hex,
                    captured_unix=time.time(), tv=data, width=width, height=height,
                    duration_seconds=round(time.monotonic()-started, 1))
        except Exception as error:
            with self.lock:
                self.state.update(phase='error', error=(
                    'The TV did not respond within 30 seconds. You can retry.' if isinstance(error, TimeoutError)
                    else 'Could not capture the TV. Check that it is on and its temporary capture connection is available.'))
        finally:
            with self.lock:
                self.state['finished_unix'] = time.time()
