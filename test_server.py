import unittest
import io
import json
from unittest.mock import patch

from server import Detector, Verdict, VisionClient


class FakeVision:
    def __init__(self, *verdicts):
        self.verdicts = iter(verdicts)

    def classify(self, png, context):
        return next(self.verdicts)


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.context = {"app": "com.samsung.tv.cobalt-yttv", "channel": "", "title": ""}

    def detector(self, *verdicts):
        return Detector(FakeVision(*verdicts), lambda: self.now)

    def test_two_distinct_ads_mute_and_two_program_frames_unmute(self):
        d = self.detector(Verdict("ad", .95), Verdict("ad", .92),
                          Verdict("program", .9, "football"), Verdict("program", .91, "football"))
        self.assertEqual(d.process("tv", b"ad1", self.context)[0], "UNMUTE")
        self.assertEqual(d.process("tv", b"ad2", self.context)[0], "MUTE")
        self.assertEqual(d.process("tv", b"show1", self.context)[0], "MUTE")
        self.assertEqual(d.process("tv", b"show2", self.context)[0], "UNMUTE")
        self.assertEqual(d.state("tv").program, "football")

    def test_duplicate_frame_cannot_create_second_ad_vote(self):
        d = self.detector(Verdict("ad", .95), Verdict("program", .9))
        self.assertEqual(d.process("tv", b"same", self.context)[0], "UNMUTE")
        self.assertEqual(d.process("tv", b"same", self.context)[0], "UNMUTE")
        self.assertEqual(d.process("tv", b"next", self.context)[0], "UNMUTE")

    def test_strong_ad_mutes_on_first_frame_after_program_is_known(self):
        d = self.detector(Verdict("program", .97, "football"),
                          Verdict("ad", .90, evidence="product pitch"))
        self.assertEqual(d.process("tv", b"show", self.context)[0], "UNMUTE")
        self.assertEqual(d.process("tv", b"ad1", self.context)[0], "MUTE")

    def test_strong_ad_without_known_program_still_needs_confirmation(self):
        d = self.detector(Verdict("ad", .97), Verdict("ad", .97))
        self.assertEqual(d.process("tv", b"ad1", self.context)[0], "UNMUTE")
        self.assertEqual(d.process("tv", b"ad2", self.context)[0], "MUTE")

    def test_youtube_tv_sponsored_badge_mutes_first_frame_without_model(self):
        class UnavailableVision:
            def classify(self, png, context):
                raise AssertionError("badge should bypass vision")

        d = Detector(UnavailableVision(), lambda: self.now)
        with patch("sponsored_badge.present", return_value=True):
            action, verdict = d.process("tv", b"badge", self.context)
        self.assertEqual(action, "MUTE")
        self.assertEqual(verdict.evidence, "YouTube TV Sponsored badge")

    def test_badge_fast_path_is_restricted_to_youtube_tv(self):
        d = self.detector(Verdict("program", .95, "show"))
        with patch("sponsored_badge.present", return_value=True) as badge:
            action, _ = d.process("tv", b"frame", dict(self.context, app="other.app"))
        self.assertEqual(action, "UNMUTE")
        badge.assert_not_called()

    def test_lower_confidence_ad_still_needs_confirmation(self):
        d = self.detector(Verdict("program", .97, "football"),
                          Verdict("ad", .89), Verdict("ad", .88))
        d.process("tv", b"show", self.context)
        self.assertEqual(d.process("tv", b"ad1", self.context)[0], "UNMUTE")
        self.assertEqual(d.process("tv", b"ad2", self.context)[0], "MUTE")

    def test_uncertain_transition_does_not_use_single_frame_rule(self):
        d = self.detector(Verdict("program", .97, "football"),
                          Verdict("uncertain", .8), Verdict("ad", .95), Verdict("ad", .94))
        d.process("tv", b"show", self.context)
        d.process("tv", b"transition", self.context)
        self.assertEqual(d.process("tv", b"ad1", self.context)[0], "UNMUTE")
        self.assertEqual(d.process("tv", b"ad2", self.context)[0], "MUTE")

    def test_stale_duplicate_frame_releases_detector_mute(self):
        d = self.detector(Verdict("ad", .95), Verdict("ad", .95))
        d.process("tv", b"ad1", self.context)
        self.assertEqual(d.process("tv", b"ad2", self.context)[0], "MUTE")
        self.now += 61
        self.assertEqual(d.process("tv", b"ad2", self.context)[0], "UNMUTE")

    def test_short_uncertain_stretch_keeps_commercial_muted(self):
        d = self.detector(Verdict("ad", .95), Verdict("ad", .95),
                          Verdict("uncertain", .8), Verdict("uncertain", .7))
        d.process("tv", b"ad1", self.context)
        d.process("tv", b"ad2", self.context)
        self.now += 21
        self.assertEqual(d.process("tv", b"ambiguous1", self.context)[0], "MUTE")
        self.now += 38
        self.assertEqual(d.process("tv", b"ambiguous2", self.context)[0], "MUTE")

    def test_model_error_immediately_unmutes(self):
        class FailingVision:
            def __init__(self):
                self.calls = 0

            def classify(self, png, context):
                self.calls += 1
                if self.calls == 3:
                    raise TimeoutError("bridge unavailable")
                return Verdict("ad", .95)

        d = Detector(FailingVision(), lambda: self.now)
        d.process("tv", b"ad1", self.context)
        d.process("tv", b"ad2", self.context)
        self.assertEqual(d.process("tv", b"next", self.context)[0], "UNMUTE")

    def test_app_change_releases_detector_mute(self):
        d = self.detector(Verdict("ad", .95), Verdict("ad", .95))
        d.process("tv", b"ad1", self.context)
        d.process("tv", b"ad2", self.context)
        self.assertEqual(d.process("tv", b"home", dict(self.context, app="home"))[0], "UNMUTE")

    def test_uncertain_frames_never_start_a_mute(self):
        d = self.detector(Verdict("uncertain", 1.0), Verdict("ad", .6))
        self.assertEqual(d.process("tv", b"one", self.context)[0], "UNMUTE")
        self.assertEqual(d.process("tv", b"two", self.context)[0], "UNMUTE")

    def test_program_start_is_first_observation_and_ad_start_needs_two_votes(self):
        d = self.detector(Verdict("program", .95, "football"),
                          Verdict("ad", .89), Verdict("ad", .91))
        d.process("tv", b"show", self.context)
        self.assertEqual(d.state("tv").first_program_seen_at, 1000)
        self.now = 1100
        d.process("tv", b"ad1", self.context)
        self.assertEqual(d.state("tv").ad_starts, [])
        self.now = 1105
        d.process("tv", b"ad2", self.context)
        self.assertEqual(d.state("tv").ad_starts, [1100])

    def test_stable_cadence_increases_sampling_near_next_break(self):
        d = self.detector()
        s = d.state("tv")
        s.last_verdict = "program"
        s.ad_starts = [100, 400, 700]
        self.now = 800
        self.assertEqual(d.next_interval("tv"), 5)
        self.now = 950
        self.assertEqual(d.next_interval("tv"), 3)
        s.ad_starts = [100, 400, 1000]
        self.now = 1250
        self.assertEqual(d.next_interval("tv"), 5)

    def test_next_frame_receives_recent_visual_context(self):
        seen = []

        class CaptureVision:
            def classify(self, png, context):
                seen.append(context)
                return Verdict("program", .9, "football", "scoreboard and field")

        d = Detector(CaptureVision(), lambda: self.now)
        d.process("tv", b"first", self.context)
        self.now += 8
        d.process("tv", b"second", self.context)
        self.assertEqual(seen[1]["known_program"], "football")
        self.assertEqual(seen[1]["recent_observations"][0]["evidence"], "scoreboard and field")

    def test_two_visual_program_changes_reset_cadence(self):
        d = self.detector(Verdict("program", .95, "football"),
                          Verdict("program", .92, "basketball", program_changed=True),
                          Verdict("program", .94, "basketball", program_changed=True))
        d.process("tv", b"game1", self.context)
        d.state("tv").ad_starts = [100, 400, 700]
        self.now = 1008
        d.process("tv", b"game2", self.context)
        self.assertEqual(len(d.state("tv").ad_starts), 3)
        self.now = 1016
        self.assertEqual(d.process("tv", b"game3", self.context)[0], "UNMUTE")
        self.assertEqual(d.state("tv").program, "basketball")
        self.assertEqual(d.state("tv").ad_starts, [])


class VisionServiceRequestTests(unittest.TestCase):
    def test_image_and_viewing_context_reach_private_service(self):
        response = io.BytesIO(json.dumps({"label": "ad", "confidence": .94,
                                          "program": "", "evidence": "product pitch"}).encode())
        with patch.dict("os.environ", {"VISION_SERVICE_URL": "http://localhost:8787/classify",
                                    "VISION_SERVICE_TOKEN": "test-token"}):
            client = VisionClient()
        with patch("urllib.request.urlopen", return_value=response) as call:
            verdict = client.classify(b"fake-png", {"app": "YouTube TV", "known_program": "football"})
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(payload["image_png_base64"], "ZmFrZS1wbmc=")
        self.assertEqual(payload["context"]["known_program"], "football")
        self.assertEqual(verdict.label, "ad")


if __name__ == "__main__":
    unittest.main()
