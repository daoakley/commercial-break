"""Small, stateless-on-disk vision classifier and conservative mute policy."""

import base64
import copy
import hashlib
import hmac
import json
import math
import os
import statistics
import threading
import time
import urllib.request
from dataclasses import dataclass, field, fields
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import sponsored_badge
from local_signals import visual_features, own_card
import zlib
from viewing_context import ViewingContext, CATEGORIES, PRESENTATIONS
from playback_identity import PlaybackIdentity

MAX_FRAME_BYTES = 1_000_000
MIN_CONFIDENCE = 0.70
SINGLE_FRAME_AD_CONFIDENCE = 0.85
POSSIBLE_PROGRAM_CHANGE_CONFIDENCE = 0.60
STRONG_PROGRAM_CHANGE_CONFIDENCE = 0.80
STALE_MUTE_SECONDS = 60


@dataclass
class Verdict:
    label: str
    confidence: float = 0.0
    program: str = ""
    evidence: str = ""
    program_changed: bool = False
    category: str = "unknown"
    presentation: str = "unknown"


@dataclass
class TVState:
    viewing: ViewingContext = field(default_factory=ViewingContext)
    app: str = ""
    channel: str = ""
    title: str = ""
    session: str = ""
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
    capture_obscured: bool = False
    updated_at: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


SYSTEM_PROMPT = """Classify one TV frame as ad, program, or uncertain using the known program and recent observations.
First distinguish the main video from graphics over it. A corner tune-in promotion such as 'ALL NEW Tonight 10/9c' over an ongoing show is in_program_promotion, label program, even when it promotes a DIFFERENT show. This applies to every category, including HGTV renovation/reality shows, sports and news. The scheduled time in a corner banner does not make the underlying video an ad. Use full_screen_ad only when the primary video itself is a standalone commercial or promo; a small banner is never sufficient. When a coherent new show replaces the old one, prefer that current visual evidence over previous ad labels.
A scheduled new show or in-app channel change can occur without a change in app ID or supplied title. The prior known program, earlier ad labels, and a scene unlike the prior show are not ad evidence by themselves. A coherent dramatic, comedic, documentary, sports, or news scene is program even if it is clearly a different show; set program_changed true when a show/channel switch is plausible. A network logo alone is not an ad cue.
Commercials include station promos, trailers, bumpers, and sponsor pitches, but require identifiable promotional intent in the current frame: a product or service pitch, advertiser brand, price, URL, phone number, call to action, or an obvious promo/trailer cue. Use high ad confidence for an unambiguous external pitch; do not require a full banner. Do not label an in-show sponsor bug, sports ticker, news lower third, show title/website, product used within an editorial segment, or ordinary scene cut as an ad just because a brand or text is present. If this frame cannot distinguish a promo from a new show, use uncertain. Black frames, menus, guide, and loading are uncertain. Give calibrated confidence, not automatic 0.95.
The TV may show this project's own cover card: an almost-black full screen with a thin muted-green horizontal line above centered white text reading Commercial Break. It may also include show context, break statistics and a viewing timeline below the title. That card hides the underlying video. Label it uncertain, not ad or program; it is not evidence that a broadcast ad is still playing.
Set program_changed true only when the current frame is labeled program and appears to be a different show. For ad and uncertain labels, always set program_changed false: ads normally look different from the show, and that difference is not a program change.
Use the category expectations and local signals as context, not as proof: brightness, cuts, logo loss and audio changes occur in programs too. Preserve a sports game or news report that remains visible under sponsor graphics or alongside a split-screen advertisement. Category, program name and actual broadcast start may be unknown; do not invent them. A title inferred visually is a hypothesis, not confirmed metadata. Do not reuse an ad's title as the ongoing show's identity.
Respond with exactly one JSON object containing label (ad|program|uncertain), confidence (0..1), program, evidence, program_changed (boolean), category (sports|news|movie|series|documentary|kids|music|unknown), and presentation (program|full_screen_ad|in_program_promotion|split_screen|menu|own_card|unknown)."""


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
        return Verdict(label, confidence, str(result.get("program") or "")[:180],
                       str(result.get("evidence", ""))[:240],
                       result.get("program_changed") is True,
                       result.get("category") if result.get("category") in CATEGORIES else "unknown",
                       result.get("presentation") if result.get("presentation") in PRESENTATIONS else "unknown")


