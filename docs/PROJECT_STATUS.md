# Project status — 24 October 2026, evening EDT

This is the authoritative status at handoff. Earlier chronological notes describe experiments, not necessarily the current deployment. The development branch is `feat/context-and-fast-detection`, PR #5. It remains a draft. **The requested 10× ad-detection improvement has not been demonstrated.**

## Deployment matrix

| Component | Owner's live system | Repository development source |
|---|---|---|
| Detector | Sequential `/v1/frame`; exact Python snapshot in `reference/deployed-2026-10-24/` | Root `server.py` additionally contains pending native onset and one-second post-response idle changes |
| Capture | One-shot .NET capture; source snapshot `reference/deployed-2026-10-24/CaptureProgram.cs` | `tv-probe/Program.cs` retains the suspended persistent/completion-handshake experiment |
| TV controls | Mute, active backlight 5/50, static information card, panel masking during covered captures | Overlay source additionally has pending spacing/text-fitting changes |
| Fast modes | `FAST_MODE=0`, `CAPTURE_PERSISTENT=0`, `OVERLAY_WARM=0`, `ENABLE_REALTIME=0`; navigation observer enabled | Experimental code retained; do not enable the combination that caused a black/show loop |
| Native metadata | One dashboard subscriber; observation-only; timeout repair active | `dashboard/` portable copy; `youtube_events.py` also contains an unfinished standalone onset relay |
| Native mute | **Not deployed or enabled** | Authenticated endpoint and one-shot next-frame hint exist; still requires review and live validation |
| Audio | No continuous collector or audio-controlled mute | Bounded observation-only research in `research/audio/` |
| Latest screenshot | Authenticated in-memory frame cache active | `/v1/latest-frame` in both source variants |
| Dashboard | Localhost UI, metadata, screenshots and human labels | Portable `dashboard/` source; no screenshots, labels or tokens committed |

A normal build at repository root builds **development code**, not the exact owner deployment. Source being present on GitHub does not mean it was deployed or validated on the TV. Do not use old release ZIPs to restore the latest system.

## What works, with evidence limits

- Temporary root and process-local capture-library patch enabled internal 480×270 screenshots on one Frame/firmware. Playback continues while the static card covers commercials.
- Confirmed program return releases owned controls. Navigation generation and stale-result admission guards are implemented. Physical channel changes and sports/news still need broader prospective validation.
- A fixed YouTube TV Sponsored-pill template can bypass vision on a matching frame. Many broadcast ads have no such pill; generic banners are not safe evidence.
- Dashboard reuses incoming frames without an additional AI call, exposes their age, and can request a separate bounded displayed-screen capture including the card.
- YouTube DIAL/Lounge supplies playback identity, position, duration, seekable ranges and some inserted-ad events. No reliable channel name, show title or scheduled broadcast start is established. Visually inferred show names are explicitly guesses.
- Python 3.9 socket timeouts previously escaped the poll loop and caused reconnect churn. Repair retained one connection through 19 recovered timeouts over 300.2 seconds / 21 status checks, with advancing frames and no observed app exit. This does not prove indefinite stability or the exact mechanism of earlier app exits.
- Internal ALSA PCM works even while speakers are muted. Selected repeated ads match acoustically. No general non-AI ad classifier or calibrated long-run false-alarm rate exists.

## Latest measured delay

The latest examined break had these **decision/actuation timestamps**, not independently annotated optical onset:

| EDT | Decision |
|---|---|
| 22:34:40 | uncertain, 0.55; no block |
| 22:34:49 | ad, 0.66; below the 0.70 minimum, no block |
| 22:35:00 | ad, 0.96; block applied |

The deployed policy permits a one-frame ad at >=0.85 after program establishment. This example did not wait for a second high-confidence ad. It waited through ambiguous/low-confidence frames. Capture took ~0.7 seconds uncovered; AI requests roughly 3–7 seconds; the sequential helper then slept, normally another five seconds. Decision spacing was often 9–14 seconds. The blocking-control phase took 0.93 seconds at this onset. The 20-second interval above does not include any ad footage before the first uncertain frame.

There is also a scheduling flaw: low-confidence `ad` clears the confident ad streak but is no longer `uncertain`, so it can fall back to the ordinary five-second sleep. The unpublished idle-time change addresses part of this, but is not a complete asynchronous design or a measured latency improvement.

At the latest diagnostic check the metadata observer was connected with one connection, 34 recovered timeouts and **zero inserted-ad events** for that playback context while vision had found commercials. More metadata alone cannot eliminate broadcast-ad misses.

## Next steps, ordered

1. Establish a single deployment manifest and measure first visible ad → arrival → local decision → AI completion → command → actual cover. Keep human reaction time and unobserved intervals explicit.
2. Review pending native onset binding (especially epoch reset), connection ownership and safety before enabling it. A valid onset should not queue behind AI. An end/absence event must never prove the full broadcast break ended.
3. Remove avoidable idle time after suspicious frames and separate latest-frame collection from slow classification. Validate display safety independently from scheduling; do not revive the failed fast/persistent/warm combination wholesale.
4. Reuse channel/content identity to invalidate stale in-flight work and per-show cadence. A prediction can prioritize observation, not independently cover a show.
5. Use Sponsored-pill, known-ad fingerprints and audiovisual transitions as distinct evidence sources with provenance and abstention. Evaluate sports/news sponsor graphics and split-screen play explicitly.
6. Prospectively measure p50/p95/max onset, misses, false program covers per viewing hour, return delay and model calls/cost. Report exact sample sizes and unknowns. No 10× claim without a comparable baseline.

See [architecture](ARCHITECTURE.md), [operations](OPERATIONS.md), [research](RESEARCH.md), [Claude handoff](CLAUDE_HANDOFF.md), and [issues](https://github.com/daoakley/commercial-break/issues).
