# YouTube ad controls

Regular YouTube uses local picture analysis on the TV. It does not generate
Samsung fingerprints or submit Samsung recognition requests. YouTube TV keeps
its separate Samsung/Sponsored detection path.

## Recognized controls

The `youtube-ad-controls-v2` detector accepts the tested bottom-right layouts:

- A yellow circle countdown with distinct numerals and arc geometry.
- “Skip in” text with yellow countdown pixels.
- The highlighted Skip button, including its text and arrow. The search also
  covers the shifted button beside a Send-to-phone end card.

A Sponsored label is diagnostic only. Phone text, an empty circle or a yellow
patch alone cannot authorize a cover or a key press. Small fixed UI templates
are included in source; private screenshots and viewing records are not.

The matcher reads small regions directly from NV12 capture planes. It uses no
OCR, LLM or full-frame PNG decoding. Native capture still acquires the full
picture; hardware region capture has not been established. The engine validates
app identity, detector version, capture time, processing time and control geometry
before accepting evidence. YouTube TV's pill, layout and acting audio rules do
not classify regular YouTube.

## Timing and a steady card

Uncovered checks target 500 ms between starts, with one capture in flight and no
queue. Capture, helper startup and optional debug encoding can extend that
interval. This is not a guaranteed ad-onset latency. Capture failures release
the cover and retry while existing recovery guards remain active.

After two fresh, decreasing circle-timer readings predict the same ending within
two seconds, the engine keeps the card up and waits until 1.5 seconds before the
earlier predicted end. A hold lasts no more than 30 seconds. Ambiguous digits
remain an interval; unreadable controls use the ordinary capture cadence.

The live loop still observes navigation, app changes, Art Mode, Off and maintenance.
Every release cancels the hold. Only that live loop renews the eight-second
watchdog lease; a stopped process cannot extend it. A bounded four-second grace
allows the next capture. Timer expiry alone never declares program return:
the next state may be Skip or another ad. Covered checks use the panel-mask
capture handshake, whose behavior remains firmware-dependent.

## Optional automatic Skip

Automatic Skip defaults off. The authenticated TV-local `POST /youtube-skip`
endpoint accepts `{"enabled":true}` or `false`. `/status` exposes the setting
and attempt state under `youtubeUi`. The main On/Off control disables all actions.

A key press requires a highlighted Skip match less than 1.5 seconds old, the
same regular-YouTube app/navigation session, and no navigation in the preceding
three seconds. An attempt is persisted before sending Return down/up through
`org.enlightenment.wm.Test.EventKey`. Key-up is attempted even on failure.

There is at most one attempt per observed break, at least 60 seconds between
attempts across restarts, and eight seconds of fresh control-free frames before
rearming. Send-to-phone text alone never causes selection. Manual remote Skip
remains available. `ad-controls-cleared` reports disappearing controls, not a
verified video title.

## Debugging and updates

Optional debug records include `youtubeControls`, timer readings, app/session
state and the existing capture/control context. Local positives are recorded as
`not_queried_local_positive`, not Samsung matches. Debugging does not enable Skip.
The original 48-hour deadline, 128 MiB rolling limit and deletion on stopping or
expiry still apply.

Build and deploy the engine and capture helper from the same revision. Before
replacing a running engine, send authenticated `POST /maintenance` with
`{"paused":true}` and wait for `recognitionInProgress:false`. This drains capture
and releases owned controls while preserving debug state. Resume with
`{"paused":false}`; engine restart also clears maintenance. Do not interrupt an
active native capture: it can leave the capture scaler unavailable.

## Validation and limits

Regression checks cover app routing, evidence freshness, control geometry,
countdown scheduling, navigation/reset behavior and Skip throttling. Local RGB
and NV12 replay were compared on the tested layout. These tests do not establish
accuracy across all YouTube UI versions, languages, resolutions or accessibility
settings. A changed layout can be missed; no universal detection claim is made.

```sh
dotnet build tv-standalone/engine/CommercialBlock.csproj -c Release
dotnet build tv-standalone/engine/capture/AcrFrameProbe.csproj -c Release
dotnet run --project tv-standalone/tests/youtube-ui/YouTubeUiTests.csproj -- --self-test
dotnet run --project tv-standalone/tests/youtube-skip/SkipGuardTests.csproj
dotnet run --project tv-standalone/tests/youtube-hold/HoldTests.csproj
python3 tv-standalone/tests/test_apps.py /path/to/dotnet
python3 tv-standalone/tests/test_youtube_evidence.py /path/to/dotnet
```

The UI harness also accepts `--stream` for consecutive 480×270 RGB888 frames,
or `--nv12 FILE WIDTH HEIGHT PITCH`. Keep any real footage private and subject
to its original debug-retention deadline.
