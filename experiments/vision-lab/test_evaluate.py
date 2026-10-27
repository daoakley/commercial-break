"""Behavior tests use invented data, never evidence of real ad-detection accuracy."""
import json
import tempfile
import unittest
from pathlib import Path

from evaluate import CausalDecision, evaluate
from train import fit, grouped_split, group_keys, score, train_experiment


def row(time, label, prediction="unknown", session="session-a", **extra):
    return {"session_id": session, "timestamp_unix": time, "manual_label": label,
            "label_source": "human", "contamination": {"status": "clean"},
            "prediction": prediction, "features": [1., 0.] if label == "ad" else [0., 1.], **extra}


class ReplayTests(unittest.TestCase):
    def test_delay_miss_false_block_and_unknown_have_time_denominators(self):
        rows = [row(0, "program", "program"), row(1, "ad", "unknown"),
                row(2, "ad", "ad"), row(3, "program", "ad"), row(4, "program", "program"),
                row(5, "ad", "unknown"), row(6, "ad", "program"), row(7, "program", "program")]
        result = evaluate(rows, confirmation_frames=1)
        counts = result["counts_and_seconds"]
        self.assertEqual(counts["evaluated_seconds"], 7)
        self.assertEqual(counts["complete_ad_breaks"], 2)
        self.assertEqual(counts["missed_ad_breaks"], 1)
        self.assertEqual(counts["false_blocked_seconds"], 1)
        self.assertEqual(counts["false_trigger_events"], 1)
        self.assertEqual(counts["ad_seconds_exposed"], 3)
        self.assertEqual(result["metrics"]["onset_median_seconds"], 1)
        self.assertEqual(result["metrics"]["restore_median_seconds"], .5)
        self.assertEqual(result["status"], "insufficient_data")

    def test_session_and_gap_reset_confirmation(self):
        rows = [row(0, "program", "ad"), row(10, "program", "ad"),
                row(11, "program", "ad", session="other"), row(12, "program", "program", session="other")]
        result = evaluate(rows)
        self.assertEqual(result["counts_and_seconds"]["false_blocked_seconds"], 0)
        self.assertEqual(result["counts_and_seconds"]["gap_resets"], 1)

    def test_future_observation_cannot_change_earlier_decisions(self):
        smoother = CausalDecision(2)
        self.assertEqual([smoother.update(x) for x in ["ad", "ad", "program", "unknown", "ad"]],
                         ["unknown", "ad", "unknown", "unknown", "unknown"])

    def test_native_pseudo_and_contaminated_never_ground_truth(self):
        rows = [row(0, "ad", "ad", label_source="native"), row(1, "ad", "ad", label_source="pseudo"),
                row(2, "ad", "ad", contamination={"status": "contaminated"}),
                row(3, "program", "program"), row(4, "program", "program")]
        result = evaluate(rows, confirmation_frames=1)
        self.assertEqual(result["counts_and_seconds"]["excluded_rows"], 3)
        self.assertEqual(result["counts_and_seconds"]["evaluated_seconds"], 1)
        self.assertEqual(result["counts_and_seconds"]["ad_seconds"], 0)

    def test_leading_and_trailing_ads_are_censored(self):
        rows = [row(0, "ad", "ad"), row(1, "program", "program"), row(2, "ad", "ad")]
        result = evaluate(rows, confirmation_frames=1)
        self.assertEqual(result["counts_and_seconds"]["complete_ad_breaks"], 0)
        self.assertEqual(result["counts_and_seconds"]["censored_ad_segments"], 2)
        self.assertIsNone(result["metrics"]["onset_p95_seconds"])

    def test_unknown_truth_breaks_temporal_continuity(self):
        rows = [row(0, "program", "program"), row(1, "ad", "ad"),
                row(2, "unknown", "ad"), row(3, "program", "program")]
        result = evaluate(rows, confirmation_frames=1)
        self.assertEqual(result["counts_and_seconds"]["complete_ad_breaks"], 0)

    def test_duplicate_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            evaluate([row(0, "ad"), row(0, "program")])


class TrainingTests(unittest.TestCase):
    def dataset(self):
        return [row(t, label, session=f"session-{s}", creative_id=f"creative-{s}" if label == "ad" else None)
                for s in range(6) for t, label in enumerate(["program", "program", "ad", "ad", "program"])]

    def test_group_holdout_is_disjoint_even_for_cross_session_creatives(self):
        rows = self.dataset()
        for r in rows:
            if r["session_id"] in ["session-0", "session-1"] and r["manual_label"] == "ad":
                r["creative_id"] = "shared"
        split = grouped_split(rows)
        keys = {name: set().union(*(group_keys(r) for r in part)) for name, part in split.items()}
        self.assertFalse(keys["train"] & keys["test"])
        self.assertFalse(keys["train"] & keys["validation"])
        self.assertFalse(keys["test"] & keys["validation"])

    def test_training_uses_humans_only_and_evaluation_rejects_leakage(self):
        rows = [row(0, "program"), row(1, "ad"), row(2, "ad", features=[0., 1.], label_source="native")]
        model = fit(rows, ".", feature_version="fixture")
        self.assertEqual(model["training_counts"], {"ad": 1, "program": 1})
        self.assertGreater(score(model, [1., 0.]), .7)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            evaluate(rows, model)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            evaluate([row(0, "ad", session="new", creative_id="old")],
                     {**model, "training_group_keys": ["creative_id:old"]})

    def test_insufficient_groups_and_single_class_fail(self):
        with self.assertRaisesRegex(ValueError, "insufficient_data"):
            grouped_split([row(0, "program"), row(1, "ad")])
        with self.assertRaisesRegex(ValueError, "insufficient_data"):
            fit([row(0, "ad")], ".")

    def test_staged_artifact_and_independent_evaluation_written(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prototype.staged.json"
            report = train_experiment(self.dataset(), folder, path)
            model = json.loads(path.read_text())
            self.assertTrue(model["observation_only"])
            self.assertEqual(model["activation"], "staged-only")
            self.assertTrue(path.with_suffix(".evaluation.json").exists())
            self.assertEqual(report["evaluation"]["test"]["status"], "insufficient_data")


if __name__ == "__main__":
    unittest.main()
