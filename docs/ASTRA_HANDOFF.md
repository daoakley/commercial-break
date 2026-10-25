# Superseded handoff

Read [Claude handoff](CLAUDE_HANDOFF.md) and [current status](PROJECT_STATUS.md) first. The text below is a historical snapshot and is not the current deployment manifest.

# Commercial Break handoff — 24 October 2026

## Current live configuration — sequential path active

The sequential TV helper is running again with `FAST_MODE=0`,
`CAPTURE_PERSISTENT=0`, `OVERLAY_WARM=0`, `ENABLE_REALTIME=0`, and
`NAVIGATION_OBSERVER=1`. The earlier fast/warm trial caused a black/show loop
and remains disabled. Do not restart that experimental combination.

The information card was enabled at approximately 21:39 EDT after a bounded
native preview and recognition check. It displays provenance-aware context,
observed timing and a sampled timeline; see [Information card](OVERLAY_INFORMATION.md).
The native YouTube ad-event research remains observation-only and is not a
replacement for the current visual detector. PR #5 is still a draft.

Commercial Break is a free experimental commercial muter for one owner's 2022 Samsung Frame (`QN65LS03BAFXZA`, `T-PTMAKUC-1720.7`, Tizen 6.5). This repository has source and reproduction steps. The owner's live TV uses the same core detector source with private configuration, TV-specific binaries, and local capture logs kept outside Git. Read [README.md](../README.md) before changing the implementation.

## Working system

The TV uses a temporary-root helper, enabled through [samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root), to call its own display-capture API. A process-local, hash-checked copy of one TV library permits the .NET capture probe to take a 480×270 screenshot; no installed firmware library is modified. The TV sends each frame and foreground app ID to an authenticated Docker detector on the owner's Mac. A separate host bridge uses the owner's signed-in Claude Code CLI to classify frames. The Docker container has no Claude credentials. On confirmed ads, the TV agent mutes its speakers, dims only the active backlight, and shows an opaque `Commercial Break` card with optional viewing information. Playback continues. The helper restores settings on program return or service failure; the card has an expiring lease and a watchdog backs up restoration. The viewer can override mute with the remote.

The local YouTube TV `Sponsored` badge detector can mute without Claude. The live TV uses the sequential `/v1/frame` path with `FAST_MODE=0`, `CAPTURE_PERSISTENT=0`, `OVERLAY_WARM=0`, `ENABLE_REALTIME=0`, and `NAVIGATION_OBSERVER=1`. The earlier fast capture/warm-overlay experiment caused a black/show loop and was rolled back; its timing measurements do not establish stable production performance. Physical-panel masking remains enabled during covered captures. No animation is in use or planned. Read [Detection design](DETECTION_DESIGN.md) for the experimental implementation, measurements, flags and rollback.

This does **not** disable Samsung ACR or other tracking. Frames and viewing context go to Claude. Any private audit screenshots/audio remain on the owner's machine and must not enter this public repository. A TV restart or standby may stop the temporary agent; Docker health alone does not prove the TV agent is running.

## Latest change and evidence

A paired-client experiment connected to the running YouTube TV app through
its advertised DIAL application status and YouTube Lounge. It received live
now-playing identity, playback position and duration. A subsequent five-minute
break test received six `adPlaying` events with distinct IDs, each accompanied
by playback `state=1081`. Their decreasing durations predicted one shared
inserted-segment endpoint within a 0.30-second spread. Their `adState` was -1,
so a naïve `adState==1` rule would miss them.

Saved TV footage showed broadcast commercials both before those events and
after the native segment ended. Native events are therefore a candidate
supplementary onset source, not complete break coverage or a safe release
signal. Keep visual fallback and program-return confirmation. Channel/seek
binding, stale events and held-out false alarms remain unvalidated. This feed
still has no production mute authority; private evidence and credentials are
not included in the repository.


Astra’s audit found that the bridge truncated instructions at 1,600 characters, so earlier offline prompt successes did not establish that all safeguards reached the live model. Complete instructions and JSON context now pass through, with explicit size rejection. Local own-card filtering prevents a contaminated screenshot from renewing ad evidence; seven saved card frames were inspected, six formerly labeled as ads.

During live work, a channel change left HGTV renovation footage covered because a small corner “Tonight 10/9c” banner was classified as a full commercial. The cover, sound and brightness were restored. The actual failing screenshot then classified as program 0.85 with `in_program_promotion`, even under stale movie/ad context. This distinction is now enforced in policy. A passive evdev observer detects navigation, clears owned controls and advances the context generation. It does not grab or inject keys and stores no key history. Physical remote behavior on this TV still needs the owner’s confirmation; opening eight input devices and a software generation-reset test are not equivalent to that confirmation.

