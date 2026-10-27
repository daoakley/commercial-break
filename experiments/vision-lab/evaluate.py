#!/usr/bin/env python3
"""Causal offline replay against clean human labels; never controls playback."""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from train import extract_features, group_keys, read_rows, score, timestamp, trusted, truth


class CausalDecision:
    def __init__(self, confirmation_frames=2, confidence=.7):
        if confirmation_frames < 1 or not .5 < confidence < 1:
            raise ValueError("confirmation_frames >= 1 and .5 < confidence < 1 required")
        self.confirmation_frames = confirmation_frames
        self.confidence = confidence
        self.reset()

    def reset(self):
        self.pending = "unknown"
        self.count = 0

    def update(self, value):
        if isinstance(value, (float, int)):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Invalid ad similarity score")
            value = "ad" if value >= self.confidence else "program" if value <= 1 - self.confidence else "unknown"
        if value not in ("ad", "program", "unknown"):
            raise ValueError("Invalid decision")
        if value == "unknown":
            self.reset()
            return "unknown"
        self.count = self.count + 1 if value == self.pending else 1
        self.pending = value
        return value if self.count >= self.confirmation_frames else "unknown"


def quantile(values, q):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * q
    lower = int(index)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (index - lower)


def evaluate(rows, model=None, data_dir="data", confirmation_frames=2, confidence=.7,
             max_gap_seconds=5, minimum_hours=1, minimum_breaks=5):
    if max_gap_seconds <= 0 or minimum_hours < 0 or minimum_breaks < 0:
        raise ValueError("Invalid evaluation duration settings")
    if model:
        used = set(model["training_group_keys"])
        overlap = sorted(set().union(*(group_keys(r) for r in rows)) & used) if rows else []
        if overlap:
            raise ValueError("Held-out evaluation overlaps training groups: " + ", ".join(overlap[:5]))
    sessions = defaultdict(list)
    for row in rows:
        sessions[row["session_id"]].append(row)
    stats = dict(evaluated_seconds=0., programming_seconds=0., ad_seconds=0.,
                 false_blocked_seconds=0., ad_seconds_exposed=0., unknown_seconds=0.,
                 false_trigger_events=0, complete_ad_breaks=0, missed_ad_breaks=0,
                 censored_ad_segments=0, excluded_rows=0, human_labelled_rows=0,
                 gap_resets=0, observed_rows=len(rows), censored_restorations=0)
    delays = []
    restoration_delays = []
    for session, items in sessions.items():
        items = sorted(items, key=timestamp)
        times = [timestamp(r) for r in items]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("Duplicate/non-increasing timestamps in session " + str(session))
        smoother = CausalDecision(confirmation_frames, confidence)
        previous_truth = None
        previous_false = False
        ad_run = None
        restoring_from = None
        for i, row in enumerate(items):
            now = times[i]
            reset = i == 0 or now - times[i - 1] > max_gap_seconds
            valid = trusted(row)
            if reset or not valid:
                smoother.reset()
                previous_truth = None
                previous_false = False
                if restoring_from is not None:
                    stats["censored_restorations"] += 1
                    restoring_from = None
                if ad_run is not None:
                    stats["censored_ad_segments"] += 1
                    ad_run = None
                if i and reset:
                    stats["gap_resets"] += 1
            if not valid:
                stats["excluded_rows"] += 1
                continue
            if row.get("contamination", {}).get("status") != "clean":
                prediction = smoother.update("unknown")
            elif model:
                prediction = smoother.update(score(model, extract_features(row, data_dir)))
            else:
                prediction = smoother.update(row.get("prediction", row.get("decision", "unknown")))
            stats["human_labelled_rows"] += 1
            label = truth(row)
            # A sample labels [this timestamp, next timestamp). Large gaps are unobserved.
            duration = times[i + 1] - now if i + 1 < len(items) else 0.
            if duration > max_gap_seconds:
                duration = 0.
            stats["evaluated_seconds"] += duration
            stats["programming_seconds" if label == "program" else "ad_seconds"] += duration
            if prediction == "unknown":
                stats["unknown_seconds"] += duration
            false_block = label == "program" and prediction == "ad"
            if false_block:
                stats["false_blocked_seconds"] += duration
                if not previous_false:
                    stats["false_trigger_events"] += 1
            previous_false = false_block
            if label == "ad":
                if ad_run is None:
                    ad_run = {"start": now, "eligible": previous_truth == "program", "detected": None}
                if prediction == "ad" and ad_run["detected"] is None:
                    ad_run["detected"] = now
                if prediction != "ad":
                    stats["ad_seconds_exposed"] += duration
                if restoring_from is not None:
                    stats["censored_restorations"] += 1
                    restoring_from = None
            else:
                if ad_run is not None:
                    if ad_run["eligible"]:
                        stats["complete_ad_breaks"] += 1
                        if ad_run["detected"] is None:
                            stats["missed_ad_breaks"] += 1
                        else:
                            delays.append(ad_run["detected"] - ad_run["start"])
                    else:
                        stats["censored_ad_segments"] += 1
                    ad_run = None
                    restoring_from = now
                if restoring_from is not None and prediction != "ad":
                    restoration_delays.append(now - restoring_from)
                    restoring_from = None
            previous_truth = label
        if ad_run is not None:
            stats["censored_ad_segments"] += 1
        if restoring_from is not None:
            stats["censored_restorations"] += 1
    hours = stats["evaluated_seconds"] / 3600
    program_hours = stats["programming_seconds"] / 3600
    reasons = []
    if not hours:
        reasons.append("no evaluable time intervals")
    if hours < minimum_hours:
        reasons.append(f"less than {minimum_hours:g} clean human-labelled viewing hours")
    if stats["complete_ad_breaks"] < minimum_breaks:
        reasons.append(f"fewer than {minimum_breaks} complete sampled ad breaks")
    result = {"status": "insufficient_data" if reasons else "diagnostic_only", "reasons": reasons,
            "settings": {"confirmation_frames": confirmation_frames, "confidence": confidence,
                         "max_gap_seconds": max_gap_seconds, "minimum_hours": minimum_hours,
                         "minimum_breaks": minimum_breaks},
            "provenance": {"truth": "clean human labels only", "sessions": len(sessions),
                           "training_group_overlap": False if model else "no model supplied"},
            "counts_and_seconds": stats,
            "metrics": {"viewing_hours": hours,
                        "false_blocked_seconds_per_viewing_hour": stats["false_blocked_seconds"] / hours if hours else None,
                        "false_triggers_per_programming_hour": stats["false_trigger_events"] / program_hours if program_hours else None,
                        "unknown_fraction": stats["unknown_seconds"] / stats["evaluated_seconds"] if hours else None,
                        "onset_median_seconds": quantile(delays, .5), "onset_p95_seconds": quantile(delays, .95),
                        "detected_complete_breaks": len(delays),
                        "restore_median_seconds": quantile(restoration_delays, .5),
                        "restore_p95_seconds": quantile(restoration_delays, .95)},
            "limitations": ["Onsets are sampled human-label transitions, not exact source-video boundaries.",
                            "Intervals use sample-and-hold; the final sample and gaps above the limit add no duration.",
                            "Onset latency excludes missed and censored breaks; inspect those counts alongside latency.",
                            "Unknown means observation-only/no block; no playback action is performed.",
                            "Minimum coverage settings are engineering diagnostics, not a reliability certification."]}
    expirations = [float(r["expires_unix"]) for r in rows if r.get("expires_unix") is not None]
    if expirations:
        result["expires_unix"] = min(expirations)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations")
    parser.add_argument("--model")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output")
    parser.add_argument("--confirmation-frames", type=int, default=2)
    parser.add_argument("--confidence", type=float, default=.7)
    parser.add_argument("--max-gap-seconds", type=float, default=5)
    parser.add_argument("--minimum-hours", type=float, default=1)
    parser.add_argument("--minimum-breaks", type=int, default=5)
    args = parser.parse_args()
    try:
        model = json.loads(Path(args.model).read_text()) if args.model else None
        result = evaluate(read_rows(args.observations), model, args.data_dir,
                          args.confirmation_frames, args.confidence, args.max_gap_seconds,
                          args.minimum_hours, args.minimum_breaks)
    except (ValueError, KeyError, OSError, ImportError) as error:
        print(json.dumps({"status": "error", "reason": str(error)}))
        return 2
    content = json.dumps(result, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(content)
    print(content, end="")
    return 2 if result["status"] == "insufficient_data" else 0


if __name__ == "__main__":
    raise SystemExit(main())
