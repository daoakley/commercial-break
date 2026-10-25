# Validation at Claude handoff — 24 October 2026

These checks validate the published development package; they do not deploy it or establish end-to-end ad-detection performance.

| Check | Result |
|---|---|
| Core detector/bridge/identity/local/native/TV shell-policy suites | 84 tests passed on host Python 3.9.6 |
| Portable dashboard, labels, capture, metadata and transport | 25 tests passed on host Python 3.9.6 |
| Audio boundary/fingerprint analysis regressions | 8 tests passed |
| Published shell files | Shell syntax passed |
| Dashboard app.js | Node syntax check passed |
| Capture, navigation and overlay .NET projects | All three Release builds passed, zero warnings/errors |
| Deployed reference | server.py and seven runtime dependencies matched SHA-256 read directly from running container |
| Publication privacy review | Known local credential values, credential signatures, private path/IP and recording/binary type checks found no matches in the publication set; known values also checked against existing Git blobs |

The privacy check is scoped to available known values and specified signatures/file types, not a proof that arbitrary historical strings can never be sensitive. No private env, recordings, raw event logs, study labels, Samsung libraries or compiled TV binaries are included. Secret values are not recorded in this document.

Prior live evidence, not rerun during this documentation task: five-minute metadata repair test, 300.2 seconds, 21 status samples, one connection, 19 ordinary timeouts recovered, fresh frames and no observed YouTube TV exit. This does not establish indefinite stability or prove why the TV previously exited the app. Earlier audio/visual studies are described with their limitations in RESEARCH.md.

Not validated: root development native-onset path as a live controller, epoch-only binding reset, new overlay spacing on the physical TV, persistent/warm/fast display stability, general audio-only detection, low long-run false-cover rate, exact first-ad-frame latency or a 10× improvement. No live services were restarted by the documentation/publication work. PR #5 remains draft.
