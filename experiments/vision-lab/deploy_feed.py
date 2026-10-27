"""Start only the bounded debug-file exporter on an already-rooted TV.

Does not enable debugging, capture frames, alter recognition, or restart the TV.
All deployment artifacts and credentials remain in the private work directory.
"""
import argparse
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import time


def stdout_fields(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'stdout' and isinstance(child, str):
                yield child
            elif isinstance(child, (dict, list)):
                yield from stdout_fields(child)
    elif isinstance(value, list):
        for child in value:
            yield from stdout_fields(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tv-host', required=True)
    parser.add_argument('--mac-host', required=True)
    parser.add_argument('--port', type=int, default=8796)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--root-tool', type=Path, required=True)
    parser.add_argument('--sdb', type=Path, required=True)
    parser.add_argument('--backfill', type=int, default=24)
    args = parser.parse_args()
    import ipaddress
    ipaddress.ip_address(args.tv_host)
    ipaddress.ip_address(args.mac_host)
    if not 0 <= args.backfill <= 256:
        raise ValueError('backfill must be 0..256')

    def root(command):
        result = subprocess.run([str(args.root_tool.resolve()), '--sdb', str(args.sdb.resolve()),
            '-o', 'json', 'archive-root', 'root', args.tv_host, '--command', command,
            '--command-timeout', '12'], capture_output=True, timeout=60)
        return '\n'.join(stdout_fields(json.loads(result.stdout)))

    status = root('curl --fail --silent --max-time 3 --config /opt/usr/home/owner/commercial-block/control.curl http://127.0.0.1:18764/status')
    status = json.loads(status)
    debug = status.get('debug', {})
    if debug.get('enabled') is not True or not debug.get('expiresAt'):
        raise RuntimeError('Debug recording is off; exporter not started. Enable the existing TV debug switch first.')
    expiry = int(debug['expiresAt']//1000)
    if expiry <= time.time():
        raise RuntimeError('Debug session expired')
    private = args.work.resolve()
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    archive = private/'tv-export.tar'
    entries = {
        'tv-debug-export.sh': Path(__file__).with_name('tv-debug-export.sh').read_bytes(),
        'upload.curl': (private/'upload.curl').read_bytes(),
        'destination': f'http://{args.mac_host}:{args.port}'.encode(),
        'expires': str(expiry).encode()}
    with tarfile.open(archive, 'w') as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
    archive.chmod(0o600)
    remote = '/home/owner/share/tmp/sdk_tools/commercial-vision-export.tar'
    pushed = subprocess.run([str(args.sdb.resolve()), '-s', args.tv_host+':26101',
                             'push', str(archive), remote], capture_output=True, timeout=25)
    if pushed.returncode:
        raise RuntimeError('Could not stage private exporter')
    # Lock is owned by the exporter; never delete another active launch's lock.
    command = f'''umask 077
target=/run/commercial-vision-export
if [ -d "$target/lock" ]; then rm -f {shlex.quote(remote)}; echo ALREADY_RUNNING; exit 0; fi
mkdir -p "$target"
chmod 700 "$target"
tar -xf {shlex.quote(remote)} -C "$target"
rm -f {shlex.quote(remote)} "$target/stop"
ls /opt/usr/home/owner/commercial-block/debug-records/*.json 2>/dev/null | sort | tail -n {args.backfill+1} | head -n 1 | sed 's|.*/||' > "$target/start-after"
nohup /bin/sh -c "$(cat "$target/tv-debug-export.sh")" > "$target/export.log" 2>&1 < /dev/null &
echo EXPORTER_STARTED
'''
    try:
        output = root(command)
    except (ValueError, subprocess.TimeoutExpired):
        # The root transport can lose its final response after a successful
        # detached launch. Confirm the receiver rather than launch a duplicate.
        try:
            feed = json.loads((private/'feed-status.json').read_text())
            confirmed = time.time()-float(feed['last_state_unix']) < 10
        except (OSError, ValueError, KeyError):
            confirmed = False
        output = 'EXPORTER_STARTED' if confirmed else ''
    print(json.dumps({'result': 'started' if 'EXPORTER_STARTED' in output else
                      'already_running' if 'ALREADY_RUNNING' in output else 'unconfirmed',
                      'expires_unix': expiry, 'backfill_max': args.backfill,
                      'capture_changes': False, 'blocker_changes': False}))


if __name__ == '__main__':
    main()
