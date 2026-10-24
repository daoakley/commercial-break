import threading
import time
import unittest
from types import SimpleNamespace

from realtime import RealtimeDetector
from server import Detector, Verdict
from viewing_context import ViewingContext


def features(png):
    return {"grid": [50] * (48 * 27), "mean_luma": 50}


class RealtimeTests(unittest.TestCase):
    context = {"app": "com.samsung.tv.cobalt-yttv", "session": "one"}

    def test_badge_can_mute_while_vision_is_blocked(self):
        entered, release = threading.Event(), threading.Event()
        class Slow:
            def process(self, *args):
                entered.set()
                release.wait(2)
                return "UNMUTE", Verdict("program", .9)
            def state(self, _):
                return SimpleNamespace(model_unavailable=False)
        rt = RealtimeDetector(Slow, extract=features, cover=lambda f: False,
                              badge=lambda p: p == b"badge")
        try:
            rt.ingest("tv", b"program", self.context)
            self.assertTrue(entered.wait(1))
            start = time.monotonic()
            result = rt.ingest("tv", b"badge", self.context)
            self.assertLess(time.monotonic() - start, .1)
            self.assertEqual(result["action"], "MUTE")
            release.set()
            with rt.condition:
                rt.condition.wait_for(lambda: rt.streams["tv"].calls >= 1, timeout=1)
            self.assertEqual(rt.status()[0]["action"], "MUTE")
        finally:
            release.set()
            rt.close()

    def test_channel_switch_discards_old_inflight_ad(self):
        entered, release = threading.Event(), threading.Event()
        class Slow:
            def process(self, tv, png, ctx):
                if ctx.get("channel") == "old":
                    entered.set()
                    release.wait(2)
                    return "MUTE", Verdict("ad", .99)
                return "UNMUTE", Verdict("program", .99)
            def state(self, _):
                return SimpleNamespace(model_unavailable=False)
        rt = RealtimeDetector(Slow, extract=features, cover=lambda f: False, badge=lambda p: False)
        try:
            rt.ingest("tv", b"old", dict(self.context, channel="old"))
            self.assertTrue(entered.wait(1))
            result = rt.ingest("tv", b"new", dict(self.context, channel="new"))
            self.assertEqual((result["action"], result["epoch"]), ("UNMUTE", 1))
            release.set()
            with rt.condition:
                rt.condition.wait_for(lambda: rt.streams["tv"].calls >= 1, timeout=1)
            self.assertEqual(rt.status()[0]["action"], "UNMUTE")
        finally:
            release.set()
            rt.close()

    def test_pending_queue_keeps_only_latest_and_never_grows(self):
        rt = RealtimeDetector(lambda: None, extract=features, cover=lambda f: False,
                              badge=lambda p: False, start_worker=False)
        for n in range(100):
            result = rt.ingest("tv", str(n).encode(), self.context)
            self.assertEqual(result["action"], "UNMUTE")
        self.assertEqual(rt.streams["tv"].pending[1], b"99")
        self.assertEqual(rt.status()[0]["pending_frames"], 1)

    def test_own_card_cannot_extend_mute_or_call_model(self):
        now = [100.0]
        rt = RealtimeDetector(lambda: None, clock=lambda: now[0], extract=features,
                              cover=lambda f: False, badge=lambda p: True, start_worker=False)
        self.assertEqual(rt.ingest("tv", b"ad", self.context)["action"], "MUTE")
        rt.cover = lambda f: True
        for n in range(1, 25):
            now[0] += 1
            reply = rt.ingest("tv", b"card" + bytes([n]), self.context)
        self.assertEqual(reply["action"], "UNMUTE")
        self.assertIsNone(rt.streams["tv"].pending)

    def test_brightness_changes_never_mute_on_their_own(self):
        def alternating(p):
            value = int(p)
            return {"grid": [value] * (48 * 27), "mean_luma": value}
        rt = RealtimeDetector(lambda: None, extract=alternating, cover=lambda f: False,
                              badge=lambda p: False, start_worker=False)
        for png in [b"0", b"255", b"0", b"255"]:
            self.assertEqual(rt.ingest("tv", png, self.context)["action"], "UNMUTE")

    def test_audio_context_mismatch_rejected_and_loudness_cannot_mute(self):
        rt = RealtimeDetector(lambda: None, extract=features, cover=lambda f: False,
                              badge=lambda p: False, start_worker=False)
        rt.ingest("tv", b"program", self.context)
        pcm = b"\x00\x00" * 96000
        self.assertFalse(rt.observe_audio("tv", pcm, dict(self.context, session="stale"), 100))
        self.assertTrue(rt.observe_audio("tv", pcm, self.context, 100))
        self.assertTrue(rt.observe_audio("tv", b"\xff\x7f\x00\x00" * 48000, self.context, 101))
        self.assertEqual(rt.status()[0]["action"], "UNMUTE")

    def test_ordinary_scene_cut_does_not_starve_ad_interpretation(self):
        entered, release = threading.Event(), threading.Event()
        class Slow:
            def process(self, *args):
                entered.set(); release.wait(2)
                return "MUTE", Verdict("ad", .99)
            def state(self, _): return SimpleNamespace(model_unavailable=False)
        def pixels(p): return {"grid": [int(p)] * 1296, "mean_luma": int(p)}
        rt = RealtimeDetector(Slow, extract=pixels, cover=lambda f: False, badge=lambda p: False)
        try:
            rt.ingest("tv", b"10", self.context)
            self.assertTrue(entered.wait(1))
            rt.ingest("tv", b"240", self.context)
            release.set()
            with rt.condition: rt.condition.wait_for(lambda: rt.streams['tv'].calls > 0, timeout=1)
            self.assertEqual(rt.status()[0]['action'], 'MUTE')
        finally: release.set(); rt.close()

    def test_uncertainty_after_badge_does_not_release_or_extend_lease(self):
        now = [100.0]
        class Unknown:
            def process(self, *args): return "UNMUTE", Verdict("uncertain", .5)
            def state(self, _): return SimpleNamespace(model_unavailable=False)
        rt = RealtimeDetector(Unknown, clock=lambda: now[0], extract=features,
                              cover=lambda f: False, badge=lambda p: p == b'badge')
        try:
            rt.ingest('tv', b'badge', self.context)
            now[0] = 103
            rt.ingest('tv', b'unknown', self.context)
            with rt.condition: rt.condition.wait_for(lambda: rt.streams['tv'].calls > 0, timeout=1)
            self.assertEqual(rt.status()[0]['action'], 'MUTE')
            now[0] = 121
            self.assertEqual(rt.ingest('tv', b'unknown2', self.context)['action'], 'UNMUTE')
        finally: rt.close()

    def test_model_failure_releases_existing_mute(self):
        now = [100.0]
        class Failing:
            def process(self, *args): raise RuntimeError('offline')
        rt = RealtimeDetector(Failing, clock=lambda: now[0], extract=features,
                              cover=lambda f: False, badge=lambda p: p == b'badge')
        try:
            rt.ingest('tv', b'badge', self.context)
            now[0] = 103
            rt.ingest('tv', b'other', self.context)
            with rt.condition: rt.condition.wait_for(lambda: rt.streams['tv'].calls > 0, timeout=1)
            self.assertEqual(rt.status()[0]['action'], 'UNMUTE')
        finally: rt.close()


