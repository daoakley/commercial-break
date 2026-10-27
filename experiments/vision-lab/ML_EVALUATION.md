# Offline training and causal evaluation

This experiment learns a **staged, observation-only** baseline. It does not modify the detector configuration, activate a model, control playback, contact an inference service, or write to the TV. It is intentionally a cheap starting point: 96 RGB values from an 8×4 image plus 24 channel-histogram bins, standardized using training data only, followed by a nearest-centroid score. There is no pretrained model download. Scores are similarity measurements, not calibrated probabilities.

## Samsung-positive learning

`teacher_train.py` is a separate positive-only learning path. It can learn from Samsung matches immediately without relabelling them as human truth. Clean, unexpired, same-session Samsung AD records teach a small visual exemplar model using centered 32×18 RGB fingerprints. Source-app binding and capture/fingerprint timing checks reject mismatched examples. Human Program labels veto positive training examples. Samsung unknowns remain unlabelled: they are never assumed to be programming.

This is local instance-based learning, intended first to recognize visually similar repeat ads. It is not a pretrained semantic vision model and cannot promise to generalize from one advertiser or shot to entirely different commercials. Fixed similarity thresholds are engineering choices, not probabilities. A threshold sweep describes sensitivity; held-out test results must not be used to select a winning threshold and then reported as independent validation.

The experiment stages a full-data candidate separately from its train-only evaluation model. Chronological evaluation holds out whole positive bursts and applies a time embargo to avoid training on immediately neighboring frames. This tests later footage; without creative labels it does not establish unseen-creative generalization. Reports distinguish recovery of Samsung-positive frames, activation on unlabelled frames, and false positives on human-labelled programming when available. Unlabelled activation is not a false-positive rate, and teacher agreement is not real-world accuracy.

Run the Samsung-positive experiment against a retained export using its CLI help for options. Keep all output under `/data/artifacts`; the original debug deadline and clear operation also cover the model's numerical fingerprints. It has no activation or TV-control path. The human-labelled classifier below remains separate.

```sh
python storage.py export --data-dir /data --output /data/artifacts/teacher-observations.jsonl
python teacher_train.py /data/artifacts/teacher-observations.jsonl --data-dir /data --output-dir /data/artifacts
```

Run these inside the lab Docker environment. Outputs are `teacher-experiment.json`, `teacher-heldout-train.staged.json` when a valid split exists, and `teacher-all-positive.staged.json` when eligible positives exist. Each run removes its prior teacher artifacts before staging replacements. The all-positive candidate is intended for future footage; scoring its own training frames would not establish useful performance.

### First Samsung-positive result — 26 October 2026

A frozen export contained 1,455 observations, with 1,128 usable images and 26 eligible Samsung-positive frames grouped into 12 temporal bursts. The chronological experiment trained on 19 positives, reserved four positives for validation and three for testing, with a 30-second embargo. At the fixed 0.985 threshold it recovered **0/4 validation positives and 0/3 test positives**. The stricter descriptive thresholds did not improve recovery. No unlabelled frames activated, but no human-labelled program examples were present, so false-positive accuracy is unmeasured.

This establishes a working positive-only learning/evaluation pipeline, not a useful detector yet. A separate candidate containing all 26 positive exemplars is staged for future comparisons. Failure of this tiny, strict visual exemplar baseline does not establish that Samsung-supervised learning cannot work; it does show that it should not replace the native detector. Further work needs repeat footage, diverse positives, and reviewed confusing programming before considering broader features or lower similarity thresholds.

Fingerprint compute p95 was 0.293ms and matching against 19 exemplars p95 was 0.700ms in Mac Docker, excluding image loading/decoding. These are component timings, not a measured TV runtime or end-to-end detection delay. All 43 lab tests passed. No TV behavior or running lab detector policy changed.

## Pretrained MobileCLIP zero-shot test — 26 October 2026

