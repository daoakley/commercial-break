#!/usr/bin/env python3
"""Staged Samsung-positive exemplar experiment. Never activates a live detector."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import statistics
import time

from train import read_rows, timestamp

DEFAULT_SOURCE = "com.samsung.tv.cobalt-yttv"
THRESHOLDS = (.985, .99, .995, .999)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def expiration(row):
    values = [timestamp(row) + 48 * 3600]
    for value in (row.get("expires_unix"), row.get("metadata", {}).get("session_expires_unix")):
        if finite(value):
            values.append(value)
    return min(values)


def evidence(row):
    return row.get("metadata", {}).get("tv_debug", {}).get("evidence", {})


def human(row):
    return row.get("manual_label") if row.get("label_source") == "human" else None


def usable(row, now, source):
    if row.get("contamination", {}).get("status") != "clean":
        return "not_clean"
    if expiration(row) <= now or timestamp(row) > now + 2:
        return "expired_or_future"
    if row.get("source") != source:
        return "source_not_allowed"
    if not row.get("session_id"):
        return "missing_session"
    return None


def positive_rejection(row):
    ev = evidence(row)
    if human(row) == "program":
        return "human_program_veto"
    if ev.get("samsung", {}).get("verdict") != "ad":
        return "no_teacher_ad"
    if ev.get("decision", {}).get("sameSession") is not True:
        return "teacher_not_same_session"
    if ev.get("samsung", {}).get("error"):
        return "teacher_error"
    capture = ev.get("capture", {})
    if capture.get("mode") not in ("normal", "panel-masked"):
        return "unverified_capture_mode"
    start, fingerprint = capture.get("captureStartedAt"), capture.get("fingerprintAt")
    if not finite(start) or not finite(fingerprint):
        return "missing_capture_alignment"
    if abs(start - fingerprint) > 2000 or abs(timestamp(row) - start / 1000) > 2:
        return "capture_alignment_over_2_seconds"
    for context in ("contextBefore", "contextAfter"):
        app = ev.get(context, {}).get("foregroundApp", {}).get("value")
        if app is not None and app != row.get("source"):
            return "source_context_mismatch"
    return None


def normalized(vector):
    values = [float(x) for x in vector]
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError("nonfinite or empty fingerprint")
    norm = math.sqrt(sum(x * x for x in values))
    if norm < 1e-8:
        raise ValueError("uninformative zero fingerprint")
    return [x / norm for x in values]


def load_vector(row, data_dir):
    from PIL import Image
    from detector import fingerprint
    root = Path(data_dir).resolve()
    path = (root / row["image_path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("image path escapes data directory")
    with Image.open(path) as image:
        image.load()
        started = time.perf_counter()
        vector = fingerprint(image)
        elapsed = (time.perf_counter() - started) * 1000
    return normalized(vector), elapsed


def bursts(positives, max_gap=30):
    per_context = defaultdict(list)
    for row in positives:
        per_context[(row["source"], row["session_id"])].append(row)
    result = []
    for key, items in per_context.items():
        current = []
        for row in sorted(items, key=timestamp):
            if current and timestamp(row) - timestamp(current[-1]) > max_gap:
                result.append(current)
                current = []
            current.append(row)
        if current:
            result.append(current)
    return sorted(result, key=lambda group: timestamp(group[0]))


def chronological_split(groups, embargo=30):
    if embargo < 30:
        raise ValueError("embargo must be at least 30 seconds")
    if len(groups) < 3:
        return None
    first = max(1, min(len(groups) - 2, int(len(groups) * .6)))
    second = max(first + 1, min(len(groups) - 1, int(len(groups) * .8)))
    val_start, test_start = timestamp(groups[first][0]), timestamp(groups[second][0])
    parts = {"train": [], "validation": [], "test": [], "excluded_boundary_bursts": []}
    for group in groups:
        start, end = timestamp(group[0]), timestamp(group[-1])
        if end <= val_start - embargo:
            parts["train"].extend(group)
        elif start >= val_start and end <= test_start - embargo:
            parts["validation"].extend(group)
        elif start >= test_start:
            parts["test"].extend(group)
        else:
            parts["excluded_boundary_bursts"].append([r["frame_id"] for r in group])
    if any(not parts[name] for name in ("train", "validation", "test")):
        return None
    parts["boundaries"] = {"validation_start": val_start, "test_start": test_start, "embargo_seconds": embargo}
    return parts


def stage_model(rows, vectors, source, expires, max_exemplars=256):
    if max_exemplars < 1:
        raise ValueError("max_exemplars must be positive")
    rows = sorted(rows, key=timestamp)
    if len(rows) > max_exemplars:
        indices = sorted({round(i * (len(rows) - 1) / max(1, max_exemplars - 1)) for i in range(max_exemplars)})
        rows = [rows[i] for i in indices]
    return {"schema_version": 1, "kind": "samsung-positive-nearest-exemplar",
            "observation_only": True, "activation": "staged-only", "teacher": "Samsung ad verdict",
            "human_ground_truth": False, "feature_version": "centered-rgb-32x18-l2-v1",
            "allowed_sources": [source], "fixed_similarity_threshold": .985,
            "expires_unix": expires,
            "exemplars": [{"frame_id": r["frame_id"], "session_id": r["session_id"], "source": r["source"],
                           "timestamp_unix": timestamp(r), "vector": vectors[r["frame_id"]]} for r in rows],
            "limitations": "Teacher mimicry / visual matching only. Unknown never means program. No live activation."}


def nearest(model, vector, source):
    if source not in model["allowed_sources"]:
        return None
    candidates = [x["vector"] for x in model["exemplars"] if x["source"] == source]
    if not candidates:
        return None
    if any(len(x) != len(vector) for x in candidates):
        raise ValueError("fingerprint dimension mismatch")
    return max(sum(a * b for a, b in zip(vector, candidate)) for candidate in candidates)


def timing(values):
    if not values:
        return {"count": 0, "median_ms": None, "p95_ms": None}
    ordered = sorted(values)
    return {"count": len(values), "median_ms": statistics.median(values),
            "p95_ms": ordered[min(len(ordered) - 1, math.ceil(len(ordered) * .95) - 1)]}


def measure(rows, model, vectors, positive_ids):
    scored = []
    times = []
    train_ids = {r["frame_id"] for r in model["exemplars"]}
    if train_ids.intersection(r["frame_id"] for r in rows):
        raise ValueError("heldout rows overlap training exemplars")
    for row in rows:
        start = time.perf_counter()
        similarity = nearest(model, vectors[row["frame_id"]], row["source"])
        times.append((time.perf_counter() - start) * 1000)
        scored.append((row, similarity))
    sweep = []
    for threshold in THRESHOLDS:
        counts = Counter()
        for row, similarity in scored:
            active = similarity is not None and similarity >= threshold
            if row["frame_id"] in positive_ids:
                category = "teacher_positive"
            elif human(row) == "program":
                category = "human_negative"
            elif human(row) == "ad":
                category = "human_positive"
            else:
                category = "unlabelled"
            counts[category] += 1
            counts[category + "_activated"] += int(active)
        def rate(name):
            return counts[name + "_activated"] / counts[name] if counts[name] else None
        sweep.append({"threshold": threshold, "counts": dict(counts),
                      "teacher_positive_recovery": rate("teacher_positive"),
                      "unlabelled_activation_rate_not_false_positive_rate": rate("unlabelled"),
                      "human_negative_false_positive_rate": rate("human_negative"),
                      "human_positive_recovery": rate("human_positive")})
    return {"observations": len(rows), "threshold_sweep_descriptive_only": sweep, "nearest_exemplar_compute": timing(times)}


def experiment(rows, data_dir, output_dir, source=DEFAULT_SOURCE, now=None, vector_loader=None, max_exemplars=256):
    now = time.time() if now is None else now
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    # These filenames belong exclusively to this experiment. A failed/shorter
    # rerun must never leave an older model looking like its current result.
    for name in ("teacher-all-positive.staged.json", "teacher-heldout-train.staged.json", "teacher-experiment.json"):
        (output / name).unlink(missing_ok=True)
    rejected = Counter()
    positive_rejections = Counter()
    usable_rows, positives, vectors, extract_times, expiries = [], [], {}, [], []
    seen = set()
    for row in sorted(rows, key=timestamp):
        identity = row.get("frame_id")
        if not identity or identity in seen:
            rejected["missing_or_duplicate_frame_id"] += 1
            continue
        seen.add(identity)
        reason = usable(row, now, source)
        if reason:
            rejected[reason] += 1
            continue
        try:
            vector, duration = vector_loader(row) if vector_loader else load_vector(row, data_dir)
            vector = normalized(vector)
        except (OSError, ValueError, KeyError) as error:
            rejected["image_or_fingerprint_unavailable"] += 1
            continue
        vectors[identity] = vector
        extract_times.append(duration)
        usable_rows.append(row)
        expiries.append(expiration(row))
        reason = positive_rejection(row)
        if reason:
            positive_rejections[reason] += 1
        else:
            positives.append(row)
    report = {"status": "insufficient_data", "observation_only": True, "source_binding": source,
              "fixed_threshold": .985, "input_observations": len(rows), "usable_observations": len(usable_rows),
              "teacher_positives": len(positives), "rejected_observations": dict(rejected),
              "positive_exclusions": dict(positive_rejections), "fingerprint_compute": timing(extract_times),
              "limitations": ["Samsung labels are noisy teacher signals, not independent ground truth.",
                              "Image and fingerprint use separate capture paths; <=2s alignment does not prove identical content.",
                              "Bursts are source/session bounded, but disjoint bursts from one session may occur in multiple partitions.",
                              "Chronological burst holdout is not unseen-creative or unseen-session evaluation; repeated ads may cross partitions.",
                              "Unlabelled activation is not a false-positive rate; unknown is never a negative training label.",
                              "Threshold sweep is descriptive; fixed .985 was not selected on test results.",
                              "Compute timings are local environment measurements, not Samsung TV benchmarks.",
                              "No heldout score is computed using the separate all-positive candidate."]}
    if not positives:
        report["reason"] = "No eligible clean, aligned, unexpired Samsung-positive examples. No candidate staged."
        report["expires_unix"] = min((expiration(r) for r in usable_rows), default=now)
        (output / "teacher-experiment.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    expires = min(expiries)
    report["expires_unix"] = expires
    candidate = stage_model(positives, vectors, source, expires, max_exemplars)
    candidate["role"] = "all-positive-candidate-not-heldout"
    (output / "teacher-all-positive.staged.json").write_text(json.dumps(candidate) + "\n")
    report["all_positive_candidate"] = {"path": str(output / "teacher-all-positive.staged.json"),
                                         "exemplars": len(candidate["exemplars"]), "heldout_claim": False}
    groups = bursts(positives)
    report["positive_bursts"] = len(groups)
    split = chronological_split(groups)
    if split is None:
        report["reason"] = "Insufficient complete positive bursts after chronological split and >=30s embargo; no heldout claim."
    else:
        model = stage_model(split["train"], vectors, source, expires, max_exemplars)
        model["role"] = "heldout-train-only"
        model["training_positive_ids"] = [r["frame_id"] for r in split["train"]]
        (output / "teacher-heldout-train.staged.json").write_text(json.dumps(model) + "\n")
        bounds = split["boundaries"]
        val, test = bounds["validation_start"], bounds["test_start"]
        excluded_ids = {item for group in split["excluded_boundary_bursts"] for item in group}
        validation = [r for r in usable_rows if val <= timestamp(r) <= test - 30 and r["frame_id"] not in excluded_ids]
        testing = [r for r in usable_rows if timestamp(r) >= test and r["frame_id"] not in excluded_ids]
        positive_ids = {r["frame_id"] for r in positives}
        report.update(status="teacher_mimicry_diagnostic_only", heldout_claim="chronological burst recovery only",
                      boundaries=bounds, excluded_boundary_bursts=split["excluded_boundary_bursts"],
                      train_positive_count=len(split["train"]),
                      train_exemplars=len(model["exemplars"]),
                      validation=measure(validation, model, vectors, positive_ids),
                      test=measure(testing, model, vectors, positive_ids))
    (output / "teacher-experiment.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations")
    parser.add_argument("--data-dir", default="/data")
    parser.add_argument("--output-dir", default="/data/artifacts")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--max-exemplars", type=int, default=256)
    args = parser.parse_args()
    try:
        # Keep CLI artifacts inside the managed retention directory.
        output = Path(args.output_dir).resolve()
        managed = (Path(args.data_dir).resolve() / "artifacts")
        if not output.is_relative_to(managed):
            raise ValueError("output-dir must be inside data-dir/artifacts")
        report = experiment(read_rows(args.observations), args.data_dir, output,
                            args.source, max_exemplars=args.max_exemplars)
    except (ValueError, KeyError, OSError, ImportError) as error:
        print(json.dumps({"status": "error", "reason": str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["status"] != "insufficient_data" else 2


if __name__ == "__main__":
    raise SystemExit(main())
