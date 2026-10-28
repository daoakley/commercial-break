# Crash diagnostics and automatic recovery

The TV engine is supervised locally by a runtime systemd service. No computer or LLM is involved in engine health checks or process recovery.
The optional boot-recovery widget has its own authenticated LAN endpoint. Samsung
recognition still requires its existing network service.

## What recovers

- A process exit (including SIGKILL) is recorded by a separate shell supervisor.
- A detection loop that stops making progress for 45 seconds is killed and
  restarted. The heartbeat uses `/proc/uptime`, so a wall-clock correction does
  not trigger a false stall. Off, Art Mode, waiting for YouTube TV and recognition
  retry delays all continue producing health pulses.
- A faulted or unexpectedly completed permanent background task now terminates
  the engine instead of silently leaving the controller showing On.
- Five consecutive recognition exceptions recycle the engine. An ordinary
  uncertain recognition result is not a failure and never triggers recovery.
- The system service restarts the supervisor itself if it exits. Its control
  group contains the engine and helpers, so restart removes orphan capture,
  renderer, navigation and classifier processes.

The restart preserves the saved On/Off setting, appearance, layout toggle and
original debug deadline. Turning blocking Off leaves a healthy controller
service running; recovery does not turn blocking back On. Missing or corrupt
On/Off data defaults to Off. Another active blocker still takes precedence.

The service waits five seconds between attempts. Repeated starts less than two
minutes apart add a 4, 8, 16, 32, then maximum 60-second cooldown. Retries continue
instead of permanently abandoning recovery. Normal detection timing and match
thresholds are unchanged.

## Playback safety

The existing independent eight-second cover lease remains. On service shutdown,
systemd stops the entire process group, then runs `release-owned.sh` to remove
our lease, undo only our owned speaker mute, and release a physical-panel mask
only when our capture helper recorded ownership. The capture helper also keeps
its existing four-second rescue process during normal operation. Cleanup is
retried before the next engine start. User brightness is not changed.

This is fail-open behavior: when the engine fails, programming remains visible
and audible once owned controls are released, although ads may play until
recovery. A failed TV control API or an OS-wide hang can still prevent cleanup.

## Private diagnostics

Files on the TV:

- `/opt/usr/home/owner/commercial-block/diagnostics/engine.jsonl`: startup and
  exception type, stage and up to eight method names. Exception messages and
  source paths are deliberately excluded.
- `/opt/usr/home/owner/commercial-block/diagnostics/recovery.jsonl`: process
  starts/exits, exit status, stalls, cooldown and available memory/swap counts.
- Each log rotates at approximately 64 KiB with two older copies: approximately
  384 KiB total, plus at most one bounded record per file. Directory permissions
  are 0700; the service uses umask 0077.
- `/run/commercial-block/supervisor.json`: current supervisor/engine PIDs,
  start count, stall deadline and current restart delay.
- `/run/commercial-block/engine-health`: PID and last loop progress in uptime
  seconds. Runtime state disappears on reboot.

These logs contain no images, fingerprints, Samsung responses, authentication
values, viewing titles or device identity. They are separate from 48-hour debug
recordings; debug expiry/deletion behavior is unchanged. Logs remain as a bounded
rolling history when debug recording stops. Do not publish raw device logs.
An exit status of 137 indicates a kill signal; it is not by itself proof of OOM.

The authenticated `/status` response adds `health` with current engine PID,
start time, loop progress and supervisor information. `systemctl show
commercial-break-engine.service` reports service state and restart count.

## Deployment on an already provisioned compatible TV

Back up the current engine and capture helper, preserve configuration/settings,
and build both projects. This update requires the coordinated capture helper
because it adds the panel-mask ownership marker used by service cleanup.

Copy `CommercialBlock.dll`, `AcrFrameProbe.dll`, `scripts/engine-supervisor.sh`,
`scripts/release-owned.sh` and `scripts/commercial-break-engine.service` into
`/opt/usr/home/owner/commercial-block`. Stop the old manually launched engine,
allow its existing fail-safe to release, and remove only its orphan helpers.
Never start this service alongside an existing unmanaged engine. Do not toggle
Off merely to deploy: Off intentionally clears debug recording.

With the already-authorized temporary root shell:

```sh
cp /opt/usr/home/owner/commercial-block/commercial-break-engine.service /run/systemd/system/
systemctl daemon-reload
systemctl start commercial-break-engine.service
systemctl show commercial-break-engine.service -p ActiveState -p SubState -p MainPID -p NRestarts
```

The service reads shell scripts through stdin because the tested retail firmware
rejects unsigned script filenames even when passed to `/bin/sh`. This does not
obtain root; provisioning must already have provided it. Never put secrets in
unit arguments or command output.

For rollback, stop the service first (which releases owned controls), restore
both backed-up DLLs, remove the runtime unit and reload systemd. Then use the
previous documented launch procedure and explicitly restore the previous
On/Off choice; older engines reset it during startup.

The runtime unit disappears at reboot. The optional
[boot-recovery widget](recovery/README.md) reacquires root, recreates the unit and
starts the engine automatically. Without that widget, the engine still needs a
privileged restart after a full boot.

## Validation

```sh
dotnet run --project tv-standalone/tests/health/HealthTests.csproj
python3 tv-standalone/tests/test_supervisor.py  # Linux, Python 3 and flock
```

Health tests exercise saved-state handling, payload exclusion, rotation and
unwritable-log behavior. Supervisor tests use real disposable child processes
to exercise process exit, stalled/mismatched heartbeat, healthy loop, duplicate
supervisor rejection, SIGKILL reporting and restart cooldown. Existing verdict,
Sponsored-pill and layout-evidence tests must also pass. Live TV validation must
check fresh recognition after restart and unchanged saved settings; off-device
tests alone do not prove native API access from a system service.

### Validated target behavior

On QN65LS03BAFXZA / T-PTMAKUC-1720.7, the service performs native captures and
recognition, preserves saved settings, and replaces a SIGKILLed engine in about
five seconds. With the separate recovery widget, one full power-cycle test also
confirmed unattended root reacquisition, engine startup and subsequent captures
and recognition. Compatibility and timing on other firmware remain unverified.
