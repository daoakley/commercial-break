#!/usr/bin/env python3
"""Offline, observation-only prototype experiment. No detector activation or networking."""
import argparse
import datetime as dt
import hashlib
import json
import math
import random
from pathlib import Path

FEATURE_VERSION = "rgb-8x4-hist8-v1"
LABELS = {"ad", "program"}


def timestamp(row):
    value = row.get("timestamp_unix", row.get("timestamp"))
    if isinstance(value, str):
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("ISO timestamp must include its timezone")
        value = parsed.timestamp()
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Nonfinite timestamp")
    return value


def truth(row):
    return row.get("manual_label", row.get("label"))


def trusted(row):
    return (row.get("label_source") == "human"
            and row.get("contamination", {}).get("status") == "clean"
            and truth(row) in LABELS)


def read_rows(path):
    rows = []
    with open(path) as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not row.get("session_id"):
                raise ValueError(f"Line {line_number}: missing session_id")
            row["timestamp_unix"] = timestamp(row)
            rows.append(row)
    return rows


def extract_features(row, data_dir):
    if "features" in row:
        vector = [float(x) for x in row["features"]]
    else:
        from PIL import Image
        root = Path(data_dir).resolve()
        path = (root / row["image_path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Image path escapes data directory")
        with Image.open(path) as image:
            image = image.convert("RGB")
            thumb = image.resize((8, 4), Image.Resampling.BILINEAR)
            vector = [channel / 255 for pixel in thumb.getdata() for channel in pixel]
            hist = image.resize((64, 36)).histogram()
            for channel in range(3):
                bins = [sum(hist[channel * 256 + i:channel * 256 + i + 32])
                        for i in range(0, 256, 32)]
                vector.extend(x / (64 * 36) for x in bins)
    if not vector or not all(math.isfinite(x) for x in vector):
        raise ValueError("Empty or nonfinite feature vector")
    return vector


def group_keys(row):
    keys = {"session:" + str(row["session_id"])}
    metadata = row.get("metadata", {})
    # Metadata availability can temporarily change an ingestion session hash.
    # Keep those fragments in one physical playback group, not separate splits.
    debug = metadata.get("tv_debug", {})
    context = debug.get("evidence", {}).get("contextBefore", {})
    playback = context.get("session", {})
    if (debug.get("sessionId") and playback.get("engineGeneration") is not None
            and playback.get("navigationGeneration") is not None):
        physical = [debug["sessionId"], playback["engineGeneration"],
                    playback["navigationGeneration"],
                    context.get("foregroundApp", {}).get("value")]
        keys.add("physical_playback:" + hashlib.sha256(json.dumps(physical).encode()).hexdigest())
    content = metadata.get("native_metadata", {}).get("identity", {}).get("content_reference")
    if content:
        keys.add("native_content:" + str(content))
    for kind in ("creative_id", "program_id"):
        value = row.get(kind, metadata.get(kind))
        if value:
            keys.add(kind + ":" + str(value))
    return keys


def grouped_split(rows, seed=7):
    """Connected components prevent session/creative/program overlap across partitions."""
    parent = {}

    def find(key):
        parent.setdefault(key, key)
        while key != parent[key]:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for row in rows:
        keys = sorted(group_keys(row))
        root = find(keys[0])
        for key in keys[1:]:
            parent[find(key)] = root
    groups = {}
    for row in rows:
        groups.setdefault(find("session:" + str(row["session_id"])), []).append(row)
    groups = [groups[key] for key in sorted(groups)]
    if len(groups) < 3:
        raise ValueError("insufficient_data: need at least three independent session/creative/program groups")
    n_test = max(1, round(len(groups) * .2))
    n_val = max(1, round(len(groups) * .2))
    for attempt in range(100):
        candidate = groups[:]
        random.Random(seed + attempt).shuffle(candidate)
        partitions = {"test": candidate[:n_test], "validation": candidate[n_test:n_test + n_val],
                      "train": candidate[n_test + n_val:]}
        split = {name: [r for group in items for r in group] for name, items in partitions.items()}
        if all({truth(r) for r in items if trusted(r)} == LABELS for items in split.values()):
            return split
    raise ValueError("insufficient_data: each independent partition needs clean human ad and program labels")


def fit(rows, data_dir, feature_version=FEATURE_VERSION):
    accepted = [r for r in rows if trusted(r)]
    if {truth(r) for r in accepted} != LABELS:
        raise ValueError("insufficient_data: both clean human-labelled classes required")
    vectors = [extract_features(r, data_dir) for r in accepted]
    dimension = len(vectors[0])
    if any(len(v) != dimension for v in vectors):
        raise ValueError("Feature dimensions differ")
    means = [sum(v[i] for v in vectors) / len(vectors) for i in range(dimension)]
    scales = [max(.02, math.sqrt(sum((v[i] - means[i]) ** 2 for v in vectors) / len(vectors)))
              for i in range(dimension)]
    normalized = [[(x - m) / s for x, m, s in zip(v, means, scales)] for v in vectors]
    centers = {}
    counts = {}
    for label in sorted(LABELS):
        subset = [v for r, v in zip(accepted, normalized) if truth(r) == label]
        counts[label] = len(subset)
        centers[label] = [sum(v[i] for v in subset) / len(subset) for i in range(dimension)]
    return {"schema_version": 1, "kind": "standardized-nearest-centroid",
            "observation_only": True, "activation": "staged-only",
            "feature_version": feature_version, "dimension": dimension,
            "mean": means, "scale": scales, "centroids": centers,
            "training_counts": counts, "training_label_sources": ["human"],
            "training_group_keys": sorted(set().union(*(group_keys(r) for r in rows))),
            "warning": "Similarity scores are not calibrated probabilities. No TV performance claim."}


def score(model, vector):
    if len(vector) != model["dimension"]:
        raise ValueError("Feature dimension does not match model")
    values = [(x - m) / s for x, m, s in zip(vector, model["mean"], model["scale"])]
    distances = {name: sum((x - c) ** 2 for x, c in zip(values, center)) / len(values)
                 for name, center in model["centroids"].items()}
    margin = max(-60, min(60, distances["program"] - distances["ad"]))
    return 1 / (1 + math.exp(-margin))


def train_experiment(rows, data_dir, output, seed=7):
    split = grouped_split(rows, seed)
    model = fit(split["train"], data_dir)
    expirations = [float(r["expires_unix"]) for r in rows if r.get("expires_unix") is not None]
    if expirations:
        model["expires_unix"] = min(expirations)
    model["partition_sessions"] = {name: sorted({r["session_id"] for r in part}) for name, part in split.items()}
    model["coverage_note"] = ("Unseen-creative claims require creative_id coverage; absent IDs only establish session separation.")
    model["creative_id_coverage"] = sum(any(k.startswith("creative_id:") for k in group_keys(r))
                                        for r in rows if trusted(r) and truth(r) == "ad") / max(1, sum(trusted(r) and truth(r) == "ad" for r in rows))
    from evaluate import evaluate
    results = {name: evaluate(part, model=model, data_dir=data_dir)
               for name, part in split.items() if name != "train"}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(model, indent=2) + "\n")
    report = {"status": "experimental_artifact_staged", "model_path": str(output),
              "model_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
              "partitions": model["partition_sessions"], "evaluation": results}
    if expirations:
        report["expires_unix"] = min(expirations)
    output.with_suffix(".evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", help="storage.py export JSONL")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output", default="artifacts/prototype.staged.json")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    try:
        result = train_experiment(read_rows(args.observations), args.data_dir, args.output, args.seed)
    except (ValueError, KeyError, OSError, ImportError) as error:
        print(json.dumps({"status": "insufficient_data" if str(error).startswith("insufficient_data") else "error", "reason": str(error)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
