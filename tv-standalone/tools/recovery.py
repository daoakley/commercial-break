#!/usr/bin/env python3
"""Authenticated fixed recovery controls; never prints tokens or sends arbitrary commands."""
import argparse
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path


def summarize_status(data, now=None):
    """Report current proof of recovery without exposing raw device event messages."""
    now = time.time() if now is None else now
    state = data['state']
    platform = data['platform']
    agent = platform.get('agent') or {}
    attempts = platform.get('attempts') or []
    last_attempt = attempts[-1] if attempts else {}
    failure = last_attempt.get('connect', '')
    if failure.startswith('fail:'):
        failure = failure[5:]
    else:
        failure = None

    cached = state.get('engine') or {}
    snapshot_at = cached.get('at')
    raw_age = (now - snapshot_at / 1000
               if isinstance(snapshot_at, (int, float)) and not isinstance(snapshot_at, bool)
               else None)
    snapshot_age = (round(raw_age) if raw_age is not None and
                    math.isfinite(raw_age) and raw_age >= 0 else None)
    fresh = snapshot_age is not None and snapshot_age <= 45
    report = cached.get('report', '')
    engine = None
    if report:
        try:
            engine = json.loads(report.splitlines()[-1])
        except (ValueError, TypeError):
            pass
    service_active = ('ActiveState=active' in report and
                      'SubState=running' in report)
    root_connected = agent.get('connected') is True and agent.get('uid') == 0
    verified = root_connected and fresh

    if not state.get('armed'):
        diagnosis = 'Recovery is disarmed.'
    elif failure == 'sdbClosed' and not root_connected:
        diagnosis = ('TV-local developer connection closed. Automatic TV-only recovery '
                     'requires Developer Mode Host PC IP 127.0.0.1. If it is set to a '
                     'computer address, use the documented computer-assisted recovery.')
    elif not root_connected:
        diagnosis = 'Root agent is not connected; inspect recovery attempts.'
    elif not fresh or not service_active or not engine:
        diagnosis = 'No fresh proof that the engine is running.'
    elif engine.get('enabled') is False:
        diagnosis = 'Engine is running; blocking is switched Off.'
    else:
        diagnosis = 'Engine is running; compare checks across two status reads to verify progress.'

    return {
        'version': state.get('version'),
        'bootId': state.get('bootId'),
        'armed': state.get('armed'),
        'servicePid': state.get('pid'),
        'serviceStartedAt': state.get('startedAt'),
        'rootConnected': root_connected,
        'rootUid': agent.get('uid'),
        'rootAttempts': len(attempts),
        'lastRootFailure': failure,
        'engineServiceActive': service_active if verified else None,
        'engineSnapshotAgeSeconds': snapshot_age,
        'engineFresh': verified,
        'engine': None if not engine or not verified else {
            k: engine.get(k) for k in
            ['health', 'enabled', 'queries', 'matches', 'localChecks', 'message', 'lastError']
        },
        'events': [{'at': e.get('at'), 'kind': e.get('kind')}
                   for e in state.get('events', []) if isinstance(e, dict)],
        'diagnosis': diagnosis,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('action', choices=['status', 'arm', 'disarm', 'restore-developer-host'])
    args = parser.parse_args()
    if any(c not in '0123456789.' for c in args.host):
        parser.error('Use the TV IPv4 address')
    request = urllib.request.Request(
        'http://' + args.host + ':18765/' + args.action,
        method='GET' if args.action == 'status' else 'POST',
        headers={'Authorization': 'Bearer ' + args.token_file.read_text().strip()},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError) as error:
        raise SystemExit('Recovery endpoint unavailable: ' + str(error))
    print(json.dumps(summarize_status(data) if args.action == 'status' else data, indent=2))


if __name__ == '__main__':
    main()