The context model separates supplied metadata from inferred show/category, first observed time from actual broadcast start, and observed timing ranges from evidence that an ad is on screen. Bounded private read-only research recovered channel IDs, advancing playback counters and cached ad records from YouTube TV. A reliable continuous current-channel/show feed is not yet connected; cached records are not ad-playing evidence. Timing memory is currently per viewing context, not persistent across restarts. New brightness/composition and audio features can request an earlier check but cannot mute on their own. Two-second known-ad fingerprint experiments are promising but remain offline/observation-only.

## Playback identity update

The sequential detector now admits frames by TV agent/navigation session and optional increasing frame sequence. Retired sessions, older navigation generations, and duplicate/out-of-order numbered frames are rejected. Classification runs against a private state copy; a result commits only while its admission ticket remains current. A context reset clears the old show, ad votes, cover decision and cadence without waiting for the old model call. Supplied channel/show metadata remains distinct from visual inference and unknown identity.

The TV reads foreground identity before capture and rechecks it before submission, after the response and after actuation. Missing foreground identity fails open. The existing passive navigation observer continues to release owned controls independently. Capture intervals and ad confidence thresholds were not changed. These protections do not establish automatic identification of a same-app channel change that produces no observed navigation event.

Authenticated `GET /v1/status` exposes the current transport identity, accepted frame sequence, observation timestamp, detector mute state and viewing context. It uses the existing frame credential; never put that credential in a URL or public output. A transport session is not a YouTube playback ID.

Validation: 69 tests pass, including blocked old AI calls during resets, out-of-order frames, agent restart, and the real TV shell loop against isolated app/capture/control fakes. Live deployment accepted numbered YouTube TV frames and returned program decisions. Advancing only the helper navigation marker increased both identity and viewing generations, returned an immediate no-model UNMUTE decision, cleared cadence, and then resumed program classification without changing channel. Physical channel-change recovery still needs a prospective viewer test; simulated races are not a measured on-screen recovery time.

## Prioritized open work

1. [Measure and reduce live ad onset latency](https://github.com/daoakley/commercial-break/issues/1). Record capture, classification, and TV actuation timestamps; measure first ad frame to cover, false program mutes per hour, return-to-show delay, and Claude calls per hour across held-out breaks. Shorten onset without assuming every scene change is an ad.
2. [Prevent the card from contaminating captures](https://github.com/daoakley/commercial-break/issues/2). Actual capture completion now controls the pause, and a local own-card filter supplies a second guard. Continue measuring contamination and mask behavior across held-out breaks.
3. [Find reliable YouTube TV channel/show metadata](https://github.com/daoakley/commercial-break/issues/3). The foreground app ID is available, but in-app channel/title remain unknown. A read-only Tizen Media Controller client returned `-38`. Avoid inventing metadata or using an unverified schedule.
4. [Validate known-ad audio fingerprints](https://github.com/daoakley/commercial-break/issues/4). Internal PCM capture worked and two known ads repeated, but the non-AI path remains observation-only until prospective held-out evidence demonstrates a very low false-mute rate.

## Guidance for the next agent

Start with repository source, tests, and these issues. Preserve the fail-open behavior: if TV capture, network, Mac, or model fails, normal sound and playback must continue. Keep changes to the live detector narrow and test them on saved ad, program, show-transition, and own-card examples before deployment. A model confidence score by itself is not a calibrated error rate. Do not copy `.env`, `tv.env`, tokens, Samsung libraries, personal screenshots/audio, or viewing history into GitHub issues, commits, or chat output. Do not run a second TV audio collector while one is active. Coordinate any live TV test with the owner if it could interrupt viewing. The abandoned dog/dinosaur animation is out of scope.

Suggested starting request for an Astra chat: “Review [Commercial Break](https://github.com/daoakley/commercial-break), especially the [handoff](https://github.com/daoakley/commercial-break/blob/main/docs/ASTRA_HANDOFF.md) and [issues](https://github.com/daoakley/commercial-break/issues). Improve ad-onset latency and reliability without increasing false program mutes or breaking the TV's fail-safe behavior. Begin by measuring the existing pipeline and validating changes against held-out real TV evidence. Keep private recordings and secrets out of the public repo.”
