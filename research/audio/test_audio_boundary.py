import struct
import unittest

from audio_boundary import find_candidates, rms_frames


def pcm_segments(*segments):
    """Segments are (milliseconds, sample value) at 48 kHz stereo."""
    chunks = []
    for duration_ms, value in segments:
        chunks.append(struct.pack("<h", value) * (duration_ms * 48 * 2))
    return b"".join(chunks)


class AudioBoundaryTests(unittest.TestCase):
    def test_detects_short_edit_gap(self):
        pcm = pcm_segments((500, 2000), (20, 0), (500, 2300))
        candidates = find_candidates(pcm)
        self.assertEqual(len(candidates), 1)
        self.assertAlmostEqual(candidates[0].offset_seconds, 0.5)
        self.assertEqual(candidates[0].silence_ms, 20)
        self.assertGreater(candidates[0].depth, .99)

    def test_ignores_long_program_silence(self):
        pcm = pcm_segments((500, 2000), (500, 0), (500, 2300))
        self.assertEqual(find_candidates(pcm), [])

    def test_detects_quiet_end_credits_to_loud_ad(self):
        pcm = pcm_segments((500, 120), (50, 0), (500, 2200))
        candidates = find_candidates(pcm)
        self.assertEqual(len(candidates), 1)
        self.assertAlmostEqual(candidates[0].offset_seconds, 0.5)

    def test_ignores_soft_undipped_audio(self):
        pcm = pcm_segments((500, 2000), (20, 800), (500, 2300))
        self.assertEqual(find_candidates(pcm), [])

    def test_ignores_all_silence(self):
        self.assertEqual(find_candidates(pcm_segments((1000, 0))), [])

    def test_rejects_incomplete_sample(self):
        with self.assertRaises(ValueError):
            rms_frames(b"\x01")


if __name__ == "__main__":
    unittest.main()
