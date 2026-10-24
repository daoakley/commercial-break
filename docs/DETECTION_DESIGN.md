# Context and fast detection — 24 October 2026

The aim is earlier commercial blocking with fewer false covers, especially
after channel changes and during programs with banners. A 10× improvement
in accuracy or every ad's onset latency has **not** been demonstrated.

## Problems found and corrected

1. The Claude bridge silently cut instructions at 1,600 characters and context
   at 3,000. Later show-change and cover-card rules were not reliably delivered.
   Complete instructions and valid JSON now pass through within explicit
   12,000-character budgets; oversized requests fail open instead of truncating.
2. A channel change within YouTube TV kept the same app ID. Old show and break
   history could therefore contaminate the new channel. A passive remote-input
   observer now provides a navigation generation. The TV clears owned controls
   on navigation, rejects responses to pre-navigation frames, and gives the
   detector a new context epoch. It does not consume or inject button presses.
3. An HGTV corner “Tonight 10/9c” tune-in graphic caused the ongoing renovation
   show to be classified as a commercial. Main video and overlaid promotion
   now have separate presentation labels. A confident in-program promotion or
   split screen releases a cover. The actual failing screenshot, tested with
   deliberately stale movie/ad context, returned program 0.85 and
   `in_program_promotion` after the correction.
4. Seven saved captures showed our own cover card; six had been labeled ad.
   A local mask recognizes the project's text/rule geometry and dark surround,
   before model interpretation. A cover cannot refresh evidence for an ad.
   The capture helper also waits for actual capture completion before returning
   the card, rather than assuming a 225 ms latch time.

## Two paths, one fail-open controller

`/v2/frame` accepts each new frame promptly. The existing YouTube TV Sponsored
template can request a mute locally; all other images update a single pending
frame for background vision. New arrivals replace the pending frame rather
than building a backlog. Capture and local checks continue while Claude runs.

The background worker uses the same conservative detector policy. An older
context's result cannot control the current view. Results older than eight
seconds are discarded. An uncertain verdict does not renew the ad lease;
evidence expires after twenty seconds. Errors release the mute. An ordinary
scene cut requests another interpretation but does not assert a channel
change: both shows and commercials cut rapidly.

Program captures target one-second cycles, including processing time.
Covered captures normally target four seconds, with quicker checks when
program return is being confirmed. Vision requests are separately scheduled,
normally five seconds after a program result or eight after an ad result;
visual/audio change candidates can request earlier interpretation. This is
not one Claude call per second.

The TV keeps its capture process alive and keeps the card window hidden in
memory between breaks. Card activation no longer has to start .NET/EFL first.
The existing speaker/backlight ownership rules, manual override, expiring
overlay lease, physical-panel rescue, and independent watchdog remain.

## Context, provenance and prediction

Each viewing context has a separate epoch and records:

- Supplied app/channel/title, where available; unknown stays unknown.
- A visually inferred show name, explicitly marked as inference.
- Category supported by repeated program observations, with expectations for
  sports, news, films, series, documentaries, children’s shows and music.
- First time the program was observed, separately from its actual broadcast
  start. The latter is unknown without a verified source.
- Recent observations, last ad observation, detected break starts/ends, and
  robust ranges for the next break and current break end when history supports
  them. A failure-induced release is not a confirmed broadcast boundary.

Timing predictions require at least three usable intervals/durations and low
dispersion. They are hints, never permission to mute or keep a show covered.
An individual ad sequence is not inferred from a generic 15/30/60-second rule.
Reliable sequence predictions need identified ads and confirmed boundaries.

On the tested YouTube TV app, actual in-app channel/title metadata is still
unavailable. The passive navigation signal detects interaction, not the name
of the newly selected channel. Automatic program changes still need visual
interpretation. Context is currently held in memory and resets on a source or
navigation change; persistent per-channel learning is not implemented.

## Deterministic signals

| Signal | Current role | Limitation |
| --- | --- | --- |
| YouTube TV Sponsored pill | Can initiate mute locally | Exact tested app/resolution/UI; absent from many ads |
| Remote navigation | Clears cover and invalidates old decisions | Recognized evdev devices/key codes; physical remote test needed on each TV |
| Own-card geometry | Rejects contaminated captures | Specific to the shipped card |
| Scene, center/border and brightness differences | Requests fresher interpretation | Cannot distinguish program edits from ads alone |
| Audio RMS, crest factor, short silence, zero crossings | Observation/urgency only via optional `/v2/audio` | Requires a separately configured internal PCM uploader; not enabled in the current trial |
| Repeated-ad acoustic fingerprints | Offline validation only | Recognizes learned recordings, not arbitrary new ads |

