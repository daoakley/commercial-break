# Optional firmware update lock

Commercial Break can reapply an owner-enabled firmware update lock when its
supervised engine starts. This is separate from ad detection. It does not run on
fresh installations: the on-TV file
`/opt/usr/home/owner/commercial-block/firmware-update-lock-enabled` must exist.

The lock checks that Samsung's installer services are inactive, saves original
settings and the engine unit under
`/opt/usr/home/owner/commercial-block/backups/firmware-update-lock/`, then:

- Keeps the menu Auto Update setting off and turns off
  `db/fw-update-service/service_onoff`.
- Creates `/mnt/backup/OS_UPGRADE_FLAG`, which the installed
  `swu-auto-upgrade.service` unit checks before it starts.
- Stops and runtime-masks the automatic SWU, firmware-download and VD-system
  update timers, paths and services. It leaves `was-background-update` and
  `appbinary-manager` alone; effects on every app-update flow have not been
  tested.

The masks live in `/run` and disappear at reboot. The saved setting and flag
persist. If the optional [boot recovery widget](recovery/README.md) successfully
reacquires root and starts the engine, the engine unit reapplies the masks before
Commercial Break starts. If it cannot reacquire root, only the persistent
setting and flag remain. This is a mitigation, not a guarantee against every
vendor update path or a firmware update already in progress.

On a QN65LS03BAFXZA running `T-PTMAKUC-1720.7`, the lock was applied and
reapplied in the same boot without interrupting YouTube TV or the Commercial
Break engine. A full reboot test has not yet been performed. Do not apply the
script while `swu-core-tv.service`, `swu-service.service` or
`bootmode-system-update.service` is active; it refuses in that state.

To undo the lock, use the existing root connection and feed the saved
`backups/firmware-update-lock/unlock.sh` to `/bin/sh` through standard input.
The unlock script restores the captured settings, flag, original engine unit,
and previously active firmware services. It does not restart Commercial Break.
The source is [scripts/firmware-update-unlock.sh](scripts/firmware-update-unlock.sh).
