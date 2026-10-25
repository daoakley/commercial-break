"""Compare deterministic audio cues with timestamped screenshot labels."""

import bisect
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def load_snapshots(directory, min_confidence=.8):
    observation_path = Path(directory) / "observations.csv"
    if observation_path.exists():
        return sorted((float(row["at_unix"]), row["label"], "")
                      for row in csv.DictReader(observation_path.open())
                      if row["label"] in {"ad", "program"}
                      and float(row["confidence"]) >= min_confidence)
    items = []
    for path in Path(directory).glob("*.json"):
        data = json.loads(path.read_text())
        if data.get("label") in {"ad", "program"} and data.get("confidence", 0) >= min_confidence:
            items.append((float(data["at_unix"]), data["label"], path.stem))
    return sorted(items)


def label_at(timestamp, snapshots, times, max_gap=12):
    position = bisect.bisect_left(times, timestamp)
    nearby = snapshots[max(0, position - 1):position + 1]
    if not nearby:
        return "unknown"
    closest = min(nearby, key=lambda item: abs(item[0] - timestamp))
    if abs(closest[0] - timestamp) > max_gap:
        return "unknown"
    return closest[1]


def analyze(study_dir, screenshot_dir):
    snapshots = load_snapshots(screenshot_dir)
    times = [item[0] for item in snapshots]
    seconds = list(csv.DictReader((Path(study_dir) / "seconds.csv").open()))
    boundaries = list(csv.DictReader((Path(study_dir) / "boundaries.csv").open()))
    audio_times = {int(epoch(row["at_utc"])) for row in seconds}
    grouped = {"program": [], "ad": [], "unknown": []}
    for row in seconds:
        label = label_at(epoch(row["at_utc"]), snapshots, times)
        grouped[label].append(float(row["rms"]))
    boundary_labels = {"program": 0, "ad": 0, "unknown": 0}
    for row in boundaries:
        label = label_at(epoch(row["at_utc"]), snapshots, times)
        boundary_labels[label] += 1
    transitions = []
    previous = None
    for at, label, stem in load_snapshots(screenshot_dir, min_confidence=.5):
        if previous == "program" and label == "ad":
            # An absent candidate is only meaningful where the audio tap ran.
            # The first study ended before later screenshot transitions.
            coverage = sum(int(at) + delta in audio_times for delta in range(-15, 16))
            if coverage < 20:
                previous = label
                continue
            nearby = [round(epoch(row["at_utc"]) - at, 1) for row in boundaries
                      if abs(epoch(row["at_utc"]) - at) <= 15]
            transitions.append((at, stem, nearby, coverage))
        previous = label
    print(f"screenshots={len(snapshots)} audio_seconds={len(seconds)} boundaries={len(boundaries)}")
    for label, values in grouped.items():
        median = round(statistics.median(values), 1) if values else "n/a"
        print(f"{label}: audio_seconds={len(values)} median_rms={median} boundary_candidates={boundary_labels[label]}")
    print(f"covered_program_to_ad_screenshot_transitions={len(transitions)}")
    for at, stem, delays, coverage in transitions:
        print(f"  {datetime.fromtimestamp(at, timezone.utc).isoformat()} screenshot={stem} audio_coverage_31s={coverage} boundary_delay_seconds={delays}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python3 analyze_audio_study.py STUDY_DIR SCREENSHOT_DIR")
    analyze(sys.argv[1], sys.argv[2])
