"""Private, observation-only human labels for Commercial Break.

Read-only TV capture and detector status; human labels never control mute.
"""
import argparse
import json
import os
from pathlib import Path
import threading
import time
import uuid
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = Path(__file__).resolve().parent
KINDS = {"ad", "program", "uncertain", "channel_changed", "undo", "end", "extend"}


class Study:
    def __init__(self, directory, clock=time.time, monotonic=time.monotonic, resume_active=False):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.path = self.directory / "labels.jsonl"
        self.clock, self.monotonic = clock, monotonic
        self.lock = threading.RLock()
        self.rows = []
        self.active = None
        self.deadline = None
        self.observer = None
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                try:
                    self.rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            # A restart never silently resumes an attention window.
            open_sessions = {}
            for row in self.rows:
                if row["kind"] == "start":
                    open_sessions[row["session_id"]] = row
                elif row["kind"] == "end":
                    open_sessions.pop(row["session_id"], None)
            for sid in open_sessions:
                old = open_sessions[sid]
                remaining = self.window_end_ms(old)/1000-self.clock()
                if resume_active and 0 < remaining <= 3600:
                    self.active = old
                    self.deadline = self.monotonic()+remaining
                    continue
                self.append("end", sid, reason="server_restart", coverage_uncertain=True)

    def append(self, kind, session_id, **extra):
        row = dict(id=uuid.uuid4().hex, session_id=session_id, kind=kind,
                   received_unix_ms=round(self.clock() * 1000), **extra)
        with self.path.open("a") as file:
            self.path.chmod(0o600)
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        self.rows.append(row)
        return row

    def window_end_ms(self, start):
        extension = sum(r.get('added_seconds', 0) for r in self.rows
                        if r['session_id']==start['session_id'] and r['kind']=='extend')
        return start['received_unix_ms']+(start.get('duration_seconds',300)+extension)*1000

    def expire(self):
        if self.active and self.monotonic() >= self.deadline:
            self.append("end", self.active["session_id"], reason="window_elapsed",
                        effective_unix_ms=self.window_end_ms(self.active))
            self.active = None
            self.deadline = None

    def snapshot(self):
        with self.lock:
            self.expire()
            active = self.active
            sid = active["session_id"] if active else (self.rows[-1]["session_id"] if self.rows else None)
            rows = [r for r in self.rows if r["session_id"] == sid]
            undone = {r.get("target_id") for r in rows if r["kind"] == "undo"}
            state = active["initial_state"] if active else "idle"
            if active:
                for row in rows:
                    if row["id"] in undone:
                        continue
                    if row["kind"] in {"ad", "program", "uncertain", "channel_changed"}:
                        state = "uncertain" if row["kind"] == "channel_changed" else row["kind"]
            start = next((r for r in rows if r['kind'] == 'start'), {})
            profile_id = start.get('profile_id')
            profile_starts = [r for r in self.rows if r['kind'] == 'start' and profile_id and r.get('profile_id') == profile_id]
            profile_sessions = {r['session_id'] for r in profile_starts}
            profile_rows = [r for r in self.rows if r['session_id'] in profile_sessions] if profile_sessions else rows
            profile_undone = {r.get('target_id') for r in profile_rows if r['kind'] == 'undo'}
            samples, observer_status = self.observer.snapshot(sid) if self.observer else ([], 'TV status not connected')
            if self.observer and profile_sessions:
                samples = sorted([sample for session in profile_sessions for sample in self.observer.snapshot(session)[0]], key=lambda s:s['received_unix_ms'])
            active_view = dict(active, planned_end_unix_ms=self.window_end_ms(active)) if active else None
            return dict(active=active_view, remaining_seconds=max(0, self.deadline-self.monotonic()) if active else 0,
                        state=state, events=rows[-30:], undone=list(undone),
                        chart_events=profile_rows, chart_undone=list(profile_undone), cover_samples=samples,
                        observer_status=observer_status,
                        channel_context=dict(source=start.get('source', ''), channel=start.get('channel', ''),
                                             show=start.get('show', ''), profile_id=profile_id,
                                             show_start_ms=start.get('show_start_ms'), identity_source='Viewer supplied'),
                        server_unix_ms=round(self.clock()*1000))

    def action(self, data):
        with self.lock:
            self.expire()
            kind = data.get("kind")
            # Idempotency: a retried request must not add a duplicate click.
            request_id = str(data.get("request_id", ""))[:64]
            if request_id and any(r.get("request_id") == request_id for r in self.rows):
                return self.snapshot()
            timing = {"request_id": request_id}
            for key in ("client_unix_ms", "client_monotonic_ms"):
                value = data.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 1e15:
                    timing[key] = value
            if kind == "start":
                if self.active:
                    raise ValueError("An observation window is already running.")
                duration = data.get('duration_seconds',900)
                if isinstance(duration,bool) or duration not in (300,900,1800):
                    raise ValueError("Choose a 5, 15 or 30 minute window.")
                state = data.get("initial_state")
                if state not in {"program", "ad", "uncertain"}:
                    raise ValueError("Choose what is on screen before starting.")
                source = str(data.get('source', 'YouTube TV'))[:80]
                channel = str(data.get('channel', '')).strip()[:100]
                show = str(data.get('show', '')).strip()[:180]
                prior = next((r for r in reversed(self.rows) if r['kind']=='start'), {})
                same = (source, channel, show) == (prior.get('source'), prior.get('channel'), prior.get('show'))
                interrupted = any(r['session_id']==prior.get('session_id') and r['kind']=='channel_changed' for r in self.rows)
                recent = self.clock()*1000-prior.get('received_unix_ms', 0) < 12*3600000
                profile_id = (prior.get('profile_id') if same and recent and not interrupted and not data.get('new_show') else None)
                if channel and show and not profile_id:
                    profile_id = uuid.uuid4().hex
                show_start_ms = data.get('show_start_ms')
                if not isinstance(show_start_ms, (int, float)) or not 0 < show_start_ms <= self.clock()*1000+300000:
                    show_start_ms = prior.get('show_start_ms') if profile_id and profile_id==prior.get('profile_id') else None
                self.active = self.append("start", uuid.uuid4().hex,
                    initial_state=state, context=str(data.get("context", ""))[:180],
                    source=source, channel=channel, show=show, profile_id=profile_id,
                    show_start_ms=show_start_ms,
                    duration_seconds=duration, **timing)
                self.deadline = self.monotonic() + duration
                if self.observer:
                    self.observer.launch(self.active['session_id'])
            else:
                if kind not in KINDS:
                    raise ValueError("Unknown marker.")
                if not self.active:
                    raise ValueError("Start an observation window first.")
                sid = self.active["session_id"]
                if kind == 'extend':
                    if self.window_end_ms(self.active)-self.active['received_unix_ms'] >= 3600000:
                        raise ValueError("This window has reached one hour. Start a new window when it ends.")
                    self.append(kind,sid,added_seconds=300,**timing)
                    self.deadline += 300
                elif kind == "undo":
                    undone = {r.get("target_id") for r in self.rows if r["session_id"] == sid and r["kind"] == "undo"}
                    target = next((r for r in reversed(self.rows) if r["session_id"] == sid and
                                   r["kind"] in {"ad", "program", "uncertain", "channel_changed"} and r["id"] not in undone), None)
                    if target is None:
                        raise ValueError("There is no marker to undo.")
                    self.append(kind, sid, target_id=target["id"], **timing)
                elif kind == "end":
                    self.append(kind, sid, reason="viewer_stopped", **timing)
                    self.active = self.deadline = None
                else:
                    self.append(kind, sid, **timing)
            return self.snapshot()


