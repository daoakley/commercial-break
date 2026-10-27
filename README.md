# Commercial Break

Commercial Break is an experimental commercial muter for a Samsung Frame TV. A temporary TV-side helper captures a 480×270 screenshot of the active display and sends it to a detector on your computer. The detector asks a Claude Code vision bridge whether the frame shows a commercial. On a confirmed ad, the TV helper mutes the speakers, lowers the active backlight, and displays an opaque "Commercial Break" card. Playback continues underneath. It restores sound and brightness when program content returns.

For YouTube TV, the detector first checks the app's fixed upper-left **Sponsored** pill locally. A strong match mutes on that frame without waiting for Claude; frames without the pill follow the normal vision path. The template is specific to 480×270 captures from the tested YouTube TV app. An optional relay (`youtube_events.py`) also subscribes to the app's own second-screen event feed and forwards the "inserted ad started" notices YouTube emits for the ads it inserts itself; the detector can cover on those without waiting for the model. Broadcast breaks carried inside a live channel produce no such notice, so the screenshot path stays primary.

This repository shares **source and reproduction steps**, not an installable Samsung app. The tested path needs temporary root access. The TV-side components are staged manually and disappear or stop after a reboot. Nothing here disables Samsung tracking.

## Status

The separate [local visual research lab](experiments/vision-lab/README.md) contains the current observation-only capture review, Samsung-positive learning, and pretrained MobileCLIP experiments. See the [learning roadmap](docs/LOCAL-LEARNING-ROADMAP.md) for implemented versus planned work, validation requirements, and the path toward TV-only inference. These experiments do not replace or activate the production detector described below.

This is a personal prototype that works on one TV. It is published so that others with the same hardware can reproduce it and so that the approach is documented. Open work is tracked in the [issue tracker](https://github.com/daoakley/commercial-break/issues); in particular, the delay between an ad starting and the card appearing is still measured in seconds, and the return to program content takes longer than that because screenshots taken while the card is up briefly expose the screen.

## What was tested

The complete capture and control path worked on a **2022 Samsung Frame QN65LS03BAFXZA, firmware T-PTMAKUC-1720.7**, running Tizen 6.5 and .NET Core 3.1. The screenshot helper captured YouTube TV and Home-screen frames. During live YouTube TV ad breaks, the helper muted, dimmed, displayed the card, and restored the original active backlight and sound when the program returned. This is one result on one TV, not a compatibility claim for other models or firmware. Other apps and protected video paths may behave differently.

The capture probe calls Samsung's `dc_request_capture_to_file_sync` in `libdisplay-capture-api.so.0`. On the tested firmware, `libtzcapturec.so` restricts this call to an allowlisted executable. `patch-local-library.py` verifies the SHA-256 of a copy of **your TV's** original library, then changes one entry from `/usr/bin/tzcapturesample` to `/usr/bin/dotnet`. The patched copy is loaded only into the .NET probe process with `LD_PRELOAD`. The installed TV library and firmware are not changed. The script refuses any library that differs from the tested firmware copy; do not bypass that check blindly.

```text
TV capture/helper --authenticated LAN request--> Docker detector
TV mute, backlight, card <-- MUTE or UNMUTE --- Docker detector
Docker detector --authenticated request--> host Claude Code bridge --> Claude
```

TizenBrew is **not required**. Samsung's developer bridge (`sdb`) is used to stage files, and [samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) provides the temporary root command path. An ordinary Samsung app certificate alone does not grant the capture access used here.

## Requirements

- A TV/firmware on which `samsung-tv-root archive-root probe` confirms the required foothold and temporary root route. The capture-library patch in this repository is restricted to the exact firmware hash above.
- Samsung Developer Mode with your computer's developer IP configured, and a compatible Samsung `sdb` command available on your computer.
- On the computer: Python 3, Docker Compose, a .NET SDK able to build `netcoreapp3.1` projects, and the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/overview) signed into an eligible personal subscription. The TV needs `/usr/bin/dotnet` with a 3.1 runtime.
- A trusted local network. Do not expose the HTTP detector or bridge to the Internet.

The Docker container does **not** receive your Claude credentials. The host bridge keeps a small pool of long-lived Claude Code CLI sessions: the classification instructions travel once as the session's system prompt and each frame is one short turn with the PNG inline, which answers in about 1–2 seconds on the tested setup. This uses your subscription allowance and sends screenshots and viewing context to Claude. Check your provider's current terms before using this integration. `CLAUDE_BRIDGE_MODE=oneshot` selects the older one-process-per-frame path.

