"""Conservative visual evidence only. Never calls a TV or changes playback."""
from collections import deque

import numpy as np
from PIL import Image

import sponsored_badge


def fingerprint(image):
    """Centered color thumbnail, adapted from work/visual_fingerprint_trial.py."""
    pixels = np.asarray(image.convert("RGB").resize((32, 18), Image.Resampling.BILINEAR),
                        dtype=np.float32)
    pixels -= pixels.mean(axis=(0, 1), keepdims=True)
    vector = pixels.ravel()
    return vector / max(float(np.linalg.norm(vector)), 1e-9)


class Detector:
    def __init__(self, similarity=0.985, max_gap=6.0):
        self.similarity = similarity
        self.max_gap = max_gap
        self.session = None
        self.history = deque(maxlen=32)
        self.badge_hits = deque(maxlen=3)

    def reset(self, session_id=None):
        self.session = session_id
        self.history.clear()
        self.badge_hits.clear()

    def observe(self, image, metadata, prototypes):
        session, timestamp = metadata["session_id"], metadata["timestamp_unix"]
        if session != self.session:
            self.reset(session)
        if self.history and (timestamp <= self.history[-1][0] or
                             timestamp - self.history[-1][0] > self.max_gap):
            self.reset(session)
        result = {"decision": "unknown", "evidence": [], "observation_only": True}
        if not metadata.get("live_decision_eligible", True):
            self.reset(session)
            result["reason"] = "historical_or_future_capture"
            return result
        if metadata["contamination"]["status"] != "clean":
            self.reset(session)
            result["reason"] = "capture_not_verified_clean"
            return result
        vector = fingerprint(image)
        self.history.append((timestamp, vector))

        # Exact known UI profile and pixel geometry only; no arbitrary logo detector.
        if metadata.get("ui_profile") == "youtube_tv_480x270" and image.size == (480, 270):
            score = sponsored_badge.score_image(image)
            if score >= sponsored_badge.THRESHOLD:
                self.badge_hits.append(timestamp)
            else:
                self.badge_hits.clear()
            if (len(self.badge_hits) >= 2 and
                    0.5 <= timestamp - self.badge_hits[0] <= self.max_gap):
                result["evidence"].append({"type": "fixed_ui_sponsored_badge",
                                           "score": round(score, 3),
                                           "hits": len(self.badge_hits)})
        else:
            self.badge_hits.clear()

        # At least three ordered images and matching capture intervals. An isolated
        # visually similar frame or a repeated static program logo cannot trigger.
        if len(self.history) >= 3:
            history = list(self.history)
            if history[-1][0] - history[0][0] >= 2.0:
                for prototype in prototypes:
                    points = prototype["points"]
                    for start in range(len(points) - 2):
                        window = points[start:start + 3]
                        if window[-1]["offset"] - window[0]["offset"] < 2.0:
                            continue
                        # Align to reference time offsets, not arrival count: extra
                        # capture frames must not break a valid repeated sequence.
                        target_times = [timestamp - window[-1]["offset"] + point["offset"]
                                        for point in window]
                        recent = [min(history, key=lambda item: abs(item[0] - target))
                                  for target in target_times]
                        if not recent[0][0] < recent[1][0] < recent[2][0]:
                            continue
                        if any(abs((recent[i][0] - recent[i-1][0]) -
                                   (window[i]["offset"] - window[i-1]["offset"])) >
                               max(0.75, 0.35 * (window[i]["offset"] - window[i-1]["offset"]))
                               for i in (1, 2)):
                            continue
                        refs = [np.asarray(point["vector"], dtype=np.float32) for point in window]
                        if all(float(np.dot(refs[0], ref)) > .97 for ref in refs[1:]):
                            continue  # No static-scene sequence confirmation.
                        scores = [float(np.dot(item[1], ref)) for item, ref in zip(recent, refs)]
                        if min(scores) >= self.similarity:
                            result["evidence"].append({"type": "human_confirmed_ad_sequence",
                                                       "prototype_id": prototype["prototype_id"],
                                                       "name": prototype["name"],
                                                       "min_similarity": round(min(scores), 5),
                                                       "matched_frames": 3})
                            break
        if result["evidence"]:
            result["decision"] = "ad"
        return result
