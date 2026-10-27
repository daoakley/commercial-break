#!/usr/bin/env python3
"""Offline, causal visual diagnostic. Samsung agreement is not accuracy or truth."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import io
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

import numpy as np
from PIL import Image, __version__ as pillow_version

from detector import Detector, fingerprint
import sponsored_badge


def quantile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = int(index)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (index - low)


def summary(values):
    return {"count": len(values), "p50": quantile(values, .5), "p95": quantile(values, .95),
            "max": max(values) if values else None,
            "mean": statistics.fmean(values) if values else None}


def timestamp(row):
    value = row.get("timestamp_unix")
    if value is None:
        value = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("invalid timestamp")
    return value


def comparison_context(row):
    metadata = row.get("metadata", {})
    evidence = metadata.get("tv_debug", {}).get("evidence", {})
    samsung = evidence.get("samsung", {})
    # Preserve unknown as unknown: no AD match does not establish programming.
    verdict = str(samsung.get("verdict", "unknown")).lower()
    if verdict not in ("ad", "program"):
        verdict = "unknown"
    bound = evidence.get("decision", {}).get("sameSession") is True
    native_bound = metadata.get("native_metadata", {}).get("native", {}).get("usable") is True
    human = row.get("label_source") == "human" and row.get("manual_label") in ("ad", "program")
    return verdict, bound, native_bound, human


def diagnose(rows, data_dir, now=None, image_loader=None, verify_badge_equivalence=False):
    """Replay prior-to-current images within each session. No learned prototypes.

    image_loader is injected in regression tests only; the CLI loads retained PNGs.
    File reads and Pillow image decoding occur before measured compute sections.
    """
    now = time.time() if now is None else now
    counts = Counter()
    sessions = defaultdict(list)
    contamination = Counter()
    capture_modes = Counter()
    raw_samsung = Counter()
    stored_decisions = Counter()
    replay_decisions = Counter()
    agreement = Counter()
    extraction_ms, detection_ms, badge_scores, badge_margins = [], [], [], []
    applicable_ms, inapplicable_ms, badge_only_ms, equivalence_errors = [], [], [], []
    top_badges = []
    expiries = []
    root = Path(data_dir).resolve()
    for row in rows:
        counts["observations"] += 1
        contamination[str(row.get("contamination", {}).get("status", "unknown"))] += 1
        verdict, samsung_bound, native_bound, human = comparison_context(row)
        raw_samsung[verdict] += 1
        counts["samsung_same_session"] += int(samsung_bound)
        counts["native_guard_usable"] += int(native_bound)
        counts["human_labelled"] += int(human)
        counts["human_clean_labelled"] += int(human and row.get("contamination", {}).get("status") == "clean")
        counts["original_live_eligible"] += int(row.get("live_decision_eligible") is True)
        stored_decisions[str(row.get("decision", "unknown"))] += 1
        evidence = row.get("metadata", {}).get("tv_debug", {}).get("evidence", {})
        capture_modes[str(evidence.get("capture", {}).get("mode", "unknown"))] += 1
        try:
            stamp = timestamp(row)
            expiry = min(float(row.get("expires_unix", stamp + 48 * 3600)), stamp + 48 * 3600)
            if not math.isfinite(expiry) or expiry <= now:
                counts["expired_excluded"] += 1
                continue
            expiries.append(expiry)
            session = row["session_id"]
            if not isinstance(session, str) or not session:
                raise ValueError("missing session")
            sessions[session].append((stamp, row))
        except (ValueError, TypeError, KeyError):
            counts["invalid_timestamp_or_session"] += 1
    for session, records in sorted(sessions.items()):
        detector = Detector()
        previous_time = None
        for stamp, row in sorted(records, key=lambda item: item[0]):
            if previous_time is not None and stamp <= previous_time:
                counts["duplicate_timestamps_excluded"] += 1
                detector.reset()
                continue
            previous_time = stamp
            if row.get("contamination", {}).get("status") != "clean":
                counts["not_clean_excluded"] += 1
                detector.reset()
                continue
            try:
                if image_loader:
                    image = image_loader(row).convert("RGB")
                else:
                    path = (root / row["image_path"]).resolve()
                    path.relative_to(root)
                    with Image.open(path) as source:
                        source.load()
                        image = source.convert("RGB")
                counts["images_loaded"] += 1
            except (OSError, ValueError, KeyError):
                counts["missing_or_invalid_image"] += 1
                detector.reset()
                continue
            meta = dict(row.get("metadata", {}), session_id=session, timestamp_unix=stamp,
                        contamination=row["contamination"], live_decision_eligible=True)
            started = time.perf_counter()
            fingerprint(image)
            extraction_ms.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            result = detector.observe(image, meta, [])
            elapsed = (time.perf_counter() - started) * 1000
            detection_ms.append(elapsed)
            applicable = meta.get("ui_profile") == "youtube_tv_480x270" and image.size == (480, 270)
            (applicable_ms if applicable else inapplicable_ms).append(elapsed)
            decision = result["decision"]
            replay_decisions[decision] += 1
            counts["replay_eligible"] += 1
            verdict, samsung_bound, _, _ = comparison_context(row)
            if samsung_bound and verdict in ("ad", "program"):
                agreement[verdict + " / " + decision] += 1
                counts["samsung_definite_comparable"] += 1
                counts["same_decision_as_samsung"] += int(verdict == decision)
            if applicable:
                started = time.perf_counter()
                badge_score = sponsored_badge.score_image(image)
                badge_only_ms.append((time.perf_counter() - started) * 1000)
                if verify_badge_equivalence:
                    # Reference verification deliberately outside compute timings.
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    old_score = sponsored_badge.score(buffer.getvalue())
                    equivalence_errors.append(abs(old_score - badge_score))
                    if old_score != badge_score or ((old_score >= sponsored_badge.THRESHOLD) != (badge_score >= sponsored_badge.THRESHOLD)):
                        raise ValueError("fast/reference badge mismatch on " + str(row.get("frame_id")))
                badge_scores.append(badge_score)
                badge_margins.append(badge_score - sponsored_badge.THRESHOLD)
                counts["single_frame_badge_above_threshold"] += int(badge_score >= sponsored_badge.THRESHOLD)
                top_badges.append({"frame_id": row.get("frame_id"), "score": badge_score,
                                   "margin": badge_score - sponsored_badge.THRESHOLD,
                                   "samsung_comparison": verdict if samsung_bound else "unbound",
                                   "local_replay_decision": decision})
    for key in ("observations", "human_labelled", "human_clean_labelled", "original_live_eligible",
                "samsung_same_session", "native_guard_usable", "replay_eligible", "samsung_definite_comparable",
                "same_decision_as_samsung", "single_frame_badge_above_threshold"):
        counts.setdefault(key, 0)
    comparable = counts["samsung_definite_comparable"]
    histogram = {"below_-300": 0, "-300_to_-150": 0, "-150_to_0": 0, "0_to_100": 0, "100_or_more": 0}
    for margin in badge_margins:
        key = ("below_-300" if margin < -300 else "-300_to_-150" if margin < -150 else
               "-150_to_0" if margin < 0 else "0_to_100" if margin < 100 else "100_or_more")
        histogram[key] += 1
    return {
        "schema": "commercial-vision-diagnostics/1", "created_unix": now,
        "expires_unix": min(expiries) if expiries else now,
        "observation_only": True, "offline_replay": True,
        "accuracy_evidence": "insufficient_accuracy_evidence",
        "accuracy_reason": ("No human ground truth labels are present." if not counts["human_clean_labelled"] else
                            "Human labels exist; this diagnostic is not a held-out accuracy evaluation. Use evaluate.py."),
        "truth_policy": "Only explicit manual_label with label_source=human is human truth. Samsung and native observations are comparison evidence only.",
        "counts": dict(counts), "sessions": len(sessions), "contamination": dict(contamination),
        "capture_modes": dict(capture_modes), "samsung_verdict_counts": dict(raw_samsung),
        "stored_live_decisions": dict(stored_decisions), "offline_replay_decisions": dict(replay_decisions),
        "samsung_agreement": {"matrix_samsung_slash_local": dict(agreement),
                              "same_decision_fraction": counts["same_decision_as_samsung"] / comparable if comparable else None,
                              "denominator": comparable,
                              "meaning": "Agreement only, not accuracy. Unknown Samsung results excluded; local unknown remains abstention, not program."},
        "badge": {"threshold": sponsored_badge.THRESHOLD, "scores": summary(badge_scores),
                  "threshold_margins": summary(badge_margins), "margin_histogram": histogram,
                  "equivalence_check": {"enabled": verify_badge_equivalence,
                                        "images_checked": len(equivalence_errors),
                                        "maximum_absolute_error": max(equivalence_errors) if equivalence_errors else None,
                                        "score_tolerance": 0, "threshold_changed": False},
                  "highest_scores": sorted(top_badges, key=lambda row: row["score"], reverse=True)[:10]},
        "timings_ms": {"feature_extraction": summary(extraction_ms),
                       "detector_including_features": summary(detection_ms),
                       "detector_badge_applicable": summary(applicable_ms),
                       "detector_badge_inapplicable": summary(inapplicable_ms),
                       "badge_score_image_only": summary(badge_only_ms),
                       "method": "Single pass, actual retained clean images, CPU wall clock. File I/O and Pillow decoding excluded. Feature extraction measured separately; detector includes its own extraction and direct NumPy badge scoring when applicable. No PNG encode/decode in compute path. Optional reference equivalence audit excluded from timings. Do not add the separate timing groups. No warmup removal, no GPU/TV inference claim."},
        "runtime": {"python": sys.version.split()[0], "platform": platform.platform(),
                    "numpy": np.__version__, "pillow": pillow_version},
        "replay_policy": "Chronological per session; contaminated/missing/duplicate captures reset state. Historical live-gating overridden only offline. Empty sequence library prevents manual prototype leakage; fixed UI template only. Outputs never deployed or used to change labels.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=Path, help="JSONL from storage.py export")
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--output", type=Path, default=Path("/data/artifacts/diagnostics.json"))
    parser.add_argument("--verify-badge-equivalence", action="store_true",
                        help="Audit all applicable real frames against original PNG scorer outside timings")
    args = parser.parse_args()
    with args.observations.open() as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    report = diagnose(rows, args.data_dir, verify_badge_equivalence=args.verify_badge_equivalence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "observations": report["counts"]["observations"],
                      "replay_eligible": report["counts"]["replay_eligible"],
                      "human_labelled": report["counts"]["human_labelled"],
                      "accuracy_evidence": report["accuracy_evidence"]}))


if __name__ == "__main__":
    main()
