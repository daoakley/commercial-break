import unittest
from datetime import datetime, timezone

from analyze_fingerprint_shadow import first_reports, frame_context


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


class FingerprintReportTests(unittest.TestCase):
    def test_frame_between_different_labels_is_transition(self):
        frames = [(100.0, "program", ""), (110.0, "ad", "")]
        times = [100.0, 110.0]
        self.assertEqual(frame_context(105.0, frames, times), "transition")
        self.assertEqual(frame_context(99.0, frames, times), "program")
        self.assertEqual(frame_context(111.0, frames, times), "ad")

    def test_event_uses_first_report_not_earliest_match_offset(self):
        reports = [
            (stamp(105.720), "transition", .9998, stamp(110.875)),
            (stamp(105.688), "transition", .9671, stamp(114.883)),
            (stamp(150.0), "ad", .96, stamp(156.0)),
        ]
        events = first_reports(reports)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0], reports[0])
        self.assertEqual(events[1], reports[2])


if __name__ == "__main__":
    unittest.main()