## 1. Set up the computer

Clone this repository, then from its root:

```sh
cp .env.example .env
cp tv.env.example tv.env
chmod 600 .env tv.env
```

Generate two **different** random tokens of at least 24 characters, for example with `openssl rand -hex 32`. Put the first token in `.env` as `FRAME_TOKEN` and in `tv.env` as the identical `FRAME_TOKEN`. Put the second token in `.env` as `VISION_SERVICE_TOKEN`. Set `.env` `BIND_IP` and `tv.env` `FRAME_URL` to your computer's LAN address. These two files are ignored by Git; keep them private. The host bridge listens on port 8787 so Docker Desktop can reach it, and the detector publishes port 28471 to the configured LAN address.

Sign in to the Claude Code CLI using its normal account login, then run:

```sh
./start-local.sh
curl -fsS http://YOUR_COMPUTER_LAN_IP:28471/health
```

The health response confirms only that the detector is reachable. It does not prove that the TV helper is running. `./stop-local.sh` stops the computer side.

To also use YouTube TV's inserted-ad notices, set `TV_HOST` in `.env` and run `./start-native.sh`; it starts `youtube_events.py`, which keeps one second-screen connection to the TV and posts validated notices to the detector. `NATIVE_ONSET_MODE` in `.env` decides whether the detector only logs them (`shadow`) or covers on them (`active`). Start with `shadow` and compare the log lines with the screenshot verdicts on real breaks before switching.

## 2. Build the TV helpers

```sh
dotnet build tv-probe/DisplayCaptureProbe.csproj -c Release
dotnet build tv-acr-probe/AcrFrameProbe.csproj -c Release
dotnet build tv-overlay/CommercialOverlayProbe.csproj -c Release
dotnet build tv-navigation/NavigationObserver.csproj -c Release
```

The TV helper uses the .NET DLL and runtimeconfig files from each project's `bin/Release/netcoreapp3.1/` directory. Compiled DLLs are deliberately excluded from this repository. The TV must have a compatible .NET runtime.

Two screenshot backends exist. `tv-probe` uses the display-capture call; `tv-acr-probe` uses the call Samsung's content-recognition service uses (`secvideo_api_capture_screen`), which on the tested firmware also works for protected streams, latches a frame in about 150 ms and converts the 720×576 result to the same 480×270 PNG. Both read the finished picture, card included, so a covered screenshot still hides the card briefly; the ACR probe keeps it hidden for about 0.2 s. Select with `CAPTURE_BACKEND` in `tv.env`.

## 3. Confirm temporary root and obtain your TV's library