`mobileclip_benchmark.py` runs the original Apple MobileCLIP2-S0 checkpoint locally with **no study training**. Revision `3136ea51c8ed56b9f9abfab04cb816735aaad6cb`; checkpoint SHA256 `bc3bc861baa680df2f9e3dc1aa0acbe5a21af21032df385026dda70c33505aa6`. The isolated Mac Python environment uses the versions in `mobileclip-requirements.lock`; these dependencies are not installed into the running collector. The benchmark uses evaluation mode, reparameterization, RGB mean 0/std 1, and the supplied 256-pixel resize/center-crop preprocessing. Center cropping removes the left/right edges of the original widescreen frame, which can remove useful ad cues.

Two prompt sets were fixed before inference: a simple commercial/program pair and twelve specific descriptions (six per class). Each predicts the class of the highest-similarity description. Text vectors are computed once. Samsung verdicts and native ad flags are **not** passed to the model. A fixed 0.02 cosine-margin abstention rule was also reported as exploratory; margins are not calibrated probabilities.

The run tested all 40 eligible Samsung-positive frames and 300 uniformly spaced other clean frames available at the snapshot. No image was uploaded to an inference provider.

| Fixed prompt set | Samsung positives called ad | Other frames called ad | Samsung positives called ad with margin ≥0.02 |
|---|---:|---:|---:|
| Simple commercial/program | 33/40 | 173/300 | 17/40 |
| Specific visual descriptions | 28/40 | 82/300 | 22/40 |

These are **teacher-agreement measurements, not ad accuracy or precision**. Samsung nonmatches are unlabelled, related frames are correlated, and both prompt variants are exploratory. This is a different snapshot from the earlier 0/7 exemplar test, so it is not a controlled numerical comparison.

Assistant visual inspection of 31 targeted disagreements found visible ads among missed frames (including service/medicine advertising and movie-release banners), but also apparent Nat Geo Wild, Discovery and Smithsonian documentary/program scenes among commercial predictions. At least one Samsung-positive image itself looked like program footage, illustrating the limitations of using its verdict as screenshot truth. Reviews are explicitly `assistant_visual_review`, never human ground truth, and do not modify the lab's human-label database. These targeted observations do not estimate an overall false-positive rate.

Image-encoder plus score computation on the Mac CPU (two threads) measured median 85.4ms, p95 98.0ms after warm-up; fetching, decoding and preprocessing are excluded. This is not a Samsung TV performance measurement. The test establishes that pretrained recognition is useful to investigate, but the unmodified model is **not ready to control blocking**. Next experiments should preserve the whole frame and incorporate verified native context, while reserving new reviewed material for final evaluation.

Detailed predictions and review metadata live in `/data/artifacts/mobileclip-*.json` under the original debug expiry/clear policy. `mobileclip-validation.json` contains aggregate results only. No images are cached by the benchmark; temporary contact sheets were removed. The public pretrained weights are stored separately in `work/mobileclip-benchmark/` with their license, not in the public app or Docker collector.

Run from the workspace root, after preparing the isolated runtime and official checkpoint:

```sh
work/mobileclip-benchmark/venv/bin/python experiments/vision-lab/mobileclip_benchmark.py \
  --checkpoint work/mobileclip-benchmark/mobileclip2_s0.pt \
  --token-file work/commercial-vision-lab/private/lab-token \
  --revision 3136ea51c8ed56b9f9abfab04cb816735aaad6cb
```

## Human-labelled record format

Use the JSONL produced by `storage.py export`. Each record needs `session_id`, `timestamp_unix` (or a timezone-qualified ISO `timestamp`), `image_path` relative to `--data-dir`, `manual_label`, `label_source`, and `contamination.status`. Only **clean records manually labelled `ad` or `program`, with `label_source: human`, are training or evaluation truth**. Native TV results, Samsung matches, pseudo-labels, unknown labels, unlabelled samples, and contaminated samples cannot become truth. Cleanliness is a prerequisite, not proof that a manual label is correct. Label review remains important.

Optional `creative_id` and `program_id` can appear at top level or in `metadata`. Assign the same creative ID to near-identical edits. Sessions connected by any shared creative/program ID stay together in one partition. Without creative IDs, the report can establish session separation only; it cannot establish performance on unseen ads. Include confusing programming, early ad openings, and complete ad/program transitions.

