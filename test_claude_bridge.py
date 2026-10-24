import unittest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from claude_bridge import AuditStore, parse_verdict


class VerdictParsingTests(unittest.TestCase):
    def test_accepts_claude_json_fence(self):
        result = parse_verdict('```json\n{"label":"ad","confidence":0.85,"program":"","evidence":"pitch"}\n```')
        self.assertEqual(result["label"], "ad")
        self.assertEqual(result["confidence"], 0.85)

    def test_rejects_unusable_verdict(self):
        with self.assertRaises(ValueError):
            parse_verdict('{"label":"ad","confidence":3}')

    def test_program_change_signal_is_boolean(self):
        self.assertTrue(parse_verdict('{"label":"program","confidence":0.9,"program_changed":true}')["program_changed"])


class AuditStoreTests(unittest.TestCase):
    def test_saves_pre_ad_ad_and_post_ad_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = AuditStore(directory)
            program = {"label": "program", "confidence": .95}
            ad = {"label": "ad", "confidence": .97}
            for index in range(4):
                audit.observe(bytes([index]), {"app": "tv"}, program, 1000 + index)
            audit.observe(b"ad1", {"app": "tv"}, ad, 1004)
            audit.observe(b"show", {"app": "tv"}, program, 1005)
            images = list(Path(directory).glob("*.png"))
            self.assertEqual(len(images), 7)
            self.assertTrue(all(path.stat().st_mode & 0o077 == 0 for path in images))

    def test_saves_program_frame_after_audio_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate_file = Path(directory) / "boundaries.csv"
            at = datetime.fromtimestamp(1009, timezone.utc).isoformat()
            candidate_file.write_text("at_utc,silence_ms\n" + at + ",120\n")
            audit = AuditStore(directory, candidate_file)
            program = {"label": "program", "confidence": .9}
            audit.observe(b"first", {"app": "tv"}, program, 1000)
            audit.observe(b"candidate", {"app": "tv"}, program, 1014)
            self.assertEqual(len(list(Path(directory).glob("*.png"))), 2)


if __name__ == "__main__":
    unittest.main()
