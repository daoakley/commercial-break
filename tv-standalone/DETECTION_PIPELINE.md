# Detection scheduling and diagnostics

The engine owns one native capture at a time. Local picture checks and Samsung
network recognition have separate schedules and failure handling. Regular
YouTube uses local controls only; YouTube TV can use local Sponsored/layout
evidence and Samsung recognition.

## Local and remote work

Uncovered captures keep the existing targets: 500 ms between starts for regular
YouTube, 1,000 ms for YouTube TV. Capture, optional debug encoding and control work
can overrun those targets. They are not guarantees of ad-onset latency.

After a local miss, an eligible Samsung fingerprint is copied into an immutable
request. There is at most one remote operation, with no request backlog. While it
waits, uncovered local captures continue without generating more fingerprints.
The main loop applies completed replies between captures; it does not interrupt
a native capture to change the overlay. An accepted local positive can cover
without waiting for the pending Samsung response.

Samsung failures delay only further Samsung submissions: 4, 8, 16, 32, then at
most 60 seconds. A successful reply resets that backoff. An unknown verdict is
not an error. Cloud errors neither renew a cover nor invalidate independent,
recent local ad evidence. The existing short cover lease still expires without
fresh positive evidence. Native capture/control failures release playback and
retry; five consecutive local failures recycle the engine under its supervisor.

Each operation carries foreground app, navigation generation, engine generation
and a monotonic start time. Off, maintenance, navigation and app changes cancel
pending work. The slot remains occupied until the cancelled operation actually
stops. A result from a different session or older than five seconds cannot cover
or renew a cover. The foreground app is rechecked before accepting a positive.
App/navigation identity does not establish a channel or program title.

## Covered checks

YouTube TV first tries a secure fingerprint with the card visible. A current
unknown reply schedules the masked fallback. A pending covered request does not
cause repeated card drops. During Samsung backoff the local masked checks remain
available. Regular YouTube keeps its local countdown/Skip path and bounded timer
hold. Samsung no-match never means that programming has definitely resumed.

Masked capture requires verified physical-panel blanking before hiding the card.
If blanking fails, the helper aborts without intentionally dropping the card.
If the card-return acknowledgement fails, the helper leaves its independent
four-second panel rescue alive instead of immediately exposing the picture.
No failed sample renews a cover. These controls depend on the target firmware;
physical blackout and cleanup require hardware validation.

## Samsung evidence validation

Every frame contributing a direct candidate ID must have the exact submitted
timestamp and a match distance from 0 through 15. A current sibling cannot make
an undated or stale frame current. Malformed candidates are ignored individually
so that they cannot authorize a cover or hide a separate valid candidate.
The aggregate commercial-confidence fallback retains its timestamp, source and
non-retained-confidence requirements. Parsing is tested with synthetic replies;
unrecognized content remains unknown.

## Scalar timing

Authenticated `/status` exposes:

- `build`: assembly version and SHA-256 of the running engine assembly.
- `samsungLane`: in-flight state, consecutive failures and retry delay.
- `samsungError`: the last current cloud exception type; no exception message.
- `timing`: latest scalar stage record, pending count and dropped records.

`diagnostics/timing.jsonl` records a capture sequence, stage, wall-clock timestamp
and monotonic elapsed milliseconds. Stages include capture start/completion,
local positive, remote submission/processing, accepted evidence, mute completion,
cover request, window shown, release and discarded evidence. Remote processing
time includes any wait for the next safe main-loop boundary; it is not just
network round-trip time. `WindowShown` acknowledges the renderer's show call,
not the exact instant pixels reach the physical panel.

Capture/control paths enqueue records in memory. Maintenance flushes them once
per second. The queue holds at most 256 entries; excess records are dropped.
The file rotates at approximately 64 KiB with two older files, plus at most one
bounded flush batch per file. Logging failure cannot stop detection. The scalar
log contains no images, raw replies, viewing titles, device identity, tokens or
arbitrary diagnostic text. It is separate from opt-in 48-hour debug recordings.
Raw operational logs should still be kept private.

Debug records retain the matching request/response even when later captures
occur while that request is pending. Debug expiry, stop-and-clear and the storage
limit still apply. `recognitionInProgress` covers local capture/processing;
`samsungLane.inFlight` separately reports the remote operation. Maintenance
cancels remote work and must drain native capture before replacing binaries.

## Build and validation

Deploy the engine, capture helper and overlay renderer from the same revision.
Use the maintenance procedure in [the YouTube guide](YOUTUBE_AD_CONTROLS.md).
The packaging tool builds the coordinated components; do not update only the
engine DLL when upgrading the capture protocol.

```sh
dotnet build tv-standalone/engine/CommercialBlock.csproj -c Release -p:UseAppHost=false
dotnet build tv-standalone/engine/capture/AcrFrameProbe.csproj -c Release -p:UseAppHost=false
dotnet build tv-standalone/engine/overlay/CommercialOverlayProbe.csproj -c Release -p:UseAppHost=false
dotnet run --project tv-standalone/tests/pipeline/PipelineTests.csproj
python3 tv-standalone/tests/test_verdicts.py dotnet
```

Offline tests exercise slow/failed operations, bounded retry, cancellation,
stale results, app/navigation changes, malformed evidence, diagnostic bounds and
renderer receipt correlation. They do not establish a TV latency or accuracy
improvement. Hardware validation should measure actual ad onset to visible cover,
program return, false covers, memory/CPU, masking, Off/navigation during requests,
and both supported apps with debugging on and off.