For unit tests or a separately controlled feature pipeline, records can supply a numeric `features` vector instead of an image. Do not mix feature definitions just because their vector dimensions match. The built-in image feature version is `rgb-8x4-hist8-v1`.

## Run a staged experiment

From the lab directory, with the service running and clean human labels already collected:

```sh
docker compose exec vision-lab mkdir -p /data/artifacts
docker compose exec vision-lab python storage.py export --data-dir /data --output /data/artifacts/observations.jsonl
docker compose exec vision-lab python train.py /data/artifacts/observations.jsonl --data-dir /data --output /data/artifacts/prototype.staged.json
```

The model and sibling `prototype.staged.evaluation.json` contain the partition sessions, counts, and independent validation/test replay reports. Splitting uses whole connected groups, approximately 60/20/20, with a fixed seed. It requires at least three independent groups and both human-labelled classes in each partition. Otherwise it exits 2 with `insufficient_data` and creates no new artifact. This floor makes a runnable experiment possible; it does not establish adequate sample size. Metadata linking every session through one program can correctly make a split impossible. Collect more independent material rather than splitting adjacent frames.

All preprocessing parameters and centroids are fit on the training partition. Validation and test data do not fit the model. Default confidence/confirmation settings are fixed engineering choices. If you use validation results to tune them, preserve the test partition and do not repeatedly select configurations by test performance. A separate `evaluate.py --model ...` invocation rejects any session, creative, or program overlapping the model's training groups; pass genuinely separate records rather than the full training export.

To evaluate recorded detector decisions against human labels without training:

```sh
docker compose exec vision-lab python evaluate.py /data/artifacts/observations.jsonl --output /data/artifacts/recorded.evaluation.json
```

This replays the exported `decision` field (or explicit `prediction`) through the same confirmation rule. For a raw recorded-decision audit, use `--confirmation-frames 1`; the default applies two-sample confirmation. Recorded ad/unknown detectors have no explicit program class, so their unknown fraction includes normal programming. With `--model`, image features and model scores replace recorded decisions. Image training requires Pillow, included in the service dependencies; feature-based tests use Python's standard library only.

## Interpret time metrics conservatively

Replay sorts timestamps within each session, processes only past/current observations, and resets confirmation on a new session, untrusted label interval, or gap over five seconds. Duplicate timestamps are rejected. Unknown decisions mean no hypothetical block. Label intervals use sample-and-hold until the next observation; the final sample and gaps above the maximum add no duration. Thus latency is relative to **sampled manual-label transitions**, not exact video onset. Sparse frame capture cannot establish sub-frame boundary timing.

Reports include false-blocked programming seconds per viewing hour, false-trigger events per programming hour, exposed ad seconds, unknown time, complete-break misses, median/p95 onset latency, and restoration delay. Leading/trailing/gapped ad segments are censored. Latency summarizes detected complete breaks only; always read missed/censored counts alongside it. Restoration treats unknown as releasing a hypothetical block and reports censored restorations separately. No playback actions are performed.

By default, fewer than one human-labelled viewing hour or five complete ad breaks yields `insufficient_data` and CLI exit 2, while retaining diagnostic metrics. These are engineering minimums, not production acceptance thresholds. Even above them the status is `diagnostic_only`, never a reliability certification. Fix an acceptable false-block budget and onset target before judging a real test. The synthetic tests prove bookkeeping and isolation, not commercial-recognition accuracy.

## Retention and verification

Keep exports, staged models, and reports under `/data/artifacts` so the service retention and clear operations cover them. They inherit the earliest available source `expires_unix`; do not copy them elsewhere to extend the capture session's lifetime. The model stores numerical summaries and group IDs, not raw images. Deleted source images make old image-based exports unusable. Local invocation outside the managed data directory does not automatically provide the service's retention lifecycle.

```sh
python3 -m unittest -v test_evaluate.py
```

Tests cover causal confirmation, session/gap resets, missed and censored breaks, time denominators, false triggers, rejection of native/pseudo/contaminated truth, connected creative holdouts, overlap rejection, insufficient-data behavior, and staged artifact output.