The audio endpoint accepts at most three seconds of 48 kHz stereo S16 PCM,
requires the current app/channel/title/session, rejects mismatched contexts,
and resets its change baseline on gaps. Raw PCM is discarded after extracting
numeric features. Neither loudness nor silence can order a mute.

## Measured evidence

- On-TV one-shot captures: 710, 640, 640 ms. Persistent captures: 410 ms first
  capture, then 170, 230, 180, 200 ms. Median improved about 3.2× in this small
  isolated test; live video complexity can increase capture time.
- Local v2 ingestion of four saved badge frames, three repeats each: median
  128 ms, maximum 145 ms. This excludes sampling, upload and visible display
  latency; all twelve requested mute without invoking vision.
- Live program capture timestamps changed from roughly 10–11-second gaps to
  roughly one-second gaps. This improves sampling opportunity about 10×;
  actual first-ad-frame-to-card latency still needs held-out measurement.
- The own-card filter matched all seven inspected card captures in 1,853
  selected images and no program-labeled image. One matching image supplied
  the mask. This is a regression check, not an unbiased accuracy benchmark.
- Large visual cuts occurred in 291/626 program-labeled frames and 512/1,103
  non-card ad-labeled frames: both approximately 46%. Brightness changes also
  occurred in both classes. These selected, irregular samples cannot measure
  a continuous-time false-alarm rate.
- A two-second acoustic template matched an independently captured repeat of
  one known ad at 0.9993; 54 selected program-labeled recordings scored at most
  0.6555. A one-second match for a different template fell inside an ambiguous
  program-to-ad interval, illustrating why nearest screenshot labels are not
  reliable ground truth at boundaries. Audio remains observation-only.

No saved broadcast images, recordings, private network settings, tokens or
Samsung libraries are included in this repository.

## Enable, verify and roll back

The sequential v1 endpoint remains the default. Build/stage the navigation
helper as well as the capture and overlay helpers. Stage `tv-capture.sh` with
the other shell helpers. Then, for a monitored fast-path test:

```text
# Computer .env
ENABLE_REALTIME=1

# TV private env; retain your own URL host and existing token
FRAME_URL=http://YOUR_COMPUTER_LAN_IP:28471/v2/frame
FAST_MODE=1
CAPTURE_PERSISTENT=1
OVERLAY_WARM=1
NAVIGATION_OBSERVER=1
```

Restart the Docker service and TV helper using the normal documented
stop/start procedure. Keep `PANEL_MASK_ON_CAPTURE` at the value validated for
your TV. Inspect content-free `capture_ms`, `request_ms`, `actuation_ms` and
Docker `ingest_ms`, `model_ms`, `epoch` logs. Authenticated `/v2/status` reports
queue depth, recent-frame age and discarded-result count. It is not proof of
what is visible on the physical panel.

For rollback, stop the TV helper, set its URL back to `/v1/frame` and
`FAST_MODE=0`, and restart. Persistent capture, warm overlay and navigation
observation are independently optional; set their flags to `0` if needed.
Retain the corrected bridge and presentation policy when reverting timing.

Acceptance checks: physical remote channel change during a cover; automatic
show transition; sports/news with banners; a full ad break and program return;
and computer/model unavailability. Measure false program covers per hour and
first-ad-frame-to-card delay separately. A model confidence score is not a
calibrated false-positive rate.

## Research informing the next steps

[Covell, Baluja and Fink](https://www.mangolassi.org/covell/pubs/mmsp06_ads.pdf)
use acoustic repetition and visual verification for known ads.
[Ramires et al.](https://arxiv.org/abs/1811.02411) use short low-energy intervals,
local context and boundary grouping. Both support combining signals; neither
establishes this TV’s real-time precision or latency.
[Comskip](https://github.com/erikkaashoek/Comskip) is a useful reference for
channel-dependent combinations of logos, silence and image transitions.

[Watching the Watchers](https://watchingthewatchers.github.io/watchingthewatchers/index.html)
shows why an ACR upload system is not automatically an accessible local ad
verdict. A local library of validated fingerprints can supply useful repeated
content recognition without enabling Samsung’s tracking for this purpose.
