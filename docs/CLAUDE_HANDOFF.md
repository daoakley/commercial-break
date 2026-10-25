# Claude handoff — Commercial Break

Read `PROJECT_STATUS.md` first, then `ARCHITECTURE.md`, `OPERATIONS.md`, `RESEARCH.md` and `VALIDATION.md`. This handoff replaces the older Astra handoff. The owner wants fast, reliable ad obscuring on their own TV, including channel/show changes and sports/news. The main unresolved problem is 20+ second ad-onset delay. Do not claim the data collection and dashboard work solved it.

## Start here

1. Verify branch/commit and distinguish root development source from `reference/deployed-2026-10-24/`. The owner's separate private workspace includes exact executable paths, private evidence and credentials; obtain the local handoff from the owner. Do not ask the owner to paste credentials into chat.
2. Inspect current health without changing playback. Confirm whether metadata is connected/paused, that frames advance, and whether an audio or Lounge observer already owns the connection. No service restart is required just to inspect state.
3. Reproduce the latest measured delay and identify idle gaps, low-confidence retries, stale frame age and actuation time. The latest 20-second sequence was uncertain → ad 0.66 → ad 0.96; control application was only ~0.9 seconds.
4. Make one bounded improvement at a time and report what is actually deployed. Preserve fail-open behavior if the computer/model disappears. Never hold a stale cover after navigation.

## Important unfinished code

- Root `server.py`: one-second post-response idle plus `/v1/native-event` ingestion and next-frame native hint; not active in owner's deployed image.
- `native_ads.py`: review epoch handling. Playback binding's `same` comparison checks connection/session/content but omits epoch; it may preserve pending onset across an epoch-only reset. Do not deploy until tested/fixed.
- `youtube_events.py`: standalone onset relay shares the transport but not every dashboard stability guard. Its current finalizer uses a fixed termination RID. Review session lifecycle and query sequence rather than assuming the five-minute dashboard validation covers the standalone relay.
- Native hints expire after five seconds and are consumed only on a subsequent frame. Existing slow sampling may miss them. Validated native onset needs a bounded, identity-safe command route independent of a slow AI request; do not treat end events as program proof.
- `tv-probe/Program.cs`: experimental persistent/completion-based source; the deployed one-shot source is separately preserved. Do not replace the live DLL merely because root source is newer.
- `tv-overlay/CommercialOverlayProbe.cs`: pending layout/text-fitting changes, not confirmed deployed. Animation was rejected and is out of scope.
- Dashboard metadata is read-only. It has no production path to mute, cadence policy or confirmed show title. Portable public paths differ from the owner's running dashboard paths.
- Learning is bounded in memory; truly persistent per-channel/per-show profiles are unfinished. Scheduled start, wall time, stream position and first observed time are different values.

## Acceptance criteria

Use held-out real breaks and long program segments, including channel changes during ads, new shows on the same channel, live sports sponsor bugs/split screens, news lower thirds, full-screen promos, guides/loading, app exits, model/network failures and TV restarts. Record onset p50/p95/max, missed ads, false covers per hour, return delay and calls per hour. Preserve abstention where evidence is weak. Report unknown onset windows instead of assigning a convenient timestamp. A model score is not a calibrated probability.

For audio, keep shadow-only until held-out evidence supports a very low false-alarm rate. Never start a second audio collector. Known-ad fingerprints are distinct from silence/cut/brightness hints. For UI validation, verify the actual physical screen with the owner: internal screenshots alone did not reveal the black/show loop.

## Do not repeat these mistakes

- Do not equate published source, a successful build, fresh metadata or a healthy container with a deployed improvement.
- Do not quietly slow capture after a regression or promise a one-second capture requirement; the goal is shortest reliable end-to-end onset.
- Do not rely on ad duration/cadence as proof, or let a generic brand/banner obscure continuing sport/news.
- Do not confuse program-return recovery with a successful onset experiment.
- Do not publish private recordings, tokens, raw session IDs or proprietary libraries. Project is MIT licensed; this does not license third-party firmware/data.
- Do not revive the failed fast/persistent/warm display combination without isolating its cause.

GitHub PR #5 remains draft. Existing issues #1–4 track onset, capture contamination, metadata and audio. [Issue #6](https://github.com/daoakley/commercial-break/issues/6) covers native onset/session safety; [issue #7](https://github.com/daoakley/commercial-break/issues/7) covers source/deployment divergence. This is a research prototype, not a finished appliance or a validated 10× improvement.
