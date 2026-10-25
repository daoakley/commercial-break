"""Deterministic, offline candidates for TV audio edit boundaries.

This module does not label commercials or control mute. Feed contiguous
48 kHz stereo S16_LE PCM; gaps between samples invalidate timing.
"""

import array
import math
import statistics
import sys
from dataclasses import dataclass


SAMPLE_RATE = 48000
CHANNELS = 2
FRAME_MS = 10
SAMPLES_PER_FRAME = SAMPLE_RATE * CHANNELS * FRAME_MS // 1000


@dataclass(frozen=True)
class BoundaryCandidate:
    offset_seconds: float
    silence_ms: int
    before_rms: float
    during_rms: float
    after_rms: float
    depth: float


def rms_frames(pcm):
    """Return 10 ms RMS values; trailing partial frames are ignored."""
    if len(pcm) % 2:
        raise ValueError("S16_LE PCM must contain complete 16-bit values")
    values = array.array("h")
    values.frombytes(pcm)
    if sys.byteorder != "little":
        values.byteswap()
    frames = []
    for start in range(0, len(values) - SAMPLES_PER_FRAME + 1, SAMPLES_PER_FRAME):
        part = values[start : start + SAMPLES_PER_FRAME]
        frames.append(math.sqrt(sum(value * value for value in part) / len(part)))
    return frames


def find_candidates(pcm, *, base_offset_seconds=0.0):
    """Locate short deep dips with active sound on both sides.

    A candidate is only a possible edit boundary. Dialogue, scene cuts,
    dropouts, and channel changes can produce the same pattern.
    """
    frames = rms_frames(pcm)
    if len(frames) < 45:
        return []
    active = [value for value in frames if value > 25]
    if not active:
        return []
    baseline = statistics.median(active)
    threshold = min(100.0, max(12.0, baseline * 0.04))
    result = []
    index = 20
    while index < len(frames) - 20:
        if frames[index] > threshold:
            index += 1
            continue
        start = index
        while index < len(frames) and frames[index] <= threshold:
            index += 1
        end = index
        duration = (end - start) * FRAME_MS
        if not 10 <= duration <= 300 or end + 20 > len(frames):
            continue
        before = statistics.median(frames[start - 20:start])
        after = statistics.median(frames[end:end + 20])
        # A show may fade down over its end credits before the first ad.
        # Keep such asymmetric edits as candidates; later visual checks must
        # reject ordinary quiet scenes and speech pauses.
        if min(before, after) < max(75.0, baseline * 0.05):
            continue
        if max(before, after) < max(300.0, baseline * 0.25):
            continue
        during = statistics.median(frames[start:end])
        depth = 1.0 - during / min(before, after)
        if depth < 0.9:
            continue
        result.append(BoundaryCandidate(
            base_offset_seconds + start * FRAME_MS / 1000,
            duration, round(before, 1), round(during, 1), round(after, 1),
            round(depth, 3),
        ))
    return result