class ContextTests(unittest.TestCase):
    def test_remote_navigation_resets_same_app_without_channel_metadata(self):
        detector = Detector(clock=lambda: 100)
        state = detector.state("tv")
        state.app = "com.samsung.tv.cobalt-yttv"
        state.session = "boot-0"
        state.muted_by_detector = True
        state.program, state.first_program_seen_at = "old show", 10
        state.ad_starts = [20, 40]
        action, _ = detector.process("tv", b"frame", {"app": state.app, "session": "boot-1234"})
        self.assertEqual(action, "UNMUTE")
        self.assertEqual(state.program, "")
        self.assertEqual(state.ad_starts, [])

    def test_unknown_name_and_start_are_not_invented(self):
        memory = ViewingContext()
        result = memory.snapshot(100, {})
        self.assertIsNone(result["show"]["name"])
        self.assertIsNone(result["actual_broadcast_start_unix"])
        self.assertIsNone(result["predicted_next_break"])

    def test_categories_and_names_learn_only_from_program(self):
        memory = ViewingContext()
        memory.observe(Verdict("program", .9, "basketball", category="sports"), 100, False)
        memory.observe(Verdict("program", .9, "basketball", category="sports"), 101, False)
        memory.observe(Verdict("ad", .99, "LEGO", category="kids"), 110, True)
        result = memory.snapshot(112, {})
        self.assertEqual(result["category"]["value"], "sports")
        self.assertEqual(result["show"]["name"], "basketball")
        self.assertEqual(result["show"]["source"], "vision_inference")
        self.assertIn("Scoreboards", result["category_expectations"])
        self.assertIsNone(result["predicted_ad_sequence"])

    def test_timing_predictions_require_history_and_expire_on_change(self):
        memory = ViewingContext()
        for start in (100, 400, 700, 1000):
            memory.observe(Verdict("ad", .99), start, True)
            memory.observe(Verdict("program", .99), start + 60, False)
        snapshot = memory.snapshot(1100, {})
        self.assertIsNotNone(snapshot["predicted_next_break"])
        self.assertFalse(snapshot["predicted_next_break"]["controls_mute"])
        memory.reset()
        self.assertIsNone(memory.snapshot(1101, {})["predicted_next_break"])

    def test_network_failure_is_not_a_confirmed_break_end(self):
        memory = ViewingContext()
        memory.observe(Verdict("ad", .99), 100, True)
        memory.observe(Verdict("uncertain", 0), 140, False, is_error=True)
        self.assertEqual(memory.durations, [])
        self.assertEqual(memory.last_break_end, 0)
        memory.observe(Verdict("ad", .99), 180, True)
        self.assertEqual(memory.starts, [100])
        self.assertEqual(memory.durations, [])

    def test_in_program_sports_promotion_cannot_start_mute(self):
        class Vision:
            def classify(self, *_):
                return Verdict("ad", .99, "football", category="sports", presentation="in_program_promotion")
        detector = Detector(Vision())
        for png in (b"one", b"two", b"three"):
            self.assertEqual(detector.process("tv", png, {"app": "test"})[0], "UNMUTE")

    def test_hgtv_corner_promo_releases_old_break_on_first_frame(self):
        class Vision:
            def classify(self, *_):
                return Verdict("ad", .85, "renovation show", program_changed=True,
                               category="series", presentation="in_program_promotion")
        detector = Detector(Vision(), clock=lambda: 100)
        state = detector.state("tv")
        state.muted_by_detector = True
        state.program, state.first_program_seen_at = "Jaws", 50
        state.last_ad_at = 99
        state.ad_starts = [60, 80]
        action, verdict = detector.process("tv", b"corner promo", {"app": "test"})
        self.assertEqual(action, "UNMUTE")
        # Changed shows must also retire old cadence; there was no actual
        # commercial boundary to learn from this false cover.
        self.assertEqual(verdict.program_changed, True)
        self.assertEqual(state.ad_starts, [])
        self.assertEqual(state.program, "renovation show")

    def test_own_card_filter_does_not_refresh_stale_ad(self):
        from unittest.mock import patch
        detector = Detector(clock=lambda: 100)
        state = detector.state("tv")
        state.muted_by_detector, state.last_ad_at = True, 20
        with patch("server.visual_features", return_value={}), patch("server.own_card", return_value=True):
            action, _ = detector.process("tv", b"card", {"app": "test"})
        self.assertEqual(action, "UNMUTE")
        self.assertEqual(state.last_ad_at, 20)


if __name__ == "__main__":
    unittest.main()
