# TV-local Sponsored-pill fast path

The standalone engine now checks YouTube TV's fixed upper-left **Sponsored** indicator before generating a secure fingerprint or connecting to Samsung. This is a narrow template matcher, not an AI model or general text detector. It runs on the TV and requires no computer or additional network service.

## Decision sequence

1. The existing guards require YouTube TV in the foreground, no competing blocker, and an unchanged navigation session.
2. Capture the picture using the existing native capture helper and existing panel/overlay handshake.
3. Read a 66 × 14 reference-pixel region directly from the captured NV12 buffers. Match the high-frequency lettering template using the same conversion and score as the existing Python implementation. No full RGB allocation, PNG encoding, OCR, or model runtime is needed for this check.
4. A fresh score of at least 300 triggers the existing cover/mute path after the engine rechecks the foreground app and navigation generation. A positive skips Samsung fingerprint generation and the recognition request for that capture.
5. Otherwise use the existing Samsung recognition path. Captures made with the cover card still visible skip the local matcher; the established masked fallback can inspect the underlying picture.
6. Existing eight-second lease expiry, navigation release, Art Mode guard, independent watchdog, and owned-mute restoration remain in place.

The engine still targets an initial check every second, subject to capture/process/network time. The timing below measures the matcher alone, **not** ad-onset-to-card latency. The existing Samsung error backoff can still delay later captures. Eliminating that dependency is a separate change requiring measurement.

## Evidence from the development TV, 2026-10-27

| Check | Result |
|---|---|
| Real retained clean captures scanned with the reference matcher | 1,647 |
| Template hits | 15, scores 481.8–688.7 |
| Highest remaining score | 58.1 |
| Visual spot check | Sponsored pills on sampled hits; ordinary program frames and rating/network graphics on sampled negatives |
| TV CPU, native NV12 ROI check, 2,000 warmed repetitions | 0.152 ms/check; zero heap bytes allocated in scoring |
| Live fresh-helper checks (includes scoring JIT) | Approximately 7–10 ms/check at initial verification |
| TV CPU, retained positive RGB fixture | 0.057 ms/check; score 512.25 |
| TV CPU, retained program RGB fixture | 0.063 ms/check; score 0.114 |
| Regression checks | 12 Samsung verdict cases; 11 local-evidence cases; RGB/NV12 parity, geometry, shifts, clipping and allocation tests |

This sample is not a representative accuracy study. It does not establish 99% recall, a false-positive rate across sports/news, or coverage of different pill positions/styles. Ads without this indicator still depend on Samsung recognition. Temporary validation images are private and excluded from Git.

## Diagnostics and retention

Authenticated engine status adds `localChecks`, `localHits`, `lastPillScore`, `lastPillMillis`, and `lastMatchSource`. `localHits` counts positive checks, not distinct ad breaks or successful covers. Debug sidecars include `localDetection`; local positives use Samsung verdict `not_queried_local_positive`. They must not be counted as Samsung recognition successes. The existing debug deadline and deletion policy are unchanged; the matcher works when debug recording is off.

The per-capture result in `/run/commercial-block/sponsored-pill.json` is replaced atomically and deleted before every new helper invocation. The engine rejects stale/future results, covered captures, altered thresholds, and unknown detector versions. Capture buffer bounds are checked before the matcher reads pixels. Optional matcher failures fall back to Samsung.

## Build and tests

Target the TV's existing .NET Core 3.1 runtime. Build the engine and capture projects, then run:

```sh
dotnet build tv-standalone/engine/CommercialBlock.csproj -c Release
dotnet build tv-standalone/engine/capture/AcrFrameProbe.csproj -c Release
python3 tv-standalone/tests/test_verdicts.py dotnet
python3 tv-standalone/tests/test_pill_evidence.py dotnet
# Python environment with Pillow and NumPy; PILL_DOTNET may name a dotnet binary.
python3 tv-standalone/tests/test_sponsored_pill.py
```

The optional `PILL_PRIVATE_FIXTURES` directory supplies currently retained 480×270 PNGs for parity tests. Do not commit viewing images, tokens, device identities, debug records, or private configuration. A bounded on-TV harness supports RGB files or NV12 fixtures and measures score-only time after JIT warmup.

## Next candidate, not enabled

Unexpected large text/product graphics during otherwise naturalistic programming may support a future detector. It needs program context and validation against opening titles, subtitles, sports graphics, and news. Text size alone is not sufficient evidence to block.
