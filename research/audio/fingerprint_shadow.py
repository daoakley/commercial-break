"""Observation-only matcher for owner-validated, repeated TV ads.

It records scores for every audio chunk. It has no TV control path.
"""

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from audio_fingerprint_trial import (RATE, best_match, descriptors,
                                     pcm_to_mono, read_wav)


class FingerprintShadow:
    def __init__(self, manifest_path, output_path):
        manifest = json.loads(Path(manifest_path).read_text())
        self.templates = []
        for item in manifest["ads"]:
            name = str(item["name"])
            offset = float(item["offset_seconds"])
            duration = float(item.get("duration_seconds", 5))
            if not 0 <= offset or not 3 <= duration <= 8:
                raise ValueError("invalid fingerprint window")
            signal = read_wav(Path(item["wav"]))
            window = signal[int(offset * RATE):int((offset + duration) * RATE)]
            if len(window) < int(duration * RATE):
                raise ValueError("fingerprint source is shorter than its window")
            self.templates.append((name, descriptors(window)))
        if not self.templates:
            raise ValueError("fingerprint library is empty")
        self.output = Path(output_path)
        self.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.output.parent.chmod(0o700)
        if not self.output.exists():
            with self.output.open("w", newline="") as file:
                csv.writer(file).writerow(["chunk_start_utc", "template", "score",
                                           "matched_audio_utc", "candidate",
                                           "received_at_utc"])
            self.output.chmod(0o600)
        self.segments = []

    def observe(self, raw, start):
        mono = pcm_to_mono(raw)
        if self.segments:
            previous_start, previous = self.segments[-1]
            duration = len(previous) / RATE
            if not duration - 1 <= start - previous_start <= duration + 1:
                self.segments.clear()
        self.segments.append((start, mono))
        while sum(len(part) for _, part in self.segments) > 20 * RATE:
            self.segments.pop(0)
        search = np.concatenate([part for _, part in self.segments])
        base = self.segments[0][0]
        candidate = descriptors(search)
        matches = []
        for name, template in self.templates:
            match = best_match(template, candidate)
            if match is not None:
                matches.append((match[0], name, base + match[1]))
        if not matches:
            return None
        score, name, matched_at = max(matches)
        stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="milliseconds")
        with self.output.open("a", newline="") as file:
            csv.writer(file).writerow([stamp(start), name, score,
                                       stamp(matched_at), int(score >= .90),
                                       stamp(time.time())])
        return score, name, matched_at
