# Operations, reproduction and recovery

Read [current status](PROJECT_STATUS.md) before building. The README contains initial root, library-patch and staging instructions. They are manual, firmware-specific steps, not a portable installer. A certificate alone does not grant this capture path. TizenBrew is not a runtime dependency.

## Source and deployment discipline

1. Record git commit, source hashes, image ID, TV source/binary hashes and startup flags before a change. Save rollback artifacts privately. A working source directory is not proof of the running version.
2. Run relevant tests. Test display changes in isolation and confirm physical output; screenshots cannot prove that the physical panel looks correct.
3. Deploy only the reviewed component. Restarting the dashboard does not require restarting Docker or the TV helper. Rebuilding the root Dockerfile activates pending detector changes.
4. Never run duplicate TV agents, audio collectors or Lounge subscribers. Current subscriber lock is a local file; running another checkout can bypass that lock. Operational coordination remains necessary.
5. Recheck live app, fresh numbered frames, cover state and program return after changes. Treat pids, IPs, filenames and counters in old notes as historical.

The exact detector reference can be built independently, without deploying it:

```sh
docker build -t commercial-break-reference:20261024 reference/deployed-2026-10-24
```

Do not pass secrets as build arguments or add env files to images. The root development Dockerfile is a different detector. The reference capture source can be copied as `Program.cs` into a separate copy of the existing capture csproj for a one-shot build; do not enable persistent capture with it. Compiled binaries and Samsung libraries are deliberately absent.

## Dashboard

Python standard library, macOS/Linux host. From the repository root:

```sh
python3 dashboard/server.py --data private/labels --port 8792 \
  --detector-env .env --detector-url http://YOUR_COMPUTER_LAN_IP:28471 \
  --tv-host YOUR_TV_LAN_IP
```

Open `http://127.0.0.1:8792/`, not the HTML file. Use the detector's actual bind address; a detector bound only to a LAN address may not answer localhost. The frame credential is read from `.env`, not embedded in the browser.

For optional displayed-screen capture, set `TVROOT` and `SDB` in the environment to executable paths. This requires the existing temporary root/capture setup. It is bounded to 30 seconds, preserves the previous image on failure, and does not drop the card or change playback. **Show latest frame** is the quick path: it uses the incoming cached image, makes no extra AI call, and displays age/staleness. Neither button guarantees a new image every second.

The native subscriber connects only when fresh detector identity says YouTube TV is foreground. It sends state queries, not playback controls. Timeout recovery stays in the same session. It pauses after repeated transport failures or a source exit shortly after connecting; even legitimate early navigation can trigger this conservative pause. There is no automatic proof that a paused observer should be restarted. Check playback and logs first.

For optional coverage sampling during a human study, also set `TV_HOST` to the same TV address and `OBSERVER_BIND_IP` to the computer's reachable LAN address, with `TVROOT` and `SDB`, then add `--tv-observer`. Port 8793 receives token-authenticated bounded TV samples. Keep it on the trusted LAN. Choose 5, 15 or 30 minutes; extend if needed; mark ad/program/channel changes only while paying attention. Viewer labels, AI labels and inferred transitions must remain distinct.

Do not run `start-native.sh` alongside the dashboard observer. The standalone onset relay is a pending experiment and lacks the dashboard's full stability circuit breaker. Its endpoint is absent from the deployed reference. Integrate one shared subscriber rather than launching two.

## Health and failure handling

Check TV heartbeat and advancing frame sequence, detector decisions, bridge availability and metadata freshness separately. Docker health alone is insufficient. Logs should contain timing/counters rather than tokens, complete requests or private IDs.

| Symptom | First response |
|---|---|
| App exits after observer work | Stop/review the metadata observer independently; preserve the existing muter; inspect connection count and recovered timeouts |
| Card stuck after channel change | Release owned controls, check navigation generation and stale decisions, inspect current content; do not keep an old ad state |
| Black/show loop | Keep fast/persistent/warm modes off; use deployed one-shot capture; inspect panel/overlay lease behavior |
| 20+ second onset | Examine capture/request/actuation plus idle gaps and low-confidence follow-up; metadata on the dashboard is not actuation |
| Missing titles | Show unknown or visually inferred title; no reliable native title/EPG feed has been demonstrated |
| No fresh frames | Check TV power/developer link/root lifetime and capture; Mac health does not establish TV health |
| Mac/model unavailable | Fail open, restore only owned settings, expire the card lease; do not pause playback |

Request a clean TV-helper stop using its `stop` marker and wait for cleanup before stopping the computer side; see README for commands. Do not blindly kill a PID from an old file. If helper cleanup fails, inspect panel mute, speaker mute, owned-backlight and overlay lease independently. Do not restore a hard-coded brightness value. TV restart removes temporary `/run` resources; revalidate firmware/library hash before restaging.

## Secrets and retention

`FRAME_TOKEN` authenticates TV→detector and dashboard server→detector. `VISION_SERVICE_TOKEN` authenticates detector→host bridge. Claude login remains in the host CLI's own account store. YouTube pairing/session credentials stay private/in memory. The optional study observer generates a separate bounded receiver token. Keep `.env`, TV env, local recovery copies and study files owner-readable. Rotate matching endpoints together if exposed; never print process environments or token-bearing command lines.

Public docs use placeholders. Do not publish Samsung binaries, screenshots, PCM/WAV, labels, raw event/session IDs, recovery env files, signed TV packages or private audit databases. Derived source templates are included, not personal recordings. Historical raw diagnostic logs may contain secrets and are not safe publication candidates.

## Tests

Run the suites separately because the dashboard and detector both have `server.py` and `test_server.py`:

```sh
python3 -m unittest discover -s . -p 'test_*.py' -q
(cd dashboard && python3 -m unittest discover -s . -p 'test_*.py' -q)
(cd research/audio && python3 -m unittest discover -s . -p 'test_*.py' -q)
```

Audio fingerprint tools additionally need NumPy. Build each TV csproj with a compatible .NET SDK; compilation alone does not validate Samsung APIs. See `VALIDATION.md` for checks actually run at this handoff.
