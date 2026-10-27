# Commercial Break — local visual lab

An observation-only Docker side project for testing inexpensive commercial detection against the TV's existing captures and native evidence. It has no mute, overlay, remote-control or Samsung-recognition client. The standalone TV app continues blocking independently, including when the computer is unavailable.

Agreed learning paths and implementation status: [roadmap](../../docs/LOCAL-LEARNING-ROADMAP.md), tracked in [issue #8](https://github.com/daoakley/commercial-break/issues/8).

## Data path

1. The existing TV debug switch saves a 480×270 PNG and JSON during its normal fingerprinting cycle. No second capture loop is installed.
2. `tv-debug-export.sh` transfers completed pairs to the Mac's authenticated `host_feed.py`. It also reports current foreground app, navigation generation, engine lifetime, debug deadline and Art Mode. It does not enable debug recording or alter recognition/capture settings.
3. The existing dashboard's **single** YouTube Lounge subscriber uses that fresh standalone source identity, independently of the stopped older detector. `http://127.0.0.1:8792/native-metadata` exposes sanitized playback/content/ad-event observations. Native forwarding to the old blocker is disabled in this deployment.
4. The host attaches native observations only when timestamps and app/navigation/engine bindings bracket the capture. Historical or unbound observations remain unknown. Samsung responses and original debug evidence are retained separately from human labels.
5. Docker stores the samples and computes local visual evidence. Its API/review page is `http://127.0.0.1:8795/`.

The adapter supplies verified content identity, playback position, inserted-ad events and their reported timing when available. **Show name, category, channel name and scheduled start remain unknown**: the verified feed does not currently provide those fields. Playback position is not a show-start time. Native ad-end/countdown is not proof that an entire broadcast break ended.

TV capture and host event timestamps use different clocks. Their correlation is useful for bounded context but is not a synchronized subsecond latency benchmark. Preserve original timestamps; measure clock offset/uncertainty before claiming which source won by milliseconds.

## Local detection and experiments

- Reused fixed-region Sponsored-pill matcher, enabled only for the known YouTube TV 480×270 profile. Repeated hits provide observation evidence; no generic sports-logo rule.
- Ordered short sequences of human-confirmed ad thumbnails. The prototype library requires clean, chronological frames and rejects static-scene sequences.
- A separate Samsung-positive learning experiment uses clean, session-bound Samsung AD frames as weak labels. It stages a local visual exemplar model, preserving Samsung provenance and leaving nonmatches unlabelled. This does not insert Samsung labels into the human-confirmed prototype library.
- `mobileclip_benchmark.py` tests pretrained MobileCLIP2-S0 locally without training or external image uploads. The first 340-frame run recovered 33/40 Samsung-positive frames with simple descriptions, but targeted review found apparent programming false positives. It remains an offline benchmark; see `mobileclip-validation.json` and `ML_EVALUATION.md`.
- Offline low-cost color/thumbnail classifier and causal replay, with whole-session/creative/program separation. Models are staged only; no training command activates a model or changes TV behavior.
- Art/card-contaminated, stale and session-mismatched samples cannot trigger live evidence. Historical clean images can still be reviewed offline.

These are candidate detectors, not a claim of production accuracy or faster blocking. The running TV blocker does not consume their results. See [ML_EVALUATION.md](ML_EVALUATION.md) for training, metrics and insufficient-data rules. Human-labelled complete program/ad intervals and independent sessions are required before claiming an improvement.

## Start and maintain

Run `sh start-lab.sh` from this directory. It creates private credentials if absent and starts the separate Compose project `commercial-vision-lab`, binding only loopback port8795. Docker dependencies are Pillow and NumPy; no model weights or inference service is downloaded/contacted during operation.

Private host settings are at:

`<repository>/work/commercial-vision-lab/private/`

`lab-token` unlocks the local review page/API. `feed-token` authenticates TV uploads. `lab.env`, `upload.curl` and `tv-export.tar` also contain private credentials. Never publish this directory. The Docker build context uses an explicit file allowlist and excludes it.

The Mac feed receiver listens on its selected LAN address, port8796, and accepts uploads only from the configured TV IP with the feed token. It forwards to loopback8795. The receiving endpoint is plain HTTP on the user's private LAN, matching the existing local capture transport; do not expose it to the internet. Credentials are read from files, not embedded in command-line arguments. Native YouTube subscription still uses its existing remote service; the Docker visual model itself uses no external inference.

Start the host receiver with `host_feed.py --bind MAC_IP --tv-host TV_IP --token-file PRIVATE/feed-token --lab-token-file PRIVATE/lab-token --source-state PRIVATE/tv-state.json --status-file PRIVATE/feed-status.json`.

Launch the existing dashboard with `--native-source-state PRIVATE/tv-state.json` and without `--native-forward`. Do not start another Lounge subscriber. Existing transport failure circuit breakers remain enabled.

`deploy_feed.py --tv-host TV_IP --mac-host MAC_IP --work PRIVATE --root-tool ROOT_EXECUTABLE --sdb SDB_EXECUTABLE` installs only the temporary bounded exporter on an already-rooted TV. The existing debug switch must already be on. It copies up to24 recent records, then follows newly committed records. It does not restart/enable the blocker. The exporter stops when debugging is switched off/expires, its stop file appears, or the Mac is unreachable for ten status attempts. A TV reboot removes it; it is not a persistence mechanism. Restart it explicitly after restoring connectivity if it stopped.

## Retention, stopping and recovery

The TV's existing 48-hour debug deadline is preserved. Docker sample expiry is the earliest of the debug deadline,48 hours after capture, or its rolling512MiB limit. Stopping debugging clears Docker data when the connected exporter reports the stop. During a connection outage, local expiry still clears records on schedule while Docker is running; if Docker is stopped, it clears expired records on next startup. Stopping the computer cannot change TV playback.

The authenticated `POST /v1/clear` (body `{}`) or `DELETE /v1/data` clears samples, labels, prototype sequences and managed derived artifacts. Keep all exports/model reports under `/data/artifacts` or `/data/experiments` so they follow cleanup. The original TV files remain governed by its existing debug switch.

For an immediate stop without changing the TV blocker: stop the host-feed PID recorded in the private directory, then run Compose `down` using the same project name and environment file. The TV exporter stops after its bounded connection failures. To erase the local dataset, call clear before stopping, or explicitly remove only this project's `lab-data` volume. Do not remove other Docker volumes.

## API

Except static review page and `/health`, all endpoints require `Authorization: Bearer <lab-token>`.

- `POST /v1/frames`: image_base64, timestamp, session_id, source, contamination and metadata.
- `GET /v1/status`: retained sample count, capacity and observation mode.
- `GET /v1/samples?limit=100`: records; `/v1/samples/ID/image` retrieves one image.
- `POST /v1/labels`: frame_ids, label (`ad`, `program`, `unknown`) and optional note. Use only for an actual human review.
- `POST /v1/prototypes`: name and ordered frame_ids from a human-confirmed commercial.
- `POST /v1/clear`: erase managed study data.

No endpoint controls playback. Test with `python3 -m unittest discover -p 'test_*.py'`; run the dashboard's tests separately in its directory. Unit tests verify bookkeeping, safeguards and synthetic visual cases, not real-world ad accuracy.

## First live validation — 26 October 2026

The live exporter populated the lab from the existing TV recording. Native playback metadata was verified connected and attached to current, bound frames. The first replay contained441 records,333 clean images and108 excluded/unknown-quality images. The local fixed-badge detector produced no positives; seven eligible clean frames had Samsung AD comparisons. These are coverage gaps to investigate, not an accuracy estimate. No human-labelled independent groups were present, so the training command returned `insufficient_data` and staged no model.

Removing redundant PNG encoding/unfiltering changed detector-compute p95 from36.95ms to0.247ms on exactly the same333 clean images in this Mac's Docker runtime. All141 applicable badge images produced exactly identical legacy/optimized scores (maximum absolute difference0). Timing excludes image I/O and decoding and is not end-to-end blocking latency or a TV runtime benchmark. The detection threshold stayed300.

Final verification:35 lab tests and47 dashboard tests passed. Aggregate results are in `validation.json`; image-bearing exports and detailed diagnostics remain only in the managed private Docker data volume. Offline diagnosis can be repeated with `python diagnose.py /data/artifacts/observations.jsonl --data-dir /data --output /data/artifacts/diagnostics.json --verify-badge-equivalence` after using `storage.py export`. No automatic model promotion is implemented.