def serve(directory, port, enable_tv_observer=False, resume_active=False, detector_env=None, detector_url='http://127.0.0.1:28471', tv_host=''):
    study = Study(directory, resume_active=resume_active)
    if enable_tv_observer:
        try:
            from tv_observer import TVObserver
            study.observer = TVObserver(study)
            if study.active:
                # The replacement receiver has a new token. Let any previous
                # bounded observer exit on rejection (or three network failures)
                # before launching its replacement. Labels retain their deadline.
                threading.Timer(7, study.observer.launch,
                                args=(study.active['session_id'],)).start()
        except OSError:
            pass  # Observation must never prevent human labels from working.
    from live_status import LiveStatus
    live = LiveStatus(detector_env, detector_url)
    from screen_capture import ScreenCapture
    capture = ScreenCapture(tv_host)
    from native_status import NativeStatus
    native = NativeStatus(tv_host, live)
    authority = f"127.0.0.1:{port}"
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.headers.get("Host") != authority:
                return self.reply(403, {"error": "Use the local panel address."})
            if self.path == "/state":
                return self.reply(200, dict(study.snapshot(), live=live.snapshot(), capture=capture.snapshot(), native=native.snapshot()))
            if self.path == '/latest-frame':
                try:
                    req = urllib.request.Request(detector_url.rstrip('/')+'/v1/latest-frame',
                        headers={'Authorization': 'Bearer '+live.token})
                    with urllib.request.urlopen(req, timeout=2) as response:
                        image = response.read(2_000_001)
                        received = float(response.headers['X-Frame-Received-Unix'])
                        sequence = response.headers.get('X-TV-Frame-Sequence', '')
                    if len(image)>2_000_000 or image[:8]!=b'\x89PNG\r\n\x1a\n':
                        raise ValueError()
                    import base64
                    return self.reply(200, dict(image=base64.b64encode(image).decode(),
                        received_unix=received, sequence=sequence, age_seconds=max(0,time.time()-received)))
                except urllib.error.HTTPError as error:
                    return self.reply(503, {'error': 'No incoming frame is available yet.' if error.code==404 else 'Frame feed unavailable.'})
                except Exception:
                    return self.reply(503, {'error': 'Frame feed unavailable. The detector may be offline.'})
            if self.path.split('?', 1)[0] == '/screen.png':
                image = capture.image_bytes()
                return self.reply(200, image, 'image/png') if image else self.reply(404, {'error': 'No screenshot yet'})
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if self.path not in files:
                return self.reply(404, {"error": "Not found"})
            name, kind = files[self.path]
            self.reply(200, (HERE / name).read_bytes(), kind)

        def do_POST(self):
            if (self.path not in ("/mark", "/capture") or self.headers.get("Host") != authority or
                self.headers.get("Origin") != "http://"+authority or
                self.headers.get("Content-Type") != "application/json"):
                return self.reply(403, {"error": "Local panel requests only."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size < 4096:
                    raise ValueError("Invalid request size.")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Invalid marker.")
                result = capture.start() if self.path == '/capture' else study.action(body)
            except (ValueError, TypeError) as exc:
                return self.reply(400, {"error": str(exc)})
            self.reply(202 if self.path == '/capture' else 200, result)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    def expiry_loop():
        while True:
            time.sleep(.5)
            with study.lock:
                study.expire()
    threading.Thread(target=expiry_loop, daemon=True).start()
    print(f"Labeling panel: http://{authority}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--tv-observer", action="store_true")
    parser.add_argument("--resume-active", action="store_true", help="Planned handoff only; preserve the observation deadline")
    parser.add_argument("--detector-env", type=Path)
    parser.add_argument('--detector-url', default='http://127.0.0.1:28471')
    parser.add_argument('--tv-host', default='')
    args = parser.parse_args()
    os.umask(0o077)
    serve(args.data, args.port, args.tv_observer, args.resume_active, args.detector_env, args.detector_url, args.tv_host)
