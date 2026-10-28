# Install Commercial Break on a compatible Samsung TV

This is an advanced, owner-provisioned installation. The verified target is the
2022 Frame QN65LS03BAFXZA, T-PTMAKUC-1720.7, Tizen 6.5, ARMv7 with .NET Core 3.1.
Native capture, fingerprint and panel-control interfaces are firmware-specific.
The capture-library patch refuses any library whose hash differs from the tested
version. Do not bypass that check to install on another firmware.

## Required inputs

- Temporary root access using [samsung-tv-root](https://github.com/chris-ritsen/samsung-tv-root).
  Follow its compatibility and installation instructions first.
- SDB/Tizen CLI from Tizen Studio and a certificate profile permitted to install
  on your TV. Keep your existing author certificate for later widget updates.
- Python 3.9+, Node.js for tests, and a .NET SDK able to build `netcoreapp3.1`
  projects. The source has been built with SDK 6.0.428. Targeting references must
  be available locally or downloadable during restore.
- Your TV's unmodified `libtzcapturec.so`, obtained through authorized root access.
  The engine loads a patched copy; the installed Samsung library stays unchanged.
- Your own Samsung ACR identity and parameter-request fields in a private JSON
  file; see [configuration](CONFIGURATION.md). These are mandatory inputs, not
  credentials supplied by this repository. Obtaining them on a new TV is not
  automated by this build tool. Stop here if they are unavailable.

The source currently uses the US Samsung recognition endpoint. Other regions
and firmware have not been validated. A certificate alone does not grant the
engine's capture privileges. Recognition sends fingerprints and device metadata
to Samsung; do not use the recognition path if that is unacceptable to you.

## 1. Prepare private inputs

From the repository root:

```sh
python3 -m venv private/build-venv
private/build-venv/bin/pip install -r tv-standalone/tools/requirements.txt
cp tv-standalone/device.example.json private/device.json
```

Replace every placeholder with values from your own TV. The builder generates a
control token if it is absent. For updates, use the exact installed `device.json`
including its existing token. Copying somebody else's identity is not supported.

Create a private certificate directory containing `author.p12`,
`distributor.p12` and `password.txt`. Both PKCS#12 files must use the same export
password, read from `password.txt`; the signer does not print it. Restrict this
directory and the build output to your user. Certificates are read, not copied
into either widget. Generated widgets still contain control tokens and are
private installation artifacts.

Record the computer's current **Host PC IP** from the TV Developer Mode screen.
You will supply it as `--restore-host`. Keep the TV pointing at the computer until
both widgets and the engine are installed and checked.

## 2. Build a private deployment bundle

Replace the paths and example computer address below:

```sh
private/build-venv/bin/python tv-standalone/tools/build.py \
  --device-config private/device.json \
  --capture-library private/libtzcapturec.so \
  --cert-dir private/certificates \
  --restore-host 192.0.2.2 \
  --out private/tv-build
```

Use `--dotnet /path/to/dotnet` if the SDK is not on PATH. The tool compiles the
engine, capture, overlay, navigation and root-recovery payloads, validates the
capture-library hash, creates matching private controller configuration and
signs both widgets. It makes no TV connection. It refuses an existing output
folder so credentials and backups cannot be silently replaced.

Outputs:

| File | Purpose |
| --- | --- |
| `engine.tar.gz` | Managed helpers, runtime configuration, themes, private device configuration and TV-sourced library copy |
| `commercial-break.wgt` | Signed On/Off/debug/theme controller |
| `commercial-break-recovery.wgt` | Signed background startup component |
| `recovery-token` | Authentication for recovery API controls |
| `install-engine.sh` | TV-side deployment of the staged engine bundle |

Keep the entire output private. For another build/update, retain
`engine/device.json`, the recovery token, your signing identity and the previous
bundle. Recovery token rotation requires updating its widget and any clients
together; a newly built recovery widget gets a new token.

## 3. Install and check the engine

With the TV still authorizing your computer's SDB connection:

```sh
sdb connect TV_IP:26101
sdb -s TV_IP:26101 push private/tv-build/engine.tar.gz \
  /home/owner/share/tmp/sdk_tools/commercial-break-engine.tar.gz
sdb -s TV_IP:26101 push private/tv-build/install-engine.sh \
  /home/owner/share/tmp/sdk_tools/commercial-break-install.sh
```

Through your already-working **TV root command channel**, run:

```sh
cat /home/owner/share/tmp/sdk_tools/commercial-break-install.sh | /bin/sh
```

This command is run on the TV, not directly in your computer terminal. Ordinary
retail `sdb shell` is not a root shell. Use the root tool's documented command
execution facility. The script validates required bundle files, refuses a
conflicting unmanaged engine or changed device configuration, backs up existing
files and installs the runtime systemd service. Saved On/Off, theme, layout and
debug state are preserved. A fresh installation defaults to Off.

Install both signed widgets using your Tizen target name:

```sh
tizen install -n commercial-break.wgt -t TV_TARGET -- private/tv-build
tizen install -n commercial-break-recovery.wgt -t TV_TARGET -- private/tv-build
```

Open **Commercial Break**, turn it on, then return to YouTube TV. Verify fresh
recognition checks, a covered ad and normal return to the show before enabling
reboot recovery. The computer-assisted blocker must be stopped to avoid two
systems controlling the TV. The optional layout detector remains off without a
separately validated local model.

## 4. Enable reboot recovery

Open **Commercial Break Recovery** once. It starts its background service and
closes. From the computer, verify the protected endpoint:

```sh
python3 tv-standalone/tools/recovery.py --host TV_IP \
  --token-file private/tv-build/recovery-token status
python3 tv-standalone/tools/recovery.py --host TV_IP \
  --token-file private/tv-build/recovery-token arm
```

Before changing Host PC IP, verify the service's `app_onboot` and
`app_autorestart` flags while your computer root channel is available.
`config.xml` requests them, but some Samsung installers ignore them. If either
flag is false, back up the registry and update only this service:

```sh
# TV root shell only. Back up the registry before changing it.
sqlite3 /opt/dbspace/.pkgmgr_parser.db ".backup '/opt/usr/home/owner/commercial-block/backups/boot-registry.sqlite'"
sqlite3 /opt/dbspace/.pkgmgr_parser.db "BEGIN IMMEDIATE; UPDATE package_app_info SET app_onboot='true',app_autorestart='true' WHERE app_id='cBRecov001.svc' AND package='cBRecov001'; COMMIT;"
sqlite3 /opt/dbspace/.pkgmgr_parser.db "SELECT app_id,app_onboot,app_autorestart FROM package_app_info WHERE app_id='cBRecov001.svc';"
```

Then set the TV Developer Mode **Host PC IP to `127.0.0.1`**. The background
service connects to the TV's own SDB and reacquires root. Some firmware requires
a restart for the host change to take effect. Normal computer SDB access stops;
the protected recovery endpoint is independent of that connection. Require
`rootConnected: true` and fresh engine status before declaring setup successful.
On subsequent launches, the connected agent verifies and repairs its own flags.

If recovery cannot connect, restore the computer Host PC IP through Developer
Mode and restart if needed. Do not restore an entire old package database over
other subsequent app installs.

## 5. Verify an unattended restart

Record `status`, disconnect TV power for 30 seconds, restore power and turn on
the TV. Do not open either Commercial Break widget or run a computer-side root
command. Allow up to 90 seconds for startup, then read `status` again. Verify:

- A different boot ID and a connected UID-0 agent.
- A fresh engine PID with the saved On/Off choice.
- Increasing queries after opening YouTube TV, normal playback, ad coverage and
  return to programming.

A launcher PID or an installed app icon alone does not establish recovery.

## Updating, disabling and removal

Use the same signing identity and installed device configuration for updates.
The installer preserves settings and saves a backup under
`/opt/usr/home/owner/commercial-block/backups/`. Build both controller and engine
from the same revision. Keep private rollback bundles outside Git.

To disable ad blocking, use the main app's Off control. To disable automatic root
recovery, use `recovery.py disarm`. To regain computer SDB, call
`recovery.py restore-developer-host` **before** disarming, or use Developer Mode
manually. If necessary, restart for the developer-host change to take effect.

For removal, first turn blocking Off, restore computer developer access and
disarm recovery. Through authorized root, stop `commercial-break-engine.service`
and remove its runtime unit; reload systemd. Uninstall only packages `nCBlkTv001`
and `cBRecov001`. Remove the dedicated engine/state/diagnostic directories only
after confirming their processes are stopped. Do not delete Samsung packages or
restore whole system databases as an uninstall method.
