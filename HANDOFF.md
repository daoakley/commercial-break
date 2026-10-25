# Commercial Break — current handoff

Updated 24 October 2026. **Ad-onset delay is still unresolved; a 10× improvement has not been demonstrated.** The owner requested a complete handoff to Claude. The current source and documentation are published on `feat/context-and-fast-detection` in [draft PR #5](https://github.com/daoakley/commercial-break/pull/5). Experimental runtime changes have not been merged into this default branch or deployed simply by publishing the handoff.

Read in this order:

- [Claude handoff](https://github.com/daoakley/commercial-break/blob/feat/context-and-fast-detection/docs/CLAUDE_HANDOFF.md)
- [Current deployment and unfinished work](https://github.com/daoakley/commercial-break/blob/feat/context-and-fast-detection/docs/PROJECT_STATUS.md)
- [Architecture and source map](https://github.com/daoakley/commercial-break/blob/feat/context-and-fast-detection/docs/ARCHITECTURE.md)
- [Operations, dashboard and recovery](https://github.com/daoakley/commercial-break/blob/feat/context-and-fast-detection/docs/OPERATIONS.md)
- [Research results and limitations](https://github.com/daoakley/commercial-break/blob/feat/context-and-fast-detection/docs/RESEARCH.md)
- [Validation actually performed](https://github.com/daoakley/commercial-break/blob/feat/context-and-fast-detection/docs/VALIDATION.md)
- [Verified deployed detector source](https://github.com/daoakley/commercial-break/blob/feat/context-and-fast-detection/reference/deployed-2026-10-24/)

The owner is running the sequential blocker with fast/persistent/warm modes off. YouTube metadata currently feeds the dashboard, not mute control. The dashboard observer's timeout/reconnect bug was repaired, but native-onset integration, display-loop diagnosis and held-out latency/false-cover measurement remain open. Audio research is observation-only.

The handoff package passed 84 core tests, 25 dashboard/transport tests and 8 audio-analysis tests; three TV helper builds passed. These checks do not establish live end-to-end improvement. Publication checks found no known credential values, private recordings or proprietary TV binaries in the package.

[Issues #1–4](https://github.com/daoakley/commercial-break/issues) were updated. [#6](https://github.com/daoakley/commercial-break/issues/6) tracks native onset/session safety and [#7](https://github.com/daoakley/commercial-break/issues/7) tracks deployment reproducibility. The owner's private handoff additionally lists exact machine paths and evidence locations; it is intentionally not published.

Source remains MIT licensed and free to use. The MIT license does not cover Samsung firmware binaries or private recordings, which are not distributed here.
