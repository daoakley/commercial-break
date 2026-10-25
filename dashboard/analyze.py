"""Join human markers to existing classifier records, without claiming frame timing."""
import argparse
import csv
import json
from pathlib import Path


def analyze(labels_path, audit_directory):
    rows = [json.loads(line) for line in labels_path.read_text().splitlines() if line.strip()]
    verdicts = []
    observation_path = audit_directory / "observations.csv"
    if observation_path.exists():
        with observation_path.open() as file:
            for row in csv.DictReader(file):
                try:
                    verdicts.append(dict(at_ms=round(float(row["at_unix"])*1000),
                                         label=row["label"], confidence=float(row["confidence"])))
                except (ValueError, KeyError):
                    pass
    verdicts.sort(key=lambda d: d["at_ms"])
    screenshots = []
    for path in audit_directory.glob("*.png"):
        try:
            screenshots.append((int(path.stem.split("-")[0]), str(path.resolve())))
        except ValueError:
            pass
    undone = {r["target_id"] for r in rows if r["kind"] == "undo"}
    windows = []
    for start in [r for r in rows if r["kind"] == "start"]:
        session = [r for r in rows if r["session_id"] == start["session_id"] and r["id"] not in undone]
        markers = []
        for row in session:
            if row["kind"] not in {"ad", "program", "uncertain", "channel_changed"}:
                continue
            received = row["received_unix_ms"]
            client = row.get("client_unix_ms", received)
            at = client if abs(client-received) <= 2000 else received
            before = next((v for v in reversed(verdicts) if 0 <= at-v["at_ms"] <= 30000), None)
            after = [v for v in verdicts if 0 <= v["at_ms"]-at <= 60000]
            near = sorted(screenshots, key=lambda pair: abs(pair[0]-at))[:4]
            markers.append(dict(kind=row["kind"], click_unix_ms=at,
                last_classifier_result_before=before, classifier_results_after=after[:8],
                nearby_saved_frames=[dict(result_unix_ms=t, path=p) for t,p in sorted(near) if abs(t-at)<=60000]))
        windows.append(dict(session_id=start["session_id"], context=start.get("context"),
                            initial_state=start["initial_state"], start_unix_ms=start["received_unix_ms"],
                            end=next((r for r in session if r["kind"]=="end"), None), markers=markers))
    return dict(windows=windows, limitations=[
        "Human clicks include reaction time; they are not exact video boundaries.",
        "Existing audit timestamps mark classifier-result time, not frame-capture time.",
        "Saved frames are sparse. A nearest frame is evidence to inspect, not a synchronized label.",
        "Classifier results do not prove when the TV overlay appeared.",
        "Only explicitly started windows count as attended observations; uncertain periods must be excluded.",
        "A server-restart closure makes the unattended tail uncertain."])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.labels, args.audit), indent=2))
