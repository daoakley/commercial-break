"""Summarize observation-only fingerprint scores against nearby TV frames."""

import bisect
import csv
import statistics
import sys
from pathlib import Path

from analyze_audio_study import epoch, label_at, load_snapshots


def frame_context(timestamp, snapshots, times, max_gap=12):
    """Avoid assigning a label across two screenshots that bracket a change."""
    position = bisect.bisect_left(times, timestamp)
    if 0 < position < len(snapshots):
        before, after = snapshots[position - 1], snapshots[position]
        if (before[1] != after[1]
                and timestamp - before[0] <= max_gap
                and after[0] - timestamp <= max_gap):
            return "transition"
    return label_at(timestamp, snapshots, times, max_gap=max_gap)


def first_reports(candidates, separation=15):
    """Group repeated reports of one match, retaining its first arrival."""
    groups = []
    for candidate in sorted(candidates, key=lambda item: epoch(item[0])):
        if not groups or epoch(candidate[0]) - epoch(groups[-1][-1][0]) > separation:
            groups.append([candidate])
        else:
            groups[-1].append(candidate)
    return [min(group, key=lambda item: epoch(item[3])) for group in groups]


def analyze(study_dir, screenshot_dir):
    snapshots = load_snapshots(screenshot_dir)
    times = [item[0] for item in snapshots]
    path = Path(study_dir) / "fingerprint_scores.csv"
    rows = list(csv.DictReader(path.open()))
    grouped = {"program": [], "ad": [], "transition": [], "unknown": []}
    candidates = []
    for row in rows:
        at = epoch(row["matched_audio_utc"])
        label = frame_context(at, snapshots, times)
        score = float(row["score"])
        grouped[label].append(score)
        if int(row["candidate"]):
            candidates.append((row["matched_audio_utc"], label, score,
                               row.get("received_at_utc", "")))
    events = first_reports(candidates)
    print(f"scored_chunks={len(rows)} candidate_rows={len(candidates)} candidate_events={len(events)}")
    for label, scores in grouped.items():
        median = round(statistics.median(scores), 4) if scores else "n/a"
        maximum = round(max(scores), 4) if scores else "n/a"
        print(f"{label}: chunks={len(scores)} median={median} max={maximum}")
    for timestamp, label, score, received in events:
        delay = round(epoch(received) - epoch(timestamp), 1) if received else "n/a"
        print(f"candidate {timestamp} nearby_label={label} score={score:.4f} detection_delay_seconds={delay}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python3 analyze_fingerprint_shadow.py STUDY_DIR SCREENSHOT_DIR")
    analyze(sys.argv[1], sys.argv[2])
