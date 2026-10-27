# Observation-only banner continuity experiment

**A small exploratory replay improved detected ad frames from 11 to 13 out of
17 (+18.2% relative), with no additional positives in 111 program frames. This
is not a demonstrated 20% improvement, a live result, or a general ad detector.**
Both additional frames belonged to one previously recognized direct-response
commercial. The technique may prevent a cover dropping during an ad Samsung
already recognized; it does not identify a new ad's opening frame.

Nothing here is installed on the TV or connected to playback controls. The
running Samsung, Sponsored-label, and fixed 141-feature layout detectors remain
unchanged.

## Technique

When the existing strict Samsung validator confirms an ad, remember a small
bottom strip from that frame. Subsequent frames may confirm that the same
advertiser graphic is still present even if Samsung returns an unknown result.
The local matcher uses existing image operations, without an LLM or neural image
encoder:

- The fixed region is x=30..449, y=235..269 in 480x270 RGB.
- Standard deviation must be at least 15, and Canny edge occupancy must exceed
  0.005 in each of three horizontal thirds. These checks reject blank strips
  and an isolated corner logo; they do not understand the text semantically.
- Match requires normalized correlation >=0.95 and mean absolute RGB error <=15.
- Only a clean, exact-capture, same-session **Samsung positive** can create an
  anchor. A local match cannot create an anchor or extend its lifetime.
- An anchor is unavailable before the Samsung response arrives. Responses over
  eight seconds after capture are rejected. Anchors expire 120 seconds after
  their original capture and clear on navigation/app/session changes or a clock
  reversal. Replay must process metadata resets even when pixels are missing.
- At most 32 patches are retained in memory (1,411,200 RGB bytes, excluding
  language/runtime overhead). No screenshot archive or persistent bank is used.

The preset image thresholds were fixed before replay. The hypothesis itself was
chosen after inspecting the historical misses, so this is development evidence.
A future deployment would also need an effective navigation identity, fail-open
integration, invalid-frame rejection, and on-TV resource measurements.

## Evidence and limits

The baseline combines same-frame fresh Samsung positives, the Sponsored detector,
and the deployed 141-feature SVM with its original 49-frame training set and 0.5
margin. The evaluated later block contains 17 assistant-labeled ad frames and 111
program frames. Seven uncertain frames were excluded. No new labels were used to
retrain that baseline.

The new matcher learned only from earlier clean Samsung positives, respecting
response availability. It added two frames from the same glove commercial whose
persistent phone/URL banner crossed multiple shots. Missing ad frames fell from
six to four (33.3% fewer misses), while true-positive frames increased 18.2%.
These are different metrics. Neither establishes ad-break recall, seconds of ads
hidden, onset latency, or performance across independent advertising creatives.

A later untouched sample contained 16 assistant-reviewed cartoon program frames
and no ads. No historical ad template matched any of those frames under the
fixed criteria. This was a **counterfactual template stress test**: in a true
chronological run the old 120-second anchors would already have expired. It adds
negative evidence, not validation of ad recall or an estimated false-alarm rate.
The thresholds were not tuned on these cartoons.

Matching all 29 retained development templates against those cartoon frames took
about 0.86 ms median / 1.13 ms p95 on the Mac. These are host-only measurements,
not TV timing. There is no measured on-TV cost for this new matcher yet.

Other tested directions were rejected: adding spatial color means gave no new
hits; expanding the layout SVM with 22 prior Samsung positives added one ad frame
but four program false positives; exact native-ROI reuse produced no useful
repeat hits once unused zero-filled regions were removed.

Known risks include wide station graphics that persist across a break boundary,
a wrong Samsung positive contaminating the short-lived cache, and changing ad
banners that fail to match. A pre-ad novelty gate and a reliable program-return
signal have not been implemented. Do not deploy this matcher as a standalone
classifier. Zero observed mistakes in a small, correlated sample is not proof
of safety across sports, news, cartoons, or channels.

## Run and test

Requirements: Python 3.10+, NumPy, Pillow, and OpenCV. The existing project
research environment can be used; no new model is downloaded.

```sh
python -m unittest discover -s experiments/ad-banner-memory -p 'test_*.py'
python experiments/ad-banner-memory/replay.py /private/data/manifest.json \
  --output /private/data/aggregate.json
```

A manifest is an array of metadata events in any order. Every event must include
`captured_at`, `expires_at` (Unix seconds), and `session` (opaque app/navigation
identity). Include events without images so navigation resets are not skipped.
For usable images provide `image` (relative to the manifest or absolute),
`clean: true`, optional reviewed `label` (`ad`, `program`, or `unknown`), and
`baseline_positive`. A teacher event may additionally set `trusted_ad: true`
and `teacher_accepted_at`; these fields must come from the existing strict native
validator, **not** an arbitrary positive-looking response or this matcher.

The generic replay emits only aggregate counts. Keep private images, identities,
fingerprints, labels, and coefficients outside Git. Do not extend their original
capture-session expiration; remove temporary analysis copies after the study.
The committed aggregate has no images, frame IDs, native fingerprints, or tokens.

## Research basis

Temporal matching is an established way to reuse evidence, but repeated material
is not automatically an advertisement. Google's
[acoustic and visual repetition work](https://research.google/pubs/advertisement-detection-and-replacement-using-acoustic-and-visual-repetition/)
and the
[per-channel overlay/transform disclosure](https://www.tdcommons.org/dpubs_series/371/)
support examining repeated content and channel graphics. This prototype is a
narrow continuity experiment, not a reproduction of either system or their
reported performance. Meta's
[PDQ reference documentation](https://github.com/facebook/ThreatExchange/tree/main/pdq)
also highlights filtering featureless imagery; this implementation does not use
PDQ or its thresholds.
