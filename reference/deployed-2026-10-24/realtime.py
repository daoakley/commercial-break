"""Bounded asynchronous ingestion: local evidence never waits behind vision.

Only the already-existing app-specific Sponsored rule can initiate a local
mute. New audio/composition features request model work and carry no mute vote.
"""

from dataclasses import dataclass, field
import hashlib
import threading
import time
import zlib

import sponsored_badge
from local_signals import visual_features, visual_change, own_card, audio_features


@dataclass
class Stream:
    key: tuple
    detector: object
    epoch: int
    latest: object = None
    previous_visual: object = None
    scene: int = 0
    pending: object = None
    busy: bool = False
    next_due: float = 0
    last_submit: float = -100
    last_received: float = 0
    last_evidence: float = 0
    badge_at: float = -100
    action: str = "UNMUTE"
    label: str = "uncertain"
    reason: str = "awaiting_evidence"
    confidence: float = 0
    audio: dict = field(default_factory=dict)
    audio_at: float = -100
    audio_end: float = 0
    model_ms: int = 0
    calls: int = 0
    discarded: int = 0
    digest: str = ""
    changed_at: float = 0


class RealtimeDetector:
    def __init__(self, factory, *, clock=time.monotonic, extract=visual_features,
                 badge=sponsored_badge.present, cover=own_card, start_worker=True):
        self.factory, self.clock = factory, clock
        self.extract, self.badge, self.cover = extract, badge, cover
        self.streams = {}
        self.condition = threading.Condition()
        self.closed = False
        self.thread = threading.Thread(target=self._run, name="vision-latest-frame", daemon=True)
        if start_worker:
            self.thread.start()

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        if self.thread.is_alive():
            self.thread.join(timeout=1)

    def ingest(self, tv_id, png, context):
        arrived = self.clock()
        try:
            features = self.extract(png)
            covered = self.cover(features)
        except (ValueError, OSError, zlib.error):
            features, covered = None, False
        is_badge = (not covered and context.get("app") == "com.samsung.tv.cobalt-yttv"
                    and self.badge(png))
        key = tuple(str(context.get(k) or "") for k in ("app", "channel", "title", "session"))
        with self.condition:
            stream = self.streams.get(tv_id)
            if stream is None or key != stream.key:
                stream = Stream(key, self.factory(), (stream.epoch + 1) if stream else 0)
                self.streams[tv_id] = stream
            stream.last_received = arrived
            digest = hashlib.sha256(png).hexdigest()
            if digest != stream.digest:
                stream.digest, stream.changed_at = digest, arrived
            elif arrived - stream.changed_at > 60:
                stream.action, stream.reason = "UNMUTE", "frozen_frame"
                stream.pending = None
                return self._reply(stream, arrived)
            if covered:
                if stream.action == "MUTE" and arrived - stream.last_evidence > 20:
                    stream.action = "UNMUTE"
                stream.reason = "own_card_rejected"
                return self._reply(stream, arrived, retry=True)
            change = visual_change(stream.previous_visual, features) if features else {}
            if change.get("scene_cut_candidate"):
                stream.scene += 1
            if features and not covered:
                stream.previous_visual = features
            stream.last_received = arrived
            # Decisions expire based on the source observation, not repeated polls.
            if stream.action == "MUTE" and arrived - stream.last_evidence > 20:
                stream.action, stream.reason = "UNMUTE", "evidence_expired"
            signals = dict(change, mean_luma=round(features["mean_luma"], 1) if features else None,
                           feature_role="urgency_only_not_ad_evidence")
            if arrived - stream.audio_at <= 3:
                signals["audio"] = dict(stream.audio)
            enriched = dict(context, local_signals=signals, _local_checked=True)
            job = (arrived, png, enriched, stream.scene)
            stream.latest = job
            if is_badge:
                stream.action, stream.label = "MUTE", "ad"
                stream.reason, stream.confidence = "sponsored_badge", .99
                stream.last_evidence = stream.badge_at = arrived
                # Do not enqueue a model call for a locally conclusive frame.
                stream.pending = None
                stream.next_due = arrived + 2
            else:
                urgent = (change.get("scene_cut_candidate") or
                          (arrived - stream.audio_at <= 3 and stream.audio.get("change_candidate")))
                if stream.pending is not None or arrived >= stream.next_due or (urgent and arrived - stream.last_submit >= 2):
                    # At most one pending frame per stream; replace, never backlog.
                    stream.pending = job
                    self.condition.notify()
            return self._reply(stream, arrived)

    def observe_audio(self, tv_id, pcm, context, capture_start):
        features = audio_features(pcm)
        now = self.clock()
        key = tuple(str(context.get(k) or "") for k in ("app", "channel", "title", "session"))
        with self.condition:
            stream = self.streams.get(tv_id)
            if stream is None or key != stream.key:
                return False
            # Capture timestamps are used only for continuity, never compared
            # with the Mac clock. Gaps and out-of-order slices reset the baseline.
            contiguous = stream.audio_end and abs(capture_start - stream.audio_end) <= .15
            delta = abs(features["rms_dbfs"] - stream.audio.get("rms_dbfs", features["rms_dbfs"]))
            features["rms_change_db"] = round(delta, 2) if contiguous else None
            features["contiguous"] = bool(contiguous)
            features["change_candidate"] = bool(contiguous and delta > 10)
            stream.audio = features
            stream.audio_at = now
            stream.audio_end = capture_start + features["duration_seconds"]
            return True

    def _reply(self, stream, now, retry=False):
        return {"action": stream.action, "label": stream.label,
                "confidence": stream.confidence, "reason": stream.reason,
                "epoch": stream.epoch, "next_capture_seconds": 1 if retry or stream.action != "MUTE" or stream.label == "program" else 4,
                "model_ms": stream.model_ms, "model_calls": stream.calls,
                "discarded_results": stream.discarded,
                "evidence_age_seconds": round(now - stream.last_evidence, 3) if stream.last_evidence else None}

    def status(self):
        now = self.clock()
        with self.condition:
            return [{"epoch": s.epoch, "frame_age_seconds": round(now - s.last_received, 2),
                     "pending_frames": int(s.pending is not None), "model_busy": s.busy,
                     **self._reply(s, now)} for s in self.streams.values()]

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or any(s.pending is not None for s in self.streams.values()))
                if self.closed:
                    return
                tv_id, stream = next((i, s) for i, s in self.streams.items() if s.pending is not None)
                job, stream.pending = stream.pending, None
                stream.busy = True
                stream.last_submit = self.clock()
                stream.next_due = stream.last_submit + 10
            arrived, png, context, scene = job
            start = self.clock()
            try:
                action, verdict = stream.detector.process(tv_id, png, context)
                failure = stream.detector.state(tv_id).model_unavailable
            except Exception:
                verdict, action, failure = None, "UNMUTE", True
            ended = self.clock()
            with self.condition:
                stream.busy = False
                stream.calls += 1
                stream.model_ms = round((ended - start) * 1000)
                self.condition.notify_all()
                if self.streams.get(tv_id) is not stream or stream.badge_at > arrived:
                    stream.discarded += 1
                    continue
                if failure:
                    stream.action, stream.reason = "UNMUTE", "model_unavailable"
                    stream.next_due = ended + 15
                    stream.pending = None
                    continue
                if ended - arrived > 8:
                    stream.discarded += 1
                    stream.next_due = ended
                    continue
                stream.label, stream.confidence = verdict.label, verdict.confidence
                # Ordinary programs AND ads cut frequently. A scene cut requests
                # fresh interpretation but is not a channel-change assertion.
                # Source/navigation epochs above reject old-view results; the
                # eight-second age limit bounds automatic-show-transition lag.
                if verdict.label == "ad" and verdict.confidence >= .7 and action == "MUTE":
                    stream.action, stream.reason = "MUTE", "vision_ad"
                    stream.last_evidence = arrived
                elif action == "UNMUTE" and verdict.label == "program" and verdict.confidence >= .7:
                    stream.action, stream.reason = "UNMUTE", "vision_release"
                # An uncertain model result cannot refresh an ad lease.
                stream.next_due = ended + (2 if stream.action == "MUTE" and verdict.label == "program" else
                                           8 if stream.action == "MUTE" else
                                           2 if verdict.label == "uncertain" or verdict.label == "ad" else 5)
                self.condition.notify_all()
