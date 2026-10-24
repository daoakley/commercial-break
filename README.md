# Commercial Break

Commercial Break is an experimental commercial muter for a Samsung Frame TV. A temporary TV-side helper captures a 480×270 screenshot of the active display and sends it to a detector on your computer. The detector asks a Claude Code vision bridge whether the frame shows a commercial. On a confirmed ad, the TV helper mutes the speakers, lowers the active backlight, and displays an opaque “Commercial Break” card. Playback continues underneath. It restores sound and brightness when program content returns.

For YouTube TV, the detector first checks the app's fixed upper-left **Sponsored** pill locally. A strong match mutes on that frame without waiting for Claude; frames without the pill follow the normal vision path. This template is specific to 480×270 captures from the tested YouTube TV app. In 1,589 saved frames from the owner's TV, it matched 68: 66 classified ads and two frames initially classified as program that visibly showed the pill over a political ad. Badge detection cannot shorten the wait until the TV takes its next screenshot.

This repository shares **source and reproduction steps**, not an installable Samsung app. The tested path needs temporary root access. The TV-side components are staged manually and disappear or stop after a reboot. Nothing here disables Samsung tracking.

## What was tested

The complete capture and control path worked on a **2022 Samsung Frame QN65LS03BAFXZA, firmware T-PTMAKUC-1720.7**, running Tizen 6.5 and .NET Core 3.1. The screenshot helper captured YouTube TV and Home-screen frames. During a live YouTube TV ad break, the helper muted, dimmed, displayed the card, and restored the original active backlight and sound when the program returned. This is one owner's result, not a compatibility claim for other models or firmware. Other apps and protected video paths may behave differently.

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

The Docker container does **not** receive your Claude credentials. The host bridge invokes your signed-in Claude Code CLI for each frame. This uses your subscription allowance and sends screenshots and viewing context to Claude. Check your provider's current terms before using this integration.

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

## 2. Build the TV helpers

```sh
dotnet build tv-probe/DisplayCaptureProbe.csproj -c Release
dotnet build tv-overlay/CommercialOverlayProbe.csproj -c Release
```

The TV helper uses the .NET DLL and runtimeconfig files from each project's `bin/Release/netcoreapp3.1/` directory. Compiled DLLs are deliberately excluded from this repository. The TV must have a compatible .NET runtime.

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
"$SDB" push private/libtzcapturec-probe.so "$STAGE/libtzcapturec-probe.so"
"$SDB" push tv.env "$STAGE/muter-live-tv.env"
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'cp /home/owner/share/tmp/sdk_tools/libtzcapturec-probe.so /run/libtzcapturec-probe.so; chmod 600 /run/libtzcapturec-probe.so /home/owner/share/tmp/sdk_tools/muter-live-tv.env'
```

An `sdb push` may loosen file permissions, so the final `chmod` matters. On this TV, Tizen blocked direct execution of the unsigned shell file. Run it as text inside the established root command path:

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

The detector tracks recent program and ad observations in memory. A matched YouTube TV Sponsored pill mutes on one frame. Without the pill, one high-confidence ad frame immediately after a known program frame can mute; otherwise it waits for two distinct ad frames. During a confirmed break it waits 8 seconds after each response before another screenshot, reducing how often the card reveals the ad. If a frame suggests the program has returned, it checks again after 2 seconds; two confident program frames are needed before unmuting. The return may therefore remain covered for several seconds, plus model processing time. Break timing can increase screenshot frequency before an ad but never orders a mute on its own. The configured app ID and optional channel/title are hints; this project does not reliably discover YouTube TV's current channel or program title.

If capture, the network, Docker, or the model fails, the helper releases the mute and active backlight change **that it owns**. The card has a renewable lease and disappears if the helper stops renewing it. A watchdog retries restoration after an unexpected helper stop. The viewer can always use the remote. The helper never pauses playback or changes channels. Test all of these behaviors before extended use on another TV.

The card covers the display screenshot, so it briefly clears for each capture and then returns. The TV helper now restores the card about 225 ms after starting native capture, while the PNG finishes writing. An isolated 200 ms test measured about 0.30 seconds uncovered and saved a valid program frame; a 100 ms test captured the card instead. A live post-update ad frame was usable, but flashes and timing vary. The direct video-plane capture path refused a protected YouTube TV stream, so the display screenshot remains the verified source for that app. Claude classifications can miss ads or identify them late. This is a prototype, not a guarantee that every commercial will be hidden.

## Privacy and repository contents

By default, the TV deletes each PNG after submission, the host bridge removes its temporary PNG after classification, and the detector keeps only short in-memory context. Optional audit capture in `claude_bridge.py` is disabled unless you set `TV_AUDIT_DIR`. Screenshots and viewing context **are sent to Claude**. Commercial Break does not block Samsung's ACR or other tracking. Do not put `private/`, `.env`, `tv.env`, captured images/audio, or any copied Samsung library in a public commit.

The repository contains only the core commercial-break source, tests, and examples. It intentionally excludes personal recordings, proprietary TV binaries, and the separate experimental audio study. The audio study is not part of the live mute decision.

Run the included policy and bridge tests with:

```sh
python3 -m unittest -v test_server.py test_claude_bridge.py test_tv_backlight.py
```

This project builds on the independent [samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) project and Samsung's developer tools. Those dependencies are not bundled here.
