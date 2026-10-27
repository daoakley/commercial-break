"""Replay private labeled samples; emits aggregates only and never controls a TV.

See README.md for the manifest contract. Run with this experiment's directory
on PYTHONPATH. The source manifest and its images remain private and must follow
the original capture session's deletion deadline.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from banner_continuity import BannerMemory


def replay(manifest):
    rows = json.loads(manifest.read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError('Manifest must be a nonempty array of metadata events')
    for row in rows:
        if row['expires_at'] <= time.time():
            raise ValueError('Expired private evidence cannot be replayed')
    memory = BannerMemory()
    counts = dict(ad_frames=0, program_frames=0, baseline_true_positive=0,
                  baseline_false_positive=0, combined_true_positive=0,
                  combined_false_positive=0, teacher_anchors_added=0)
    for row in sorted(rows, key=lambda item: item['captured_at']):
        at, session = row['captured_at'], row['session']
        memory.advance(at, session)  # Include navigation even without pixels.
        if not row.get('clean') or not row.get('image'):
            continue
        image = Path(row['image'])
        if not image.is_absolute():
            image = manifest.parent / image
        with Image.open(image) as loaded:
            rgb = np.asarray(loaded.convert('RGB'))
        candidate = memory.query(rgb, at, session)
        label = row.get('label')
        if label in ('ad', 'program'):
            baseline = row['baseline_positive'] is True
            is_ad = label == 'ad'
            counts['ad_frames' if is_ad else 'program_frames'] += 1
            suffix = 'true_positive' if is_ad else 'false_positive'
            counts['baseline_' + suffix] += int(baseline)
            counts['combined_' + suffix] += int(baseline or candidate)
        if row.get('trusted_ad') is True:
            # This must already be validated by the native application's
            # exact-capture, same-session, fresh-response AD predicate.
            available_at = row['teacher_accepted_at']
            added = memory.seed(rgb, at, session, True, True, available_at)
            counts['teacher_anchors_added'] += int(added)
    baseline = counts['baseline_true_positive']
    combined = counts['combined_true_positive']
    counts['relative_true_positive_gain'] = (
        (combined - baseline) / baseline if baseline else None)
    counts['status'] = 'offline_observation_only_not_live_validation'
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.manifest)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
