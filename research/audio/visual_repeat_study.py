"""Offline, observation-only test of repeated-ad video fingerprints.

The source frames and Claude labels are private. This script neither contacts
the TV nor has a path to its mute control. A fixed early library is evaluated
on later frames, so adjacent captures of one break cannot count as a replay.
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image


SIDE = 32
LOW_FREQUENCIES = 8
MIN_REPLAY_GAP_SECONDS = 180


def perceptual_hash(path):
    image = Image.open(path).convert("L").resize((SIDE, SIDE), Image.Resampling.LANCZOS)
    pixels = np.asarray(image, dtype=np.float32)
    axis = np.arange(SIDE, dtype=np.float32)
    basis = np.cos(np.pi * (axis[:, None] + .5) * axis[None, :] / SIDE)
    spectrum = basis[:LOW_FREQUENCIES] @ pixels @ basis[:LOW_FREQUENCIES].T
    coefficients = spectrum.flatten()[1:]
    median = float(np.median(coefficients))
    bits = coefficients >= median
    return sum(int(bit) << position for position, bit in enumerate(bits))


def color_thumbnail(path):
    image = Image.open(path).convert("RGB").resize((48, 27), Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.uint8)


def mean_pixel_error(left, right):
    return float(np.abs(left.astype(np.int16) - right.astype(np.int16)).mean())


def load_frames(directory):
    frames = []
    for metadata_path in Path(directory).glob("*.json"):
        image_path = metadata_path.with_suffix(".png")
        if not image_path.is_file():
            continue
        try:
            metadata = json.loads(metadata_path.read_text())
            label = metadata["label"]
            if label not in {"ad", "program", "uncertain"}:
                continue
            frames.append({
                "at": float(metadata["at_unix"]),
                "label": label,
                "confidence": float(metadata["confidence"]),
                "app": metadata.get("app") or "",
                "path": image_path,
            })
        except (OSError, ValueError, KeyError, TypeError):
            continue
    frames.sort(key=lambda frame: frame["at"])
    for frame in frames:
        frame["hash"] = perceptual_hash(frame["path"])
        frame["thumbnail"] = color_thumbnail(frame["path"])
    return frames


def evaluate(frames, *, library_fraction=.5, holdout_fraction=.25, thresholds=(4, 8, 12)):
    if not 0 < library_fraction < 1 - holdout_fraction < 1:
        raise ValueError("invalid chronological split")
    library_end = int(len(frames) * library_fraction)
    holdout_start = int(len(frames) * (1 - holdout_fraction))
    library = [frame for frame in frames[:library_end]
               if frame["label"] == "ad" and frame["confidence"] >= .9]
    results = {}
    for name, trial in (("calibration", frames[library_end:holdout_start]),
                        ("held_out", frames[holdout_start:])):
        cases = []
        for frame in trial:
            if frame["label"] not in {"ad", "program"} or frame["confidence"] < .9:
                continue
            eligible = [prior for prior in library
                        if prior["app"] == frame["app"]
                        and frame["at"] - prior["at"] >= MIN_REPLAY_GAP_SECONDS]
            nearest = min(((frame["hash"] ^ prior["hash"]).bit_count(),
                           prior["path"].name) for prior in eligible) if eligible else None
            color_candidates = [
                (round(mean_pixel_error(frame["thumbnail"], prior["thumbnail"]), 1),
                 prior["path"].name)
                for prior in eligible
                if (frame["hash"] ^ prior["hash"]).bit_count() <= 12
            ]
            color_nearest = min(color_candidates) if color_candidates else None
            cases.append((frame, nearest, color_nearest))
        results[name] = {
            "period": (
                datetime.fromtimestamp(trial[0]["at"], timezone.utc).isoformat()
                if trial else None,
                datetime.fromtimestamp(trial[-1]["at"], timezone.utc).isoformat()
                if trial else None,
            ),
            "counts": dict(Counter(frame["label"] for frame, _, _ in cases)),
            "thresholds": {
                threshold: dict(Counter(frame["label"] for frame, nearest, _ in cases
                                        if nearest is not None and nearest[0] <= threshold))
                for threshold in thresholds
            },
            "color_verified": {
                threshold: dict(Counter(frame["label"] for frame, _, nearest in cases
                                        if nearest is not None and nearest[0] <= threshold))
                for threshold in (10, 15, 20, 25)
            },
            "nearest_program": sorted(
                ((nearest[0], frame["path"].name, nearest[1]) for frame, nearest, _ in cases
                 if frame["label"] == "program" and nearest is not None))[:5],
            "nearest_ad": sorted(
                ((nearest[0], frame["path"].name, nearest[1]) for frame, nearest, _ in cases
                 if frame["label"] == "ad" and nearest is not None))[:5],
            "nearest_color_program": sorted(
                ((nearest[0], frame["path"].name, nearest[1]) for frame, _, nearest in cases
                 if frame["label"] == "program" and nearest is not None))[:5],
            "nearest_color_ad": sorted(
                ((nearest[0], frame["path"].name, nearest[1]) for frame, _, nearest in cases
                 if frame["label"] == "ad" and nearest is not None))[:5],
        }
    return {"total_frames": len(frames), "library_ads": len(library), "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(load_frames(args.audit_dir)), indent=2))


if __name__ == "__main__":
    main()