class Detector:
    def __init__(self, vision=None, clock=None):
        self.vision = vision or VisionClient()
        self.clock = clock or time.time
        self.states = {}
        self.identities = {}
        self.states_lock = threading.Lock()

    def state(self, tv_id):
        with self.states_lock:
            return self.states.setdefault(tv_id, TVState())

    @staticmethod
    def replace_state(target, replacement):
        with target.lock:
            for f in fields(TVState):
                if f.name != 'lock':
                    setattr(target, f.name, getattr(replacement, f.name))

    def status(self):
        with self.states_lock:
            return [dict(tv_id=tv_id, identity=identity.snapshot(),
                         muted_by_detector=self.states[tv_id].muted_by_detector,
                         viewing_context=self.states[tv_id].viewing.snapshot(self.clock(),
                             dict(channel=identity.channel, title=identity.title)))
                    for tv_id, identity in self.identities.items() if tv_id in self.states]

    def overlay_info(self, tv_id, context):
        with self.states_lock:
            identity = self.identities.get(tv_id)
            state = self.states.get(tv_id)
            if not identity or not state or context.get("session", "") != identity.session:
                return {}
            return state.viewing.overlay_info(self.clock(), dict(
                app=identity.app, channel=identity.channel, title=identity.title))

    def next_interval(self, tv_id):
        state = self.state(tv_id)
        now = self.clock()
        with state.lock:
            if state.capture_obscured:
                return 2
            if state.model_unavailable:
                return 15
            if state.muted_by_detector:
                # Avoid repeatedly uncovering the ad behind the card. Once a
                # program frame appears, confirm it promptly before unmuting.
                return 2 if state.program_streak == 1 else 8
            if state.ad_streak or state.program_streak == 1:
                return 2
            if state.last_verdict == "uncertain":
                return 2
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
        at = self.clock()
        with self.states_lock:
            identity = self.identities.setdefault(tv_id, PlaybackIdentity())
            accepted, reason = identity.admit(context, at)
            if not accepted:
                return "UNMUTE", Verdict("uncertain", evidence=reason)
            state = self.states.setdefault(tv_id, TVState())
            if reason:
                # Replace the active state without waiting for an old AI call.
                # That call holds only a private working copy and cannot revive it.
                fresh = TVState(app=identity.app, session=identity.session,
                                channel=identity.channel, title=identity.title)
                fresh.viewing.epoch = state.viewing.epoch + 1
                self.replace_state(state, fresh)
                return "UNMUTE", Verdict("uncertain", evidence=reason)
            if not identity.app:
                return "UNMUTE", Verdict("uncertain", evidence="foreground app unavailable")
            ticket = identity.ticket
            working = TVState(**{f.name: copy.deepcopy(getattr(state, f.name))
                                 for f in fields(TVState) if f.name != 'lock'})
            enriched = dict(context, playback_identity=identity.snapshot())
        action, verdict = self._process(tv_id, png, enriched, working)
        working.viewing.observe(verdict, at, action == "MUTE", is_error=working.model_unavailable)
        with self.states_lock:
            if identity.ticket != ticket:
                return "UNMUTE", Verdict("uncertain", evidence="obsolete playback result")
            self.replace_state(state, working)
            return action, verdict

    def _process(self, tv_id, png, context, state=None):
        state = state if state is not None else self.state(tv_id)
        now = self.clock()
        with state.lock:
            app = context.get("app", "")
            channel = context.get("channel", "")
            title = context.get("title", "")
            session = context.get("session", "")
            session_changed = bool(session and state.session and session != state.session)
            app_changed = bool(state.app and app != state.app)
            # A program may have been observed even when the vision service
            # cannot name it. The timestamp is the reliable context marker.
            channel_changed = bool(channel and channel != state.channel and state.first_program_seen_at)
            title_changed = bool(title and title != state.title and state.first_program_seen_at)
            if app_changed or channel_changed or title_changed or session_changed:
                state.viewing.reset()
                state.app = app
                state.channel = channel
                state.title = title
                state.session = session
                state.program = ""
                state.first_program_seen_at = 0.0
                state.ad_candidate_at = 0.0
                state.ad_starts.clear()
                state.last_ad_end_at = 0.0
                state.last_ad_at = 0.0
                state.last_verdict = "uncertain"
                state.recent_observations.clear()
                state.switch_streak = 0
                state.previous_hash = ""
                state.ad_streak = state.program_streak = 0
                state.muted_by_detector = False
                state.model_unavailable = False
                state.updated_at = now
                reason = ("navigation/session changed" if session_changed else "app changed" if app_changed else
                          "channel changed" if channel_changed else "title changed")
                return "UNMUTE", Verdict("uncertain", evidence=reason)
            state.app = app
            if session:
                state.session = session
            state.capture_obscured = False
            if not context.get("_local_checked"):
                try:
                    state.capture_obscured = own_card(visual_features(png))
                except (ValueError, OSError, zlib.error):
                    pass
            if state.capture_obscured:
                state.last_verdict = "uncertain"
                if now - state.last_ad_at > STALE_MUTE_SECONDS:
                    state.muted_by_detector = False
                return ("MUTE" if state.muted_by_detector else "UNMUTE"), Verdict("uncertain", evidence="own_card", presentation="own_card")
            if channel:
                state.channel = channel
            if title:
                state.title = title
            digest = hashlib.sha256(png).hexdigest()
            if digest == state.previous_hash:
                if state.muted_by_detector and now - state.last_ad_at > STALE_MUTE_SECONDS:
                    state.muted_by_detector = False
                    return "UNMUTE", Verdict("uncertain", evidence="stale frame")
                return ("MUTE" if state.muted_by_detector else "UNMUTE"), Verdict("uncertain", evidence="unchanged frame")
            state.previous_hash = digest
            model_context = dict(context, viewing_context=state.viewing.snapshot(now, context), known_program=state.program,
                                 seconds_since_last_ad=round(now - state.last_ad_at) if state.last_ad_at else None,
                                 previous_label=state.last_verdict,
                                 program_first_observed_at_utc=(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(state.first_program_seen_at)) if state.first_program_seen_at else None),
                                 confirmed_ad_breaks_utc=[time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value)) for value in state.ad_starts],
                                 recent_observations=state.recent_observations[-6:])
            # This fixed YouTube TV UI badge is stronger evidence than a scene
            # change and can be checked locally before the slower vision agent.
            badge_hit = app == "com.samsung.tv.cobalt-yttv" and sponsored_badge.present(png)
            if badge_hit:
                verdict = Verdict("ad", 0.99, evidence="YouTube TV Sponsored badge")
                state.model_unavailable = False
            else:
                try:
                    verdict = self.vision.classify(png, model_context)
                    state.model_unavailable = False
                except Exception as exc:
                    verdict = Verdict("uncertain", evidence="model error: " + type(exc).__name__)
                    state.model_unavailable = True
            if verdict.presentation in {"in_program_promotion", "split_screen"}:
                verdict = Verdict("program", verdict.confidence, verdict.program,
                                  "program remains visible during promotion", verdict.program_changed,
                                  verdict.category, verdict.presentation)
            elif verdict.presentation in {"menu", "own_card"}:
                verdict = Verdict("uncertain", 0, evidence=verdict.presentation,
                                  presentation=verdict.presentation)
                if verdict.presentation == "menu":
                    state.viewing.reset()
                    state.program = ""
                    state.first_program_seen_at = state.last_ad_at = 0
                    state.ad_starts.clear()
                    state.ad_streak = state.program_streak = 0
                    state.muted_by_detector = False
            state.updated_at = now
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
            possible_new_program = (verdict.label == "program" and verdict.program_changed
                                    and bool(state.first_program_seen_at)
                                    and verdict.confidence >= POSSIBLE_PROGRAM_CHANGE_CONFIDENCE)
            if possible_new_program:
                state.switch_streak += 1
                if (state.switch_streak >= 2
                        or (state.muted_by_detector
                            and verdict.confidence >= STRONG_PROGRAM_CHANGE_CONFIDENCE)):
                    state.viewing.reset()
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
            if verdict.presentation in {"in_program_promotion", "split_screen"} and verdict.confidence >= .8:
                # A positive view of the show with a corner promotion must not
                # inherit a previous break's cover while waiting for two votes.
                if state.muted_by_detector:
                    state.last_ad_end_at = now
                state.muted_by_detector = False
                state.ad_streak = 0
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
                and bool(state.first_program_seen_at)
                and not verdict.program_changed
            )
            if not state.muted_by_detector and (state.ad_streak >= 2 or strong_ad_against_known_program or badge_hit):
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
    latest_frame_lock = threading.Lock()
    latest_frame = None
    detector = Detector()
    token = os.getenv("FRAME_TOKEN", "")
    realtime_enabled = os.getenv("ENABLE_REALTIME", "0") == "1"
    realtime = None
    realtime_lock = threading.Lock()

    @classmethod
    def fast(cls):
        with cls.realtime_lock:
            if cls.realtime is None:
                from realtime import RealtimeDetector
                cls.realtime = RealtimeDetector(lambda: Detector())
            return cls.realtime

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
        elif self.path == "/v2/status" and self.realtime_enabled:
            if not self._authorized():
                self._reply(401, "unauthorized")
            else:
                self._reply(200, json.dumps(self.fast().status()), "application/json")
        elif self.path == "/v1/latest-frame":
            if not self._authorized():
                self._reply(401, "unauthorized")
                return
            with self.latest_frame_lock:
                frame = type(self).latest_frame
            if frame is None:
                self._reply(404, "No frame received yet")
                return
            png, received, sequence = frame
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Received-Unix", str(received))
            self.send_header("X-TV-Frame-Sequence", sequence)
            self.end_headers()
            self.wfile.write(png)
        elif self.path == "/v1/status":
            if not self._authorized():
                self._reply(401, "unauthorized")
            else:
                self._reply(200, json.dumps(self.detector.status()), "application/json")
        else:
            self._reply(404, "not found")

    def do_POST(self):
        if self.path != "/v1/frame" and not (self.realtime_enabled and self.path in {"/v2/frame", "/v2/audio"}):
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
        if self.path != "/v2/audio" and (png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR"):
            self._reply(415, "PNG required")
            return
        context = {
            "app": self.headers.get("X-TV-App", "")[:120],
            "channel": self.headers.get("X-TV-Channel", "")[:120],
            "title": self.headers.get("X-TV-Title", "")[:180],
            "local_time": self.headers.get("X-TV-Local-Time", "")[:80],
            "session": self.headers.get("X-TV-Session", "")[:80],
            "frame_sequence": self.headers.get("X-TV-Frame-Sequence", "")[:24],
        }
        tv_id = self.headers.get("X-TV-ID", "frame-tv")[:80]
        if self.path in ("/v1/frame", "/v2/frame") and tv_id == "frame-tv":
            # One in-memory arrival snapshot; never changes the detector decision.
            with self.latest_frame_lock:
                type(self).latest_frame = (png, time.time(),
                    context['frame_sequence'] if context['frame_sequence'].isdigit() else '')
        if self.path == "/v2/audio":
            try:
                capture_start = float(self.headers.get("X-Capture-Start-Unix", ""))
                if not math.isfinite(capture_start):
                    raise ValueError("invalid capture time")
                accepted = self.fast().observe_audio(tv_id, png, context, capture_start)
            except ValueError:
                self._reply(400, "invalid audio")
                return
            self._reply(200 if accepted else 409, "observed" if accepted else "context mismatch")
            return
        if self.path == "/v2/frame":
            started = time.monotonic()
            result = self.fast().ingest(tv_id, png, context)
            elapsed_ms = round((time.monotonic() - started) * 1000)
            action = result["action"]
            print(f"decision={action} source={result['reason']} ingest_ms={elapsed_ms} "
                  f"model_ms={result['model_ms']} epoch={result['epoch']}", flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(action)))
            self.send_header("X-Next-Capture-Seconds", str(result["next_capture_seconds"]))
            self.send_header("X-Decision-Source", result["reason"])
            self.send_header("X-Processing-Ms", str(elapsed_ms))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(action.encode("ascii"))
            return
        started = time.monotonic()
        action, verdict = self.detector.process(tv_id, png, context)
        next_interval = self.detector.next_interval(tv_id)
        elapsed_ms = round((time.monotonic() - started) * 1000)
        print(f"decision={action} label={verdict.label} confidence={verdict.confidence:.2f} "
              f"program_changed={int(verdict.program_changed)} classify_ms={elapsed_ms}", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(action)))
        self.send_header("X-Frame-Label", verdict.label)
        self.send_header("X-Frame-Confidence", f"{verdict.confidence:.2f}")
        card = self.detector.overlay_info(tv_id, context)
        payload = base64.b64encode(json.dumps(card, ensure_ascii=True, separators=(",", ":")).encode()).decode()
        if len(payload) <= 8192:
            self.send_header("X-Overlay-Info", payload)
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
