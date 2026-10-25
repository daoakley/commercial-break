# Commercial Break

**Handoff status (24 October 2026):** ad-onset delay remains unresolved. The development source differs from the live detector, and the earlier fast-display trial remains suspended. Start with [current status](docs/PROJECT_STATUS.md), [architecture](docs/ARCHITECTURE.md), [operations/dashboard](docs/OPERATIONS.md), [research](docs/RESEARCH.md), and [Claude handoff](docs/CLAUDE_HANDOFF.md). The verified deployed detector source is preserved under [reference](reference/deployed-2026-10-24/). PR #5 is a draft; this is not a validated release.

Commercial Break is an experimental commercial muter for a Samsung Frame TV. A temporary TV-side helper captures a 480×270 screenshot of the active display and sends it to a detector on your computer. The detector asks a Claude Code vision bridge whether the frame shows a commercial. On a confirmed ad, the TV helper mutes the speakers, lowers the active backlight, and displays an opaque “Commercial Break” card. Playback continues underneath. It restores sound and brightness when program content returns.

For YouTube TV, the detector first checks the app's fixed upper-left **Sponsored** pill locally. A strong match mutes on that frame without waiting for Claude; frames without the pill follow the normal vision path. This template is specific to 480×270 captures from the tested YouTube TV app. In 1,589 saved frames from the owner's TV, it matched 68: 66 classified ads and two frames initially classified as program that visibly showed the pill over a political ad. Badge detection cannot shorten the wait until the TV takes its next screenshot.

This repository shares **source and reproduction steps**, not an installable Samsung app. The tested path needs temporary root access. The TV-side components are staged manually and disappear or stop after a reboot. Nothing here disables Samsung tracking.

The card can also display the current viewing context, elapsed detected-break time, learned timing and a bounded program/ad/coverage timeline. Inferred titles are labeled; unknown values stay unknown. See [Information card](docs/OVERLAY_INFORMATION.md).

