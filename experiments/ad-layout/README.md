# Offline advertising-layout test

Research hypothesis: a compact spatial classifier can recognize advertising presentation without memorizing individual ads. This test leaves all TV controls and running collectors unchanged. It is **not ready for deployment**.

## What ran

- Extracted 141 spatial measurements from 1,647 retained, clean 480×270 screenshots.
- Selected 187 review frames deterministically, at roughly 20-second intervals per recorded session. Assistant visual review, without Samsung scores on the sheets, labeled 24 ads/promos,153 program frames and 10 ambiguous/UI frames (excluded). These are **not human-verified labels**.
- Two recorded sessions overlapped the same programs. We therefore split by actual chronological program blocks: industry/border programming versus outdoor programming. No neighboring-frame random split.
- Compared a one-feature flat-region model with an FMPI-inspired spatial RBF SVM. Both used fixed C=1, gamma=scale and balanced class weights. No held-out threshold tuning.
- Masked the Sponsored-pill region before feature extraction, preventing the experiment from counting rediscovery of the existing pill detector as a new capability.
- Used fresh same-session Samsung positives or the existing Sponsored matcher as the **same-frame baseline**. This is not the live blocker's overall success rate: cover leases, sampling gaps, and excluded card-visible images prevent that comparison.

## Results

| Held-out footage | Training / test frames | Additional ad frames from spatial classifier | Additional program false positives | Flat-only false positives |
|---|---:|---:|---:|---:|
| Earlier industry/border block |128 /49 |3 |3 |19 |
| Later outdoor block (forward test) |49 /128 |1 |0 |56 |

Across the two diagnostic folds, the same-frame native baseline identified 12 of 24 reviewed ad frames. Adding the spatial classifier identified 16, while falsely flagging 3 of 153 program frames. The spatial classifier alone identified only 4 of 24 ad frames. **These are sparse, assistant-reviewed frame results, not commercial-break recall, onset timing, or a 70-to 90% effectiveness improvement.**

The false positives were industrial program imagery. The feature extractor took a median 2.96 ms and p 953.24 ms on the development Mac; batched classifier evaluation was below 0.01 ms/frame. These results do not establish Tizen runtime support or TV performance. The extraction uses OpenCV; no TV port or model was deployed.

The forward test trains on only 7 ad frames. The reverse diagnostic trains on 17. Both are too small to settle the method's potential. No cartoons were present. Snowy program frames, subtitles, program photo inserts, graphics and product bottles were represented, but broad sports/news coverage was absent.

## Feature recipe and departures from the paper

The [FMPI paper](https://nlpr.ia.ac.cn/2006 papers/gjhy/gh 41.pdf) describes local color coherence, edge density, Gabor texture and global color/edge-orientation measurements. Our implementation follows its 141-dimensional structure:16 cells ×(3 color-coherence values+1 edge-density value+4 texture values), plus 9 global color and 4 orientation values.

This is an **approximation**, not a reproduction of the reported paper results. We specify 160×96 processing resolution,16 LUV histogram bins per channel, fixed Canny thresholds,11×11 complex Gabor filters, and fixed SVM parameters. Some filter parameters are implementation choices. We also train ad-versus-program labels, whereas the paper's FMPI recognizer targets product-information frames, a narrower category. Author weights were not available. The optional pretrained MAdVerse comparison was not run: checkpoint access was not verified during research.

## Native-event audit

Of 1,647 clean frames,530 contained an ad reference (five distinct references). Stored ad-reference age reached 1,152.9 seconds—about 19.2 minutes. Ten frames had player state 1081, but none carried a verified `inserted_ad.active=true` flag. The retained snapshots do not preserve the full ordered `adPlaying`→player-state sequence required by the existing relay. Consequently, this experiment does **not** validate an event-triggered native detector. A fresh metadata snapshot is not necessarily a fresh ad event.

## Reproduce

Use an isolated Python environment with `requirements.lock`. Run `python test_features.py`. The extractor accepts 480×270 RGB arrays; it never contacts the TV.

`evaluate.py PRIVATE_DIRECTORY --output RESULTS.json` expects:

- `features-private.npz`: arrays `x` (N×141), `flat` (N), and extraction `timings` in milliseconds.
- `rows-private.json`: per-frame `expires`, `samsung`, `same_session`, and boolean `pill` fields.
- `labels-private.json`: review `row` index, `review_index`, `label` (`ad`, `program`, `unknown`) and non-overlapping program `group`.

Evaluation refuses expired evidence and exports no trained model. It writes a private per-frame prediction file and an aggregate report. Never publish screenshots, identifiers, detailed viewing records, credentials, or private labels. The original study remains under its existing 48-hour/debug-stop retention policy. Temporary review images, feature arrays and label/prediction manifests were deleted after this run; only aggregate results and test code are retained.

## Decision

Do not add these classifications to blocking. The test demonstrates a small complementary signal, poor cross-program transfer with the limited training set, and severe failure of flat-color-only classification. Further evaluation needs representative independently checked labels—including cartoons—and a genuinely held-out sequence with real ad boundaries before any performance or deployment claim.
