"""Small, stateless-on-disk vision classifier and conservative mute policy."""

import base64
import hashlib
import hmac
import json
import os
import statistics
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_FRAME_BYTES = 1_000_000
MIN_CONFIDENCE = 0.70
SINGLE_FRAME_AD_CONFIDENCE = 0.90
STALE_MUTE_SECONDS = 60


@dataclass
class Verdict:
    label: str
    confidence: float = 0.0
    program: str = ""
    evidence: str = ""
    program_changed: bool = False


@dataclass
class TVState:
    app: str = ""
    title: str = ""
    program: str = ""
    first_program_seen_at: float = 0.0
    ad_candidate_at: float = 0.0
    ad_starts: list = field(default_factory=list)
    last_ad_end_at: float = 0.0
    recent_observations: list = field(default_factory=list)
    switch_streak: int = 0
    previous_hash: str = ""
    ad_streak: int = 0
    program_streak: int = 0
    muted_by_detector: bool = False
    last_ad_at: float = 0.0
    last_verdict: str = "uncertain"
    model_unavailable: bool = False
    updated_at: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


SYSTEM_PROMPT = """You classify ONE television screenshot as program, ad, or uncertain.
Use visible evidence and the supplied viewing context. A logo, score graphic,
or sponsorship inside the program is not by itself a commercial. An abrupt switch
from the established program to a product/service pitch is strong ad evidence.
Black, loading, menus, and ambiguous frames are uncertain. Do not guess.
If a frame is clearly a different show or channel than the known program,
classify it as program, not as an ad merely because the scene changed, and set
program_changed to true. A normal cut within the same show is not a change.
Respond with exactly one JSON object containing label (ad|program|uncertain),
confidence (0..1), program (stable description including show/channel if visible),
evidence (one short sentence), and program_changed (boolean)."""


class VisionClient:
    def __init__(self):
        self.url = os.getenv("VISION_SERVICE_URL", "").strip()
        self.token = os.getenv("VISION_SERVICE_TOKEN", "").strip()

    @property
    def configured(self):
        return self.url.startswith(("http://", "https://"))

    def classify(self, png, context):
        if not self.configured:
            return Verdict("uncertain", evidence="vision service is not configured")
        payload = {"image_png_base64": base64.b64encode(png).decode("ascii"),
                   "context": context, "instructions": SYSTEM_PROMPT}
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(
            self.url, json.dumps(payload).encode("utf-8"), headers, method="POST"
        )
        with urllib.request.urlopen(request, timeout=34) as response:
            result = json.load(response)
        label = str(result.get("label", "uncertain")).lower()
        if label not in {"ad", "program", "uncertain"}:
            label = "uncertain"
        confidence = max(0.0, min(1.0, float(result.get("confidence", 0))))
        return Verdict(label, confidence, str(result.get("program", ""))[:180],
                       str(result.get("evidence", ""))[:240],
                       result.get("program_changed") is True)


