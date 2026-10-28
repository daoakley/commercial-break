# Commercial Break

Commercial Break runs on a Samsung Frame TV and covers commercials with a themed
screen while muting their audio. The show continues playing underneath. The
current version uses Samsung recognition and local image checks on the TV; it
does not need Docker, a computer, or an LLM running during viewing.

The installed TV app provides On/Off controls, a break-screen theme picker, and
an optional 48-hour debug session. The privileged background engine does the
capture, detection, muting, and overlay work. Closing the controller app leaves
the enabled engine running.

**Experimental, tested on one TV:** 2022 Samsung Frame QN65LS03BAFXZA,
firmware T-PTMAKUC-1720.7, Tizen 6.5, .NET Core 3.1. This is source for a manually
provisioned installation, not a Samsung Store app or a universal installer.
The optional signed recovery widget starts after a full reboot, reacquires
root through TV-local SDB and starts the existing engine. A power-cycle test on
the listed model confirmed automatic startup and resumed recognition; allow
roughly 90 seconds for startup. Other hardware/firmware remain unverified.

## How it works

[samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) provides the
temporary privileged access needed to run the TV helpers. Samsung's developer
bridge, `sdb`, stages the files. TizenBrew is not required.

The capture helper uses Samsung's `secvideo_api_capture_screen` path and the
TV's native secure fingerprinting functions. A process-local copy of a capture
library supplies the access needed on the tested firmware; proprietary Samsung
libraries are obtained from the owner's TV and are not distributed here.

```text
YouTube TV picture
  ├─ Local Sponsored-pill match ───────────────────┐
  ├─ Optional local advertising-layout classifier ┤
  └─ Native fingerprint → Samsung recognition ────┤
                                                  ▼
                                  Mute + themed Commercial Break card
                                  Playback continues underneath
```

- **Sponsored pill:** checks the tested YouTube TV upper-left indicator directly
  in capture buffers. A positive match can act before a Samsung request.
- **Samsung recognition:** submits native fingerprints to Samsung's configured
  recognition service. A validated ad match starts or renews the cover.
- **Experimental layout detector:** an optional small local classifier evaluates
  image composition using the TV's existing OpenCV library. It has a separate
  off switch and limited validation; it is not enabled merely by building this
  repository. Its private trained model is not included.
- **Release and recovery:** matches must be fresh and belong to the current
  app/navigation state. Covers require renewal; watchdogs release owned controls
  after failure. The main loop currently targets YouTube TV, not every TV app.

Running on the TV does **not** mean entirely offline: the Samsung path sends
fingerprints and device metadata to Samsung. The local checks need no remote
AI service. This app does not disable Samsung tracking.

## TV controls and break screens

Open **Commercial Break → Break screen** to preview and choose a theme. There
are 23 choices: Original; seasonal, holiday and zen scenes; and day/night
skyline scenes for Raleigh, Memphis, Washington DC and Charlotte. The Raleigh design includes landmark silhouettes and wooded foreground.

Custom artwork uses a minimal clock in the upper-right. It is rendered locally
with geometric primitives, with no artwork download or animation service.
Selecting a theme changes the next break; it does not replace an active card.
The original scene remains available.

You can inspect the actual theme picker safely on a computer:

```sh
python3 -m http.server 8797 --bind 127.0.0.1 --directory tv-standalone/app
```

Open [the local preview](http://127.0.0.1:8797/preview.html). This preview does
not load TV credentials or contact the TV; Save is simulated.

## Source and reproduction

Start with the [installation guide](tv-standalone/INSTALL.md) for private inputs,
building/signing, deployment, reboot recovery, validation and removal. The
[app guide](tv-standalone/README.md) covers controls, themes and maintenance.

| Component | Source |
| --- | --- |
| TV controller and theme preview | [`tv-standalone/app`](tv-standalone/app) |
| Detection, controls and debug lifecycle | [`tv-standalone/engine`](tv-standalone/engine) |
| Capture, Sponsored check and local classifier | [`engine/capture`](tv-standalone/engine/capture) |
| Native card renderer | [`engine/overlay`](tv-standalone/engine/overlay) |
| Theme generators and watchdog | [`tv-standalone/scripts`](tv-standalone/scripts) |
| Automatic root and engine startup | [`tv-standalone/recovery`](tv-standalone/recovery) |
| Private bundle builder and management CLI | [`tv-standalone/tools`](tv-standalone/tools) |
| Tests | [`tv-standalone/tests`](tv-standalone/tests) |

Additional details: [Sponsored detection](tv-standalone/SPONSORED_PILL.md),
[experimental layout detector and off switch](tv-standalone/EXPERIMENTAL_LAYOUT.md).
The [computer-assisted guide](COMPUTER_ASSISTED.md) documents the optional
Docker/Claude implementation at the repository root. Research under
[`experiments`](experiments) is separate from the deployed app and is not a
promise of production accuracy.

## Privacy and limits

Debug mode is opt-in, bounded to 48 hours and a storage cap. It saves screenshots
with recognition/context metadata on the TV. Stopping debug or reaching its
expiry clears that session's records. The experimental classifier's temporary
frame handoff does not create a second recording archive.

Private device credentials, signing keys, signed packages, captured media,
private learned models, native Samsung binaries, and local deployment records
are excluded from this repository. Supply your own authorized device setup.
There is no bundled credential that makes Samsung recognition work on other TVs.

Ads can still be missed, and an experimental detector can misidentify a show.
No measured detection-accuracy guarantee is established. Timing and compatibility vary
with firmware, capture availability and the recognition service. Report concrete
failures through the [issue tracker](https://github.com/daoakley/commercial-break/issues)
without posting private captures or credentials.

## License

Free to use, modify and share under the [MIT License](LICENSE). Third-party
projects and the TV's proprietary libraries retain their own licenses.
