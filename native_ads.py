"""Fresh native onset hints. End events never release a visual cover."""
import math
import threading

YOUTUBE_TV = "com.samsung.tv.cobalt-yttv"
# How long an unused onset stays valid. The TV helper completes a cycle every
# ~4 s and a model call can add ~2 s, so five seconds could expire a hint that
# arrived just after a capture. Inserted ads run 10 s or more.
HINT_SECONDS = 8
# A pod-end notice older than this no longer justifies an early covered check,
# and one younger than the settle time may still be followed by the next ad.
END_SECONDS = 20
END_SETTLE_SECONDS = 1.5


class NativeAds:
    def __init__(self, clock):
        self.clock = clock
        self.lock = threading.Lock()
        self.bindings = {}
        self.counters = {"accepted_starts": 0, "used_starts": 0, "used_ends": 0, "rejected": 0}

    def observe(self, data, identity):
        now = self.clock()
        with self.lock:
            def reject():
                self.counters["rejected"] += 1
                return False
            if not identity or identity.app != YOUTUBE_TV or data.get("session") != identity.session or data.get("epoch") != identity.epoch:
                return reject()
            at = data.get("observed_unix")
            if isinstance(at, bool) or not isinstance(at, (int, float)) or not math.isfinite(at) or not -1 <= now-at <= 5:
                return reject()
            tv = data.get("tv_id")
            connection = data.get("connection")
            seq = data.get("sequence")
            if not isinstance(connection, str) or not 8 <= len(connection) <= 80 or type(seq) is not int or seq < 1:
                return reject()
            b = self.bindings.get(tv)
            kind = data.get("kind")
            content = data.get("content_id")
            if kind == "playback":
                if not isinstance(content, str) or not 3 <= len(content) <= 100:
                    return reject()
                if b and b["connection"] == connection and seq <= b["seq"]:
                    return reject()
                # A changed playback ID, session or epoch revokes any pending
                # onset immediately: a hint never survives a viewer navigation.
                same = b and all(b[k] == v for k, v in (("connection", connection), ("session", identity.session),
                                                        ("epoch", identity.epoch), ("content", content)))
                self.bindings[tv] = dict(connection=connection, session=identity.session, epoch=identity.epoch,
                    content=content, seq=seq, seen=now, onset=b["onset"] if same else None,
                    used=b["used"] if same else False, creatives=b["creatives"] if same else set())
                return True
            if not b or b["connection"] != connection or b["session"] != identity.session or b["epoch"] != identity.epoch or seq <= b["seq"] or now-b["seen"] > 25:
                return reject()
            b["seq"] = seq
            if kind == "disconnect":
                del self.bindings[tv]
                return True
            if kind == "heartbeat":
                b["seen"] = now
                return True
            if kind == "ad_end":
                # Revoke an unused hint, but do not touch the visual mute state.
                # Remember the end so a covered helper can look again early;
                # the picture still decides whether the show is really back.
                b["onset"] = None
                b["ended_at"], b["end_used"] = now, False
                return True
            creative = data.get("creative_id")
            if kind != "ad_start" or content != b["content"] or data.get("player_state") != 1081:
                return reject()
            if not isinstance(creative, str) or not 3 <= len(creative) <= 100 or creative in b["creatives"]:
                return reject()
            b["creatives"].add(creative)
            if len(b["creatives"]) > 200:
                b["creatives"] = {creative}
            b["onset"], b["used"], b["seen"] = at, False, now
            self.counters["accepted_starts"] += 1
            return True

    def take(self, tv_id, session, app, frame_at, epoch):
        with self.lock:
            b = self.bindings.get(tv_id)
            now = self.clock()
            if (app != YOUTUBE_TV or not b or b["session"] != session or b["epoch"] != epoch or b["used"]
                    or b["onset"] is None or not 0 <= now-b["onset"] <= HINT_SECONDS
                    or b["onset"] > frame_at):
                return None
            b["used"] = True
            self.counters["used_starts"] += 1
            return {"age_ms": round((now-b["onset"])*1000)}

    def take_end(self, tv_id, session, app, epoch, max_age=END_SECONDS, settle=END_SETTLE_SECONDS):
        """One-shot: a native pod end arrived recently for this exact playback.

        Inside a pod, each ad's end arrives in the same breath as the next ad's
        start, so an end only counts after a short settle time with no newer
        start behind it; otherwise a covered helper would look (and blink) at
        every ad boundary within the pod."""
        with self.lock:
            b = self.bindings.get(tv_id)
            now = self.clock()
            if (app != YOUTUBE_TV or not b or b["session"] != session or b["epoch"] != epoch
                    or b.get("end_used", True) or not settle <= now - b.get("ended_at", -1e9) <= max_age):
                return False
            if b.get("onset") is not None and b["onset"] >= b["ended_at"]:
                b["end_used"] = True  # a newer ad began: this end was mid-pod
                return False
            b["end_used"] = True
            self.counters["used_ends"] += 1
            return True

    def metrics(self):
        with self.lock:
            return dict(self.counters)
