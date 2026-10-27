import copy
import json
from pathlib import Path
import tempfile
import unittest

from teacher_train import (DEFAULT_SOURCE, bursts, chronological_split, experiment, nearest,
                           positive_rejection, stage_model)


def row(t, verdict="ad", session="s", source=DEFAULT_SOURCE, **updates):
    result = {"frame_id": str(t), "timestamp_unix": t, "session_id": session, "source": source,
              "expires_unix": 10000, "contamination": {"status": "clean"},
              "metadata": {"tv_debug": {"evidence": {
                  "samsung": {"verdict": verdict}, "decision": {"sameSession": True},
                  "capture": {"captureStartedAt": t * 1000, "fingerprintAt": t * 1000 + 500, "mode": "normal"}}}}}
    result.update(updates)
    return result


class TeacherTests(unittest.TestCase):
    def test_only_aligned_teacher_positives_and_manual_veto(self):
        good = row(100)
        self.assertIsNone(positive_rejection(good))
        self.assertEqual(positive_rejection(row(100, "unknown")), "no_teacher_ad")
        self.assertEqual(positive_rejection(row(100, manual_label="program", label_source="human")), "human_program_veto")
        bad = copy.deepcopy(good)
        bad["metadata"]["tv_debug"]["evidence"]["capture"]["fingerprintAt"] += 2001
        self.assertEqual(positive_rejection(bad), "capture_alignment_over_2_seconds")
        bad = copy.deepcopy(good)
        bad["metadata"]["tv_debug"]["evidence"]["decision"]["sameSession"] = False
        self.assertEqual(positive_rejection(bad), "teacher_not_same_session")
        masked = copy.deepcopy(good)
        masked["metadata"]["tv_debug"]["evidence"]["capture"]["mode"] = "panel-masked"
        self.assertIsNone(positive_rejection(masked))
        masked["metadata"]["tv_debug"]["evidence"]["capture"]["mode"] = "card-visible"
        self.assertEqual(positive_rejection(masked), "unverified_capture_mode")

    def test_bursts_respect_source_session_and_30s_gap(self):
        groups = bursts([row(100), row(125), row(156), row(160, session="other"), row(165, source="other")])
        self.assertEqual([len(x) for x in groups], [2, 1, 1, 1])

    def test_chronological_split_excludes_crossing_bursts(self):
        groups = [[row(100)], [row(150), row(205)], [row(200, session="x")], [row(300)]]
        split = chronological_split(groups)
        self.assertIsNotNone(split)
        self.assertIn(["150", "205"], split["excluded_boundary_bursts"])
        self.assertLessEqual(max(r["timestamp_unix"] for r in split["train"]), split["boundaries"]["validation_start"] - 30)

    def test_source_binding_prevents_cross_app_activation(self):
        model = stage_model([row(100)], {"100": [1., 0.]}, DEFAULT_SOURCE, 10000)
        self.assertEqual(nearest(model, [1., 0.], DEFAULT_SOURCE), 1)
        self.assertIsNone(nearest(model, [1., 0.], "some-other-app"))

    def test_full_candidate_separate_and_holdout_does_not_memorize_test(self):
        rows = [row(100), row(200), row(300), row(400), row(500), row(510, "unknown"),
                row(520, "unknown", manual_label="program", label_source="human")]
        loader = lambda r: ([1., 0.] if r["timestamp_unix"] < 400 else [0., 1.], .1)
        with tempfile.TemporaryDirectory() as temp:
            report = experiment(rows, temp, temp, now=1000, vector_loader=loader)
            model = json.loads((Path(temp) / "teacher-heldout-train.staged.json").read_text())
            full = json.loads((Path(temp) / "teacher-all-positive.staged.json").read_text())
            self.assertEqual(len(full["exemplars"]), 5)
            self.assertEqual(len(model["exemplars"]), 3)
            result = report["test"]["threshold_sweep_descriptive_only"][0]
            self.assertEqual(result["teacher_positive_recovery"], 0)
            self.assertEqual(result["unlabelled_activation_rate_not_false_positive_rate"], 0)
            self.assertEqual(result["human_negative_false_positive_rate"], 0)
            self.assertEqual(report["expires_unix"], 10000)

    def test_insufficient_bursts_stage_candidate_without_heldout_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            report = experiment([row(100), row(120)], temp, temp, now=1000, vector_loader=lambda r: ([1., 0.], .1))
            self.assertEqual(report["status"], "insufficient_data")
            self.assertFalse(report["all_positive_candidate"]["heldout_claim"])
            self.assertFalse((Path(temp) / "teacher-heldout-train.staged.json").exists())

    def test_expired_contaminated_other_source_and_unknown_never_train(self):
        rows = [row(100, expires_unix=999), row(200, contamination={"status": "contaminated"}),
                row(300, source="other"), row(400, "unknown")]
        with tempfile.TemporaryDirectory() as temp:
            report = experiment(rows, temp, temp, now=1000, vector_loader=lambda r: ([1., 0.], .1))
            self.assertEqual(report["teacher_positives"], 0)
            self.assertEqual(report["usable_observations"], 1)
            self.assertEqual([p.name for p in Path(temp).iterdir()], ["teacher-experiment.json"])

    def test_rerun_clears_stale_heldout_then_all_positive_candidates(self):
        loader = lambda r: ([1., 0.], .1)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            experiment([row(100), row(200), row(300)], temp, temp, now=1000, vector_loader=loader)
            self.assertTrue((root / "teacher-heldout-train.staged.json").exists())
            experiment([row(100), row(120)], temp, temp, now=1000, vector_loader=loader)
            self.assertFalse((root / "teacher-heldout-train.staged.json").exists())
            self.assertTrue((root / "teacher-all-positive.staged.json").exists())
            experiment([row(100, "unknown")], temp, temp, now=1000, vector_loader=loader)
            self.assertFalse((root / "teacher-all-positive.staged.json").exists())
            self.assertEqual(json.loads((root / "teacher-experiment.json").read_text())["teacher_positives"], 0)


if __name__ == "__main__":
    unittest.main()
