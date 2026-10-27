# Experimental TV-local advertising layout detector

This is an explicitly enabled pilot, not a validated general commercial detector.
The owner authorized live testing on October 27, 2026, accepting that normal
programming may be interrupted and requesting a separate way to turn it off.
Samsung recognition and the Sponsored-pill detector remain active.

## What is deployed

A small RBF SVM with 141 spatial color, edge and texture measurements. It uses
stock OpenCV 4.5 on the tested Frame through its legacy C API. No LLM, external
inference service, new native runtime, or MobileCLIP model is required. Existing
Samsung requests continue normally when local detectors do not identify an ad.

The fixed pilot is `forward-49-20261027`, threshold **0.5 SVM margin** (not a
probability), 44 support vectors, and a 147,944-byte private model file. This is
the earlier-block training model from `experiments/ad-layout`, not a refit using
the held-out block. The Sponsored region is masked out of its features.

The small forward test added one ad frame to ten already detected by the
same-frame Samsung/Sponsored baseline: 10 to 11, a 10% relative gain in that
sample. It produced no false positives in 111 held-out program frames. The
cutoff was selected after examining results; this is not an independent final
validation. There were no cartoons in the test, labels were assistant review,
and sparse frames cannot establish live recall, interruption rate, or onset
latency. Do not represent this as a demonstrated 10% viewing improvement.

## Runtime sequence

1. Existing capture and Sponsored check run as before. Covered-card screenshots
   are excluded from local visual classification.
2. After the panel/card is restored, an uncovered, non-Sponsored frame is
   converted to 480×270 RGB and handed to a persistent isolated worker. The
   optional debug PNG reuses that conversion.
3. The worker uses the TV's OpenCV functions at 160×96 and evaluates the fixed
   model. Its positive result can cover the picture before a Samsung query.
4. The engine waits at most 200 ms beyond the capture helper's completion for
   the worker; a miss/unavailable result falls through to Samsung. It accepts
   only this capture's fresh result, expected model ID, fixed margin, and an
   unchanged app/navigation/control generation.
5. Existing eight-second cover renewal, navigation release, and watchdog rules
   remain. Turning this experiment off releases a cover whose most recent
   accepted match came from this experiment.

The worker loads once. In an isolated 28-frame TV test, total handoff/response
latency had an 83 ms median and 238 ms maximum; worker RSS peaked at 29.3 MiB.
One-time startup/warmup was about 1.5 seconds, during which normal recognition
continues. Real-frame decisions agreed with the Python reference on seven
fixtures (five real, two synthetic), with maximum margin difference under
0.00046. Small gradient orientation differences exist between implementations.
These are microbenchmarks, not a guarantee under every live TV load.

The worker cannot control playback. Three missing replies or repeated startup
failures disable the experiment. Capture/native or network failures retain the
existing fail-open behavior. This feature does not fix unrelated Samsung errors.

## Switch and diagnostics

On the TV, using the existing private local control configuration:

```sh
curl --fail --silent --config /opt/usr/home/owner/commercial-block/control.curl \
  -H 'Content-Type: application/json' --data '{"enabled":false}' \
  http://127.0.0.1:18764/layout
```

Use `true` to enable. This switch affects only the experiment, not the main
app's On/Off control, Samsung detector, Sponsored detector, or debug mode. Its
setting is persisted in `layout-enabled`. It is initially off on deployment.
The existing TV app UI has no separate layout toggle in this pilot; use the
local authenticated endpoint or ask the operator to turn it off.

`/status` includes `layout.enabled`, `checks`, `hits`, `lastScore`, `lastMillis`,
`lastModel`, `error`, and `threshold`. `lastMatchSource=experimental-layout`
identifies an accepted layout match. Existing debug records include
`experimentalLayout` with frame timestamp, score, margin, model ID, processing
time and verdict. This preserves the debug session's original 48-hour deadline.

Transient RGB handoff files live in `/run/commercial-block`, are consumed and
removed per request, and are cleared on shutdown/off. They do not create a
second screenshot archive. Existing debug images follow existing retention and
storage bounds. Learned coefficients stay on the private device/deployment
workspace; no viewing screenshots, tokens or private model are in Git.

## Build and model reproduction

Build the existing engine and capture projects with .NET Core 3.1 targeting.
`LayoutDetector.cs` uses only libraries already present on the tested TV.
Install both updated DLLs together; preserve appearance settings, device config,
control configuration, and debug metadata. Back up the original DLLs first.
Restart only the blocker engine and its helpers, then restore its prior On state.
Do not reboot the TV or disable debug just to update this detector.

`experiments/ad-layout/export_model.py` exports a reviewed sklearn pipeline into
the bounded JSON format. For the deployed pilot, use only the 49 earlier reviewed
training frames, with the scaler and `SVC(C=1, gamma='scale', class_weight='balanced',
kernel='rbf')`. Private training images/labels are not distributed. Retraining
requires a new model identity, explicit adjustment of the engine's accepted ID,
new held-out validation, and TV parity checks; do not silently overwrite the
pilot with a model trained on its test block.

Tests: `tests/test_layout_evidence.py` checks freshness, disabled state, model
identity, covered frames, margin and timing. `tests/test_layout_model.py` also
checks sklearn score parity, malformed models, and NV12 conversion. Existing
Samsung/Sponsored tests remain required. Experimental status is intentional:
collect user-reported false blocks and retained debug evidence before raising sensitivity.
