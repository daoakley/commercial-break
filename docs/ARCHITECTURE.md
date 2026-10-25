# Architecture and source map

## Current control path

```text
Samsung display capture → tv-agent.sh → authenticated /v1/frame
                                        ↓
                           identity admission / own-card rejection
                                        ↓
                           fixed Sponsored-pill template
                                        ↓ if no match
                           Claude bridge → signed-in Claude CLI
                                        ↓
                           verdict + context + mute policy
                                        ↓
TV response validation → mute/backlight/card → wait → next capture
```

The current loop is sequential. A configured sleep is not a screenshot period: capture, upload, classification and actuation are additional. Covered capture temporarily hides the card while physical panel mute keeps the image black; the internal capture stays readable. The mechanism has had contamination and display-loop failures, so timing benchmarks are not proof of visible correctness.

## Components

| Source | Responsibility |
|---|---|
| `tv-agent.sh` | Foreground identity, numbered frames, response validation, controls, timing log and cleanup |
| `tv-probe/` | .NET/PInvoke display capture; root version currently experimental; deployed source in reference directory |
| `patch-local-library.py` | Hash-checked process-local copy patch; original Samsung library never committed or changed in place |
| `tv-navigation/` | Passive input observation, no key injection/grab; advances navigation generation |
| `tv-overlay/`, `tv-overlay.sh` | Static card, lease, info file, hide/resume handshake; no animation |
| `tv-backlight.sh`, `tv-watchdog.sh` | Owned-setting restoration and independent stale-agent recovery |
| `server.py` | HTTP authentication, image intake, state, policy and vision request |
| `playback_identity.py` | Session/epoch/frame ordering, retired-session rejection and stale AI-result admission |
| `viewing_context.py` | Inferred identity/category, provenance, observed transitions, bounded cadence/timeline |
| `sponsored_badge.py` | Narrow fixed-resolution app UI template; not a general OCR/banner detector |
| `local_signals.py`, `realtime.py` | Own-card filter and experimental latest-frame/local-signal scheduler |
| `claude_bridge.py` | Host-only Claude Code calls, full prompt/context handling, optional private audit files |
| `youtube_events.py` | DIAL/Lounge transport and separate unfinished onset relay |
| `native_ads.py` | Pending fresh session-bound, one-shot onset hint; no native-end uncover |
| `dashboard/` | Local UI, cached frame, bounded explicit capture, metadata, study labels and coverage timeline |
| `research/audio/` | PCM studies, boundaries, repeated-ad fingerprints; no mute authority |
| `reference/deployed-2026-10-24/` | Detector snapshot verified against running image, dependency copies and deployed capture source |

## Identity and evidence contract

Foreground app identifies the app, not the in-app channel. Transport session identifies the TV helper/navigation generation, not YouTube content. Playback content ID is private and not a show title. App state `1` is playback active, not evidence of program rather than advertising. A raw cached ad ID is not a live onset.

The live Lounge experiment observed six `adPlaying` events, with playback state `1081`, associated with inserted advertising. Reported durations approached a common inserted-pod endpoint within 0.30 seconds. Broadcast ads existed on both sides of the pod. `adState` was -1 in those observed starts, so checking only for `adState==1` would miss them. End events/absence do not justify uncovering.

The development relay expects matching content identity, current position <=2 seconds, an `adPlaying`/1081 pair within one second and a fresh transport binding. `native_ads.py` admits hints within five seconds and consumes them on a subsequent frame. This still waits for a frame; it is not an independent immediate actuator. Review these assumptions against held-out events before deployment.

## APIs and privacy

- `/health`: liveness only; does not prove the TV is capturing or the model is available.
- `/v1/frame`: authenticated PNG and identity headers; action plus scheduling/context headers.
- `/v1/status`: authenticated state, context and transport identity; raw response is private.
- `/v1/latest-frame`: authenticated PNG, receipt timestamp and sequence; 404 before a frame; no-store. May show underlying content, not the physical card.
- `/v1/native-event`: development-only authenticated onset ingestion; absent in the deployed reference.
- `/v2/*`: optional experimental asynchronous endpoints, disabled in the current live configuration.
- Dashboard `/state`, `/latest-frame`, `/capture`, `/capture-image`, `/mark`: localhost-only proxy/label routes. Credentials remain in the server process. POST requires local Host/Origin and JSON. Labels do not mute the TV.

The dashboard retains latest displayed-screen capture in memory. Study labels persist privately. Detector context is in-memory and resets on restart; long-lived per-channel/per-show learning is not yet implemented. Claude screenshots leave the home network. The project does not disable Samsung ACR.
