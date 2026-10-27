import unittest
from PIL import Image

from diagnose import diagnose


class DiagnosticTests(unittest.TestCase):
    def row(self, stamp=100, session="s", clean=True):
        return {"frame_id": str(stamp), "session_id": session, "timestamp_unix": stamp,
                "expires_unix": 1000, "decision": "unknown", "live_decision_eligible": False,
                "contamination": {"status": "clean" if clean else "contaminated"},
                "metadata": {"ui_profile": "youtube_tv_480x270", "manual_label": "ad",
                             "tv_debug": {"evidence": {"samsung": {"verdict": "ad"},
                                                       "decision": {"sameSession": True},
                                                       "capture": {"mode": "panel-masked"}}},
                             "native_metadata": {"native": {"usable": True}}}}

    def test_samsung_and_pseudo_labels_are_not_human_truth(self):
        row = dict(self.row(), manual_label="ad", label_source="native")
        report = diagnose([row], "/unused", now=200, image_loader=lambda _: Image.new("RGB", (480, 270)),
                          verify_badge_equivalence=True)
        self.assertEqual(report["accuracy_evidence"], "insufficient_accuracy_evidence")
        self.assertEqual(report["counts"]["human_labelled"], 0)
        self.assertEqual(report["samsung_agreement"]["matrix_samsung_slash_local"], {"ad / unknown": 1})
        self.assertEqual(report["samsung_agreement"]["same_decision_fraction"], 0)
        self.assertEqual(report["counts"]["native_guard_usable"], 1)
        self.assertIn("File I/O and Pillow decoding excluded", report["timings_ms"]["method"])
        self.assertEqual(report["badge"]["equivalence_check"]["images_checked"], 1)
        self.assertEqual(report["timings_ms"]["detector_badge_applicable"]["count"], 1)

    def test_causal_order_exclusions_and_timing_sample_counts(self):
        seen = []
        def loader(row):
            seen.append(row["timestamp_unix"])
            return Image.new("RGB", (480, 270))
        rows = [self.row(102), self.row(100), self.row(101, clean=False), self.row(102)]
        report = diagnose(rows, "/unused", now=200, image_loader=loader)
        self.assertEqual(seen, [100, 102])
        self.assertEqual(report["counts"]["not_clean_excluded"], 1)
        self.assertEqual(report["counts"]["duplicate_timestamps_excluded"], 1)
        self.assertEqual(report["timings_ms"]["detector_including_features"]["count"], 2)
        self.assertEqual(report["expires_unix"], 1000)

    def test_unknown_is_not_program_and_unbound_is_not_compared(self):
        row = self.row()
        row["metadata"]["tv_debug"]["evidence"]["samsung"]["verdict"] = "unknown"
        other = self.row(101)
        other["metadata"]["tv_debug"]["evidence"]["decision"]["sameSession"] = False
        report = diagnose([row, other], "/unused", now=200, image_loader=lambda _: Image.new("RGB", (480, 270)))
        self.assertEqual(report["samsung_agreement"]["denominator"], 0)
        self.assertIsNone(report["samsung_agreement"]["same_decision_fraction"])


if __name__ == "__main__":
    unittest.main()