Follow the [samsung-tv-root quickstart](https://github.com/chris-ritsen/samsung-tv-root) for your TV and install Samsung's `sdb`. Use these commands only after substituting your paths and TV address:

```sh
TV_IP=YOUR_TV_LAN_IP
SDB=/path/to/sdb
TVROOT=/path/to/samsung-tv-root
STAGE=/home/owner/share/tmp/sdk_tools

"$SDB" devices
"$TVROOT" --sdb "$SDB" archive-root probe "$TV_IP"
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'id'
```

On the tested TV, the original library is `/usr/lib/libtzcapturec.so`. Copy it to the developer-writable staging area using the authenticated temporary root route, pull it to a **Git-ignored** local `private/` directory, and remove the staging copy:

```sh
mkdir -p private
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'mkdir -p /home/owner/share/tmp/sdk_tools; cp /usr/lib/libtzcapturec.so /home/owner/share/tmp/sdk_tools/libtzcapturec-original.so; chmod 644 /home/owner/share/tmp/sdk_tools/libtzcapturec-original.so'
"$SDB" pull "$STAGE/libtzcapturec-original.so" private/libtzcapturec-original.so
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'rm -f /home/owner/share/tmp/sdk_tools/libtzcapturec-original.so'
python3 patch-local-library.py private/libtzcapturec-original.so private/libtzcapturec-probe.so
```

The patch succeeds only if the original library matches the tested `T-PTMAKUC-1720.7` SHA-256. Do not publish either library. On another firmware, inspect and validate the capture path independently before adapting it. A successful root probe alone does not establish capture compatibility.

## 4. Stage and start the TV helper

Push the four shell files, built .NET files, card scene, private TV settings, and temporary library. The staging path below is the one verified on the tested Frame:

```sh
for name in tv-agent.sh tv-watchdog.sh tv-backlight.sh tv-overlay.sh; do
  "$SDB" push "$name" "$STAGE/$name"
done
"$SDB" push tv-probe/bin/Release/netcoreapp3.1/DisplayCaptureProbe.dll "$STAGE/DisplayCaptureProbe.dll"
"$SDB" push tv-probe/bin/Release/netcoreapp3.1/DisplayCaptureProbe.runtimeconfig.json "$STAGE/DisplayCaptureProbe.runtimeconfig.json"
"$SDB" push tv-overlay/bin/Release/netcoreapp3.1/CommercialOverlayProbe.dll "$STAGE/CommercialOverlayProbe.dll"
"$SDB" push tv-overlay/bin/Release/netcoreapp3.1/CommercialOverlayProbe.runtimeconfig.json "$STAGE/CommercialOverlayProbe.runtimeconfig.json"
"$SDB" push tv-overlay/commercial-break-scene.json "$STAGE/commercial-break-scene.json"
"$SDB" push tv-acr-probe/bin/Release/netcoreapp3.1/AcrFrameProbe.dll "$STAGE/AcrFrameProbe.dll"
"$SDB" push tv-acr-probe/bin/Release/netcoreapp3.1/AcrFrameProbe.runtimeconfig.json "$STAGE/AcrFrameProbe.runtimeconfig.json"
"$SDB" push tv-navigation/bin/Release/netcoreapp3.1/NavigationObserver.dll "$STAGE/NavigationObserver.dll"
"$SDB" push tv-navigation/bin/Release/netcoreapp3.1/NavigationObserver.runtimeconfig.json "$STAGE/NavigationObserver.runtimeconfig.json"
"$SDB" push private/libtzcapturec-probe.so "$STAGE/libtzcapturec-probe.so"
"$SDB" push tv.env "$STAGE/muter-live-tv.env"
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'cp /home/owner/share/tmp/sdk_tools/libtzcapturec-probe.so /run/libtzcapturec-probe.so; chmod 600 /run/libtzcapturec-probe.so /home/owner/share/tmp/sdk_tools/muter-live-tv.env'
```

An `sdb push` may loosen file permissions, so the final `chmod` matters. On the tested TV, Tizen blocked direct execution of the unsigned shell file. Run it as text inside the established root command path:

```sh
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'mkdir -p /run/codex-commercial-muter; if [ -f /run/codex-commercial-muter/heartbeat ]; then echo agent-already-running; else set -a; . /home/owner/share/tmp/sdk_tools/muter-live-tv.env; set +a; AGENT_DIR=/home/owner/share/tmp/sdk_tools setsid /bin/sh -c "$(cat /home/owner/share/tmp/sdk_tools/tv-agent.sh)" >/run/codex-commercial-muter/agent.log 2>&1 </dev/null & echo agent-started; fi'
```

Check for a fresh TV heartbeat and incoming decisions. Do not start a second agent when one is already running:

```sh
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'date +%s; cat /run/codex-commercial-muter/heartbeat 2>/dev/null || echo no-heartbeat; tail -n 5 /run/codex-commercial-muter/agent.log 2>/dev/null'
docker compose logs --tail=20 detector
```

To stop cleanly, request a TV-side stop first, wait for its heartbeat to disappear, then run `./stop-local.sh`:

```sh
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'touch /run/codex-commercial-muter/stop'
```

The default `tv.env.example` limits the first TV run to 15 minutes. If the agent owns a mute at that limit, it may extend until the show returns, with a five-minute maximum extension. After validating restoration on your TV, you can set `MAX_RUNTIME_SECONDS=0` for an unbounded session. The TV agent has no boot hook. Rebooting requires restaging the temporary library and restarting the agent; a firmware update requires revalidating the library hash and capture behavior before doing either.

## Decision and fail-safe behavior

The detector tracks recent program and ad observations in memory. A matched YouTube TV Sponsored pill mutes on one frame. Without the pill, a model-labeled ad at confidence 0.85 or higher can mute on one frame when a program is established, including after uncertain cutaway frames; otherwise it waits for two distinct ad frames. The prompt requires promotional evidence in the current frame: a change from the previously known show is not itself an ad, and the `program_changed` flag is reserved for `program` frames so that a trailer cannot block its own one-frame mute. A screenshot of the project's own cover card is classified as an obscured frame, never as an ad. There is no generic banner detector.

While uncovered the helper sleeps `PROGRAM_IDLE_SECONDS` (default 1 s) after each response, so with a ~1.5 s model answer and ~0.7 s capture a clear ad frame is usually covered within about 4–8 seconds of its start. During a confirmed break the helper waits 8 seconds between screenshots with the display backend, or `COVERED_IDLE_ACR_SECONDS` (default 4) with the ACR backend, because each covered capture briefly blanks the panel. Two program frames are required before anything uncovers; a first program frame is confirmed after 2 seconds. Two moderate-confidence frames identifying a coherent new program release the cover and reset the learned break cadence; one strong new-program frame can release it while muted. Break timing never orders a mute on its own.

Two things shorten the covered wait without weakening that rule. If the native relay reports that an inserted-ad pod ended, the covered helper (which polls `/v1/wake` once a second) takes its next screenshot immediately instead of waiting out the gap; an end inside a pod, followed within 1.5 s by the next ad, is ignored. And the viewer's own unmute is honoured within a second: pressing the remote's mute key so that the speakers come back on drops the card, restores brightness, and stops the helper from re-muting for the rest of that break. Remote navigation (guide, back, channel) releases the cover as well.

The TV helper reads Tizen's current foreground app ID for each frame, using the configured `TV_APP` only if that read fails. A changed channel/title also resets the detector when supplied, but no reliable live YouTube TV channel/title feed was found on this Frame; a native Media Controller client returned `-38` when created in a temporary root shell.

An observed program counts as established even if the model cannot give it a title. The detector logs the ad/program label, confidence, program-change flag, and classification time, without logging the screenshot or viewing description. These fields help separate a slow model response from a policy decision when coverage is late.

If capture, the network, Docker, or the model fails, the helper releases the mute and active backlight change **that it owns**. The card has a renewable lease and disappears if the helper stops renewing it. A watchdog retries restoration after an unexpected helper stop. The viewer can always use the remote. The helper never pauses playback or changes channels. Test all of these behaviors before extended use on another TV.

The card covers the display screenshot, so it briefly clears for each capture and then returns. With the display backend the card returns about 225 ms after the capture starts; shorter latches captured the card itself. With the ACR backend the frame is latched inside the capture call, about 150 ms. The optional `PANEL_MASK_ON_CAPTURE=1` setting uses the TV's **LFD panel-mute control** to turn the physical screen fully black while the card is hidden. The internal screenshot remains clear. The capture helper waits for the physical panel to blank before hiding the card, then waits after the card returns before unmuting the panel, and a separate four-second rescue unmutes the panel if capture exits abruptly. On the tested Frame the panel followed the command within 50 ms each way: margins of 50/30 ms never showed the picture and 0/0 ms did once, so the ACR probe defaults to 100 ms before hiding the card and 60 ms after it returns (`ACR_PANEL_LEAD_MS`, `ACR_PANEL_RETURN_MS`). `PANEL_MASK_ON_CAPTURE=0` is the default, and the setting must be re-enabled whenever the temporary TV agent is restarted. Active backlight at 0/50 was tested as a mask first but left the image clearly visible. A blur or noise overlay would appear in the captured image as well. Every capture path on this TV reads the finished picture: the video-plane call and the "post" variant refuse protected streams, and the content-recognition path includes overlays, so no path can see beneath the card.

Claude classifications can miss ads or identify them late. This is a prototype, not a guarantee that every commercial will be hidden.

## Privacy and repository contents

By default, the TV deletes each PNG after submission, the host bridge removes its temporary PNG after classification, and the detector keeps only short in-memory context. Optional audit capture in `claude_bridge.py` is disabled unless you set `TV_AUDIT_DIR`. Screenshots and viewing context **are sent to Claude**. Commercial Break does not block Samsung's ACR or other tracking. Do not put `private/`, `.env`, `tv.env`, captured images/audio, or any copied Samsung library in a public commit.

The repository contains only the core commercial-break source, tests, and examples. It intentionally excludes personal recordings, proprietary TV binaries, and private measurements.

Run the included policy and bridge tests with:

```sh
python3 -m unittest discover -p 'test_*.py'
```

This project builds on the independent [samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) project and Samsung's developer tools. Those dependencies are not bundled here.

### Standalone TV appearance preview

See [TV appearance themes](tv-standalone/README.md) for the isolated standalone controller source, seasonal/holiday/zen scenes, offline preview, and validation instructions. Installed on the development Frame TV; physical navigation and themed-overlay appearance still await viewer validation.