For the asynchronous fast path, context model, navigation reset and measured limits, see [Detection design](docs/DETECTION_DESIGN.md). The sequential endpoint remains the default for first-time setup. Also see [the Astra handoff](docs/ASTRA_HANDOFF.md) and the [issue tracker](https://github.com/daoakley/commercial-break/issues).

**Experimental fast-path trial suspended:** the owner reported a repeated
black-screen/program-image loop despite UNMUTE decisions. Keep fast,
persistent-capture and warm-overlay modes disabled until the display-side
regression is isolated. The draft documents both the timing gains and this
failure; it is not a validated release.

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
dotnet build tv-navigation/NavigationObserver.csproj -c Release
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

On the tested TV, the original library is `/usr/lib/libtzcapturec.so`. Copy it to the developer-writable staging area using the authenticated temporary root route, transfer it to a **Git-ignored** local `private/` directory, and remove the staging copy. The generic example below uses `sdb pull`; this failed on the owner's retail set. Their working fallback was a bounded read through the established root command path. Do not treat a failed pull as failed root, and never print a library or token into a public transcript:

```sh
mkdir -p private
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'mkdir -p /home/owner/share/tmp/sdk_tools; cp /usr/lib/libtzcapturec.so /home/owner/share/tmp/sdk_tools/libtzcapturec-original.so; chmod 644 /home/owner/share/tmp/sdk_tools/libtzcapturec-original.so'
"$SDB" pull "$STAGE/libtzcapturec-original.so" private/libtzcapturec-original.so
"$TVROOT" --sdb "$SDB" archive-root root "$TV_IP" --command 'rm -f /home/owner/share/tmp/sdk_tools/libtzcapturec-original.so'
python3 patch-local-library.py private/libtzcapturec-original.so private/libtzcapturec-probe.so
```

The patch succeeds only if the original library matches the tested `T-PTMAKUC-1720.7` SHA-256. Do not publish either library. On another firmware, inspect and validate the capture path independently before adapting it. A successful root probe alone does not establish capture compatibility.

## 4. Stage and start the TV helper

Push the shell files, built .NET files, card scene, private TV settings, and temporary library. The staging path below is the one verified on the tested Frame:

```sh
for name in tv-agent.sh tv-watchdog.sh tv-backlight.sh tv-overlay.sh tv-capture.sh; do
  "$SDB" push "$name" "$STAGE/$name"
done
"$SDB" push tv-probe/bin/Release/netcoreapp3.1/DisplayCaptureProbe.dll "$STAGE/DisplayCaptureProbe.dll"
"$SDB" push tv-probe/bin/Release/netcoreapp3.1/DisplayCaptureProbe.runtimeconfig.json "$STAGE/DisplayCaptureProbe.runtimeconfig.json"
"$SDB" push tv-navigation/bin/Release/netcoreapp3.1/NavigationObserver.dll "$STAGE/NavigationObserver.dll"
"$SDB" push tv-navigation/bin/Release/netcoreapp3.1/NavigationObserver.runtimeconfig.json "$STAGE/NavigationObserver.runtimeconfig.json"
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

The following policy describes the deployed reference. Root development source has pending differences listed in [current status](docs/PROJECT_STATUS.md); its shorter idle delay has not been live-validated.

The detector tracks recent program and ad observations in memory. A matched YouTube TV Sponsored pill mutes on one frame. Without the pill, a model-labeled ad at confidence 0.85 or higher can mute on one frame when a program is established, including after uncertain cutaway frames; otherwise it waits for two distinct ad frames. The prompt requires promotional evidence in the current frame: a change from the previously known show is not itself an ad. It does not use a generic banner detector. Uncertain frames request another capture after 2 seconds. During a confirmed break it waits 8 seconds after each response before another screenshot. Two moderate-confidence frames identifying a coherent new program release the cover and reset the learned break cadence; one strong new-program frame can release it while muted. The return may therefore remain covered for several seconds, plus model processing time. Break timing can increase screenshot frequency before an ad but never orders a mute on its own. The TV helper reads Tizen's current foreground app ID for each frame, failing open if that read is unavailable. A changed channel/title also resets the detector when supplied, but this project has not found a reliable live YouTube TV channel/title feed on this Frame. A native Media Controller client returned `-38` when created in a temporary root shell, so that probe supplied no now-playing data.

An observed program counts as established even if the model cannot give it a title. The detector logs the ad/program label, confidence, program-change flag, and classification time, without logging the screenshot or viewing description. These fields help separate a slow model response from a policy decision when coverage is late.

On 24 October, a saved high-confidence game-trailer ad was labeled `ad` at 0.96 but also had `program_changed=true`, blocking the one-frame mute. The prompt now reserves that flag for `program` frames. In a small offline check, that ad remained `ad` with the flag cleared; a saved show-change frame remained `program` with the flag set. A saved screenshot of this project's own cover card had previously been labeled an ad; the prompt now identifies it as an obscured frame, and the same offline check returned `uncertain`. This is a targeted correction, not evidence of low false-mute rates or a fixed capture handshake.

In one owner's 3,713 recorded model verdicts, replaying this revised decision rule produced 14 earlier mute starts and no new isolated mutes compared with the previous rule. The verdicts are not independent ground truth, and prompt changes can alter future verdicts; live false-alarm and onset timing still need measurement.

If capture, the network, Docker, or the model fails, the helper releases the mute and active backlight change **that it owns**. The card has a renewable lease and disappears if the helper stops renewing it. A watchdog retries restoration after an unexpected helper stop. The viewer can always use the remote. The helper never pauses playback or changes channels. Test all of these behaviors before extended use on another TV.

The card covers the display screenshot, so it briefly clears for each capture and then returns. The TV helper restores the card about 225 ms after starting native capture, while the PNG finishes writing. An isolated 200 ms test measured about 0.30 seconds uncovered and saved a valid program frame; a 100 ms test captured the card instead. A live post-update ad frame was usable. The optional `PANEL_MASK_ON_CAPTURE=1` setting uses the TV's **LFD panel-mute control** to turn the physical screen fully black while the card is hidden for a capture during a confirmed ad. The internal screenshot remains clear. On the tested 2022 Frame, the owner confirmed the screen was fully black in a reversible 30-second trial; a separate brief test captured a readable internal 480×270 screenshot under LFD mute and panel mute returned to off. The updated capture helper also passed an isolated handshake test with about 259 ms card-hidden and 924 ms panel-muted. It waits for the physical panel to blank before hiding the card, then waits after the card returns before unmuting the panel. A separate four-second rescue unmutes the panel if capture exits abruptly. `PANEL_MASK_ON_CAPTURE=0` is the default. This setting must be re-enabled when the temporary TV agent is started after a reboot. It does not prevent an ad from being seen before the first detection.

Active backlight at 0/50 was tested first but left the image clearly visible, so it is no longer used as the capture mask. During the first live covered break with the LFD helper, panel mute was observed engaging during capture. The subsequent program decision removed the card and restored panel mute off and active brightness to 38/50. A room-side check for any remaining visible ad fragment is still pending. A blur or noise overlay would appear in the captured image as well and cannot be reliably removed from the screenshot. The direct video-plane capture path refused a protected YouTube TV stream, so the display screenshot remains the verified source for that app. Claude classifications can miss ads or identify them late. This is a prototype, not a guarantee that every commercial will be hidden.

## Privacy and repository contents

By default, the TV deletes each PNG after submission, the host bridge removes its temporary PNG after classification, and the detector keeps only short in-memory context. Optional audit capture in `claude_bridge.py` is disabled unless you set `TV_AUDIT_DIR`. Screenshots and viewing context **are sent to Claude**. Commercial Break does not block Samsung's ACR or other tracking. Do not put `private/`, `.env`, `tv.env`, captured images/audio, or any copied Samsung library in a public commit.

The repository contains core source, tests, the portable local dashboard, deployed-reference source, and observation-only audio research tools. It excludes personal recordings, credentials and proprietary TV binaries. Audio is not part of the live mute decision.

Run the included policy and bridge tests with:

```sh
python3 -m unittest -v test_server.py test_claude_bridge.py test_tv_backlight.py
```

This project builds on the independent [samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) project and Samsung's developer tools. Those dependencies are not bundled here.
