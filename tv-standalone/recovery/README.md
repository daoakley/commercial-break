# Automatic boot recovery

This signed Tizen widget restores the existing Commercial Break engine after a
full TV reboot. It does not change ad-detection thresholds, replace Samsung
applications, or install a custom launcher.

## Startup sequence

1. Tizen launches `cBRecov001.svc`, a JavaScript background service registered
   with `on-boot` and `auto-restart` enabled.
2. If recovery was armed, the service connects to the TV's SDB on localhost.
3. The archive-root integration starts an authenticated root agent. The service
   accepts it only when its reported UID, EUID, GID and EGID are all zero.
4. It verifies its own startup flags and repairs them when necessary. A backup
   precedes the scoped package-registry update.
5. If Commercial Break is not active, it copies the installed unit into
   `/run/systemd/system`, reloads systemd and starts the supervised engine.
6. If the owner enabled the optional [firmware update lock](../FIRMWARE_UPDATE_LOCK.md),
   the engine unit reapplies its runtime masks before launching the engine.
7. The engine reads the saved On/Off setting. Off remains Off.

The widget and its armed marker persist under `/opt`. Root is reacquired at
startup; it is not retained through the power loss. `/run` state is recreated.
The underlying root method must remain compatible with the installed firmware.
Host PC IP must be `127.0.0.1` for this TV-local recovery path, which prevents
the computer's usual SDB connection. The engine itself can still run when Host
PC IP points to a computer; the difference appears after a full TV reboot.

| Developer Mode Host PC IP | After a full reboot | Computer SDB access |
| --- | --- | --- |
| `127.0.0.1` | TV-local recovery can reacquire root if its service launches | Normally unavailable |
| Computer's LAN address | TV-local recovery cannot complete its SDB handshake; use [computer-assisted recovery](../RECOVERY.md#full-tv-reboot) | Available from that address |

These modes are alternatives. Changing Host PC IP is not required to repair the
engine in the current boot when the computer's developer connection still works.
Do not describe the computer-address mode as unattended TV-only recovery.

## Build and install

Use the [installation guide](../INSTALL.md). The private bundle builder compiles
the included root payload sources and signs the recovery widget with your own
certificates. No compiled Samsung libraries, device identities or certificates
are distributed.

The widget requests automatic service launch after install/boot, but that must
be verified on each device; it makes no root attempt until armed. Opening
**Commercial Break Recovery** explicitly
launches its service and closes the foreground window. The separate main
Commercial Break controller remains the On/Off interface for ad blocking.

## API

The service listens on TV TCP port **18765**. Every endpoint requires its own
random 256-bit bearer token, separate from the main engine's token. Use
`tools/recovery.py` so credentials do not appear in command arguments.

| Method/path | Behavior |
| --- | --- |
| `GET /status` | Service boot ID, root-agent state and cached engine status |
| `POST /arm` | Persist recovery intent and begin root acquisition |
| `POST /disarm` | Disable this service's boot flags and root integration; keep the current engine running |
| `POST /restore-developer-host` | Restore the computer IPv4 address supplied at build time |

There is no remote arbitrary-command endpoint. The root-agent transport binds
loopback and authenticates messages with HMAC-SHA256. The LAN API uses HTTP, so
use it only on a trusted network and never forward its port to the Internet.
Neither the API token nor a signed widget belongs in an issue or public repo.

Disarming and developer-host restoration require the root agent to be connected.
If it cannot connect, change Host PC IP back to the computer using the TV's
Developer Mode screen and restart if needed. Uninstalling the recovery widget
removes its package registration; it does not uninstall the main blocker.

## Failure behavior and limits

Root acquisition is limited to 12 attempts per service process, with increasing
retry delays. Preparation errors do not launch an incomplete payload. Recovery
status keeps at most 30 events; adapter state retains bounded attempts. Root
staging uses a distinct random directory per service process and does not remove
another tool's files. These staging directories are not currently pruned by this
component; inspect disk use during maintenance and remove only verified inactive
recovery-owned staging after disarming.

If the status endpoint is unreachable, the service may not have launched or may
have exited even when its installed `on-boot` and `auto-restart` flags are true.
Opening the **Commercial Break Recovery** widget starts the service for diagnosis, but may
briefly take foreground focus. If status then reports `sdbClosed`, the TV-local
developer handshake failed. In computer-address mode this is expected; use the
computer connection to restore the engine. A plain interactive `sdb shell`
printing `closed` is a separate retail-TV restriction and does not by itself
diagnose this service failure. The `tools/recovery.py status` summary reports
the last handshake failure and marks old engine snapshots stale rather than
presenting them as proof of current operation.

The main engine has its own [crash supervisor](../RECOVERY.md). A recovery-widget
failure does not stop an already-running engine. A full reboot still needs the
widget to start successfully and the root method to work. This is not protection
against OS-wide failure, corrupted storage or a firmware change.

Compatibility validation: QN65LS03BAFXZA, T-PTMAKUC-1720.7, Tizen 6.5. One full
power-cycle test confirmed automatic service launch, UID-0 acquisition, engine
startup at approximately 76 seconds, and subsequent captures and recognition.
This is a compatibility result, not a universal startup-time or reliability
promise. The older engine `rebootReady` field does not discover this separate
widget; use this API and a changed boot ID to validate boot recovery.

## Source provenance

`service/platform.js`, `adb.js`, `sdb.js`, `tar.js` and `root-agent.js` derive from
[Vetro](https://github.com/andrearicci93/vetro), revision
`b05a374ac8396220795fe44321d415b26718a4fa`, under [MIT](VETRO-LICENSE). This integration
removes debloat/install APIs and cross-project staging cleanup, bounds root
attempts, and omits unbounded adapter log writes.

`payload-source/` contains `SamsungTvArchiveRoot` and `SamsungTvRootAgent` from
[samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root) release 0.0.12,
under the [Unlicense](payload-source/LICENSE). The package is a standalone widget;
TizenBrew and Gaming Hub replacement are not involved.

## Tests

```sh
node tv-standalone/recovery/tests/recovery.test.cjs
```

Tests cover authentication, fixed endpoints, no root before arming, armed
startup, own-service registry changes and preservation of a running engine.
For a hardware check, record status, disconnect power for 30 seconds, restore
power, and poll status without opening either widget or issuing a root command.
Require a new boot ID, connected UID-0 agent, fresh engine process and new queries
after opening YouTube TV. Check ordinary playback, an ad cover and return to the
show separately. If the status endpoint does not appear by the expected startup
window, record that as a boot-service failure before manually opening the widget;
the manual launch must not be counted as unattended recovery.