class Detector:
    def __init__(self, vision=None, clock=None):
        self.vision = vision or VisionClient()
        self.clock = clock or time.time
        self.states = {}
        self.states_lock = threading.Lock()

    def state(self, tv_id):
        with self.states_lock:
            return self.states.setdefault(tv_id, TVState())

    def next_interval(self, tv_id):
        state = self.state(tv_id)
        now = self.clock()
        with state.lock:
            if state.model_unavailable:
                return 15
            if state.muted_by_detector or state.ad_streak or state.program_streak == 1:
                return 2
            if state.last_verdict == "uncertain":
                return 3
            starts = state.ad_starts
            if len(starts) >= 3:
                gaps = [b - a for a, b in zip(starts, starts[1:])]
                cadence = statistics.median(gaps)
                drift = statistics.median(abs(gap - cadence) for gap in gaps)
                if 60 <= cadence <= 1800 and drift <= cadence * .25:
                    expected = starts[-1] + cadence
                    if expected - 60 <= now <= expected + 90:
                        return 3
            if state.last_ad_end_at and now - state.last_ad_end_at < 60:
                return 8
            return 5

    def process(self, tv_id, png, context):
        state = self.state(tv_id)
        now = self.clock()
        with state.lock:
            app = context.get("app", "")
            title = context.get("title", "")
            if state.app and (app != state.app or (title and state.title and title != state.title)):
                state.app = app
                state.title = title
                state.program = ""
                state.first_program_seen_at = 0.0
                state.ad_candidate_at = 0.0
                state.ad_starts.clear()
                state.last_ad_end_at = 0.0
                state.recent_observations.clear()
                state.switch_streak = 0
                state.previous_hash = ""
                state.ad_streak = state.program_streak = 0
                state.muted_by_detector = False
                state.model_unavailable = False
                state.updated_at = now
                return "UNMUTE", Verdict("uncertain", evidence="app changed")
            state.app = app
            if title:
                state.title = title
            digest = hashlib.sha256(png).hexdigest()
            if digest == state.previous_hash:
                if state.muted_by_detector and now - state.last_ad_at > STALE_MUTE_SECONDS:
                    state.muted_by_detector = False
                    return "UNMUTE", Verdict("uncertain", evidence="stale frame")
                return ("MUTE" if state.muted_by_detector else "UNMUTE"), Verdict("uncertain", evidence="unchanged frame")
            state.previous_hash = digest
            model_context = dict(context, known_program=state.program,
                                 seconds_since_last_ad=round(now - state.last_ad_at) if state.last_ad_at else None,
                                 previous_label=state.last_verdict,
                                 program_first_observed_at_utc=(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(state.first_program_seen_at)) if state.first_program_seen_at else None),
                                 confirmed_ad_breaks_utc=[time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value)) for value in state.ad_starts],
                                 recent_observations=state.recent_observations[-6:])
            try:
                verdict = self.vision.classify(png, model_context)
                state.model_unavailable = False
            except Exception as exc:
                verdict = Verdict("uncertain", evidence="model error: " + type(exc).__name__)
                state.model_unavailable = True
            state.updated_at = now
            previous_label = state.last_verdict
            state.last_verdict = verdict.label
            if state.model_unavailable:
                state.muted_by_detector = False
                state.ad_streak = state.program_streak = 0
                return "UNMUTE", verdict
            state.recent_observations.append({
                "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "label": verdict.label,
                "confidence": round(verdict.confidence, 2),
                "evidence": verdict.evidence[:160],
            })
            state.recent_observations = state.recent_observations[-6:]
            confident = verdict.confidence >= MIN_CONFIDENCE
            if verdict.label == "program" and confident and verdict.program_changed and state.program:
                state.switch_streak += 1
                if state.switch_streak >= 2 or state.muted_by_detector:
                    state.program = verdict.program
                    state.first_program_seen_at = now
                    state.ad_candidate_at = state.last_ad_at = state.last_ad_end_at = 0.0
                    state.ad_starts.clear()
                    state.ad_streak = 0
                    state.program_streak = 1
                    state.muted_by_detector = False
                    state.switch_streak = 0
                    state.recent_observations = state.recent_observations[-1:]
                    return "UNMUTE", verdict
            else:
                state.switch_streak = 0
            if verdict.label == "ad" and confident:
                if state.ad_streak == 0:
                    state.ad_candidate_at = now
                state.ad_streak += 1
                state.program_streak = 0
                state.last_ad_at = now
            elif verdict.label == "program" and confident:
                state.program_streak += 1
                state.ad_streak = 0
                if not state.first_program_seen_at:
                    state.first_program_seen_at = now
                if verdict.program:
                    state.program = verdict.program
            else:
                state.ad_streak = state.program_streak = 0

            strong_ad_against_known_program = (
                verdict.label == "ad" and confident
                and verdict.confidence >= SINGLE_FRAME_AD_CONFIDENCE
                and bool(state.program)
                and previous_label == "program"
            )
            if not state.muted_by_detector and (state.ad_streak >= 2 or strong_ad_against_known_program):
                state.muted_by_detector = True
                if not state.ad_starts or state.ad_candidate_at - state.ad_starts[-1] > 30:
                    state.ad_starts.append(state.ad_candidate_at)
                    state.ad_starts = state.ad_starts[-8:]
                return "MUTE", verdict
            if state.muted_by_detector and state.program_streak >= 2:
                state.muted_by_detector = False
                state.last_ad_end_at = now
                return "UNMUTE", verdict
            if state.muted_by_detector and now - state.last_ad_at > STALE_MUTE_SECONDS:
                state.muted_by_detector = False
                return "UNMUTE", verdict
            return ("MUTE" if state.muted_by_detector else "UNMUTE"), verdict


class Handler(BaseHTTPRequestHandler):
    detector = Detector()
    token = os.getenv("FRAME_TOKEN", "")

    def log_message(self, fmt, *args):
        # Avoid logging paths, authorization, content, or viewing context.
        pass

    def _authorized(self):
        header = self.headers.get("Authorization", "")
        return bool(self.token) and hmac.compare_digest(header, "Bearer " + self.token)

    def _reply(self, code, body, content_type="text/plain"):
        body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, json.dumps({"ok": True, "vision_configured": self.detector.vision.configured}), "application/json")
        else:
            self._reply(404, "not found")

    def do_POST(self):
        if self.path != "/v1/frame":
            self._reply(404, "not found")
            return
        if not self._authorized():
            self._reply(401, "unauthorized")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if size < 33 or size > MAX_FRAME_BYTES:
            self._reply(413, "invalid frame size")
            return
        png = self.rfile.read(size)
        if png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
            self._reply(415, "PNG required")
            return
        context = {
            "app": self.headers.get("X-TV-App", "")[:120],
            "channel": self.headers.get("X-TV-Channel", "")[:120],
            "title": self.headers.get("X-TV-Title", "")[:180],
            "local_time": self.headers.get("X-TV-Local-Time", "")[:80],
        }
        tv_id = self.headers.get("X-TV-ID", "frame-tv")[:80]
        action, verdict = self.detector.process(tv_id, png, context)
        next_interval = self.detector.next_interval(tv_id)
        print(f"decision={action} label={verdict.label} confidence={verdict.confidence:.2f}", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(action)))
        self.send_header("X-Frame-Label", verdict.label)
        self.send_header("X-Frame-Confidence", f"{verdict.confidence:.2f}")
        self.send_header("X-Next-Capture-Seconds", str(next_interval))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(action.encode("ascii"))


def main():
    if len(os.getenv("FRAME_TOKEN", "")) < 24:
        raise SystemExit("FRAME_TOKEN must be at least 24 characters")
    host = os.getenv("LISTEN_HOST", "0.0.0.0")
    port = int(os.getenv("LISTEN_PORT", "8080"))
    print(f"listening on {host}:{port}; vision configured={Handler.detector.vision.configured}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
