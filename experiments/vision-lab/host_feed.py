"""TV debug export -> local lab, with one existing dashboard metadata subscriber.

Never captures, pairs with YouTube, or writes TV controls. Receives existing
debug PNG/JSON pairs; credentials stay in files, not process arguments.
"""
import argparse
import base64
from collections import deque
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
import time
import urllib.request

MAX_BODY = 7 * 1024 * 1024


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, separators=(',', ':')))
    temp.chmod(0o600)
    temp.replace(path)


def normalize_state(source, status, guard, now):
    observed = number(source.get('observed_unix'))
    if observed is None or abs(now-observed) > 10:
        raise ValueError('stale_source')
    app = source.get('source_app')
    if not isinstance(app, str) or not app or len(app) > 150:
        raise ValueError('invalid_app')
    generation, navigation = source.get('generation'), source.get('navigation_epoch')
    if (not isinstance(generation, (str, int)) or isinstance(generation, bool) or
            not str(generation) or len(str(generation)) > 160 or
            not isinstance(navigation, int) or isinstance(navigation, bool) or navigation < 0):
        raise ValueError('invalid_source_session')
    mode = guard.get('guard', {}).get('artMode')
    return {'observed_unix': observed, 'received_unix': now,
            'source_app': app, 'generation': generation,
            'navigation_epoch': navigation,
            'enabled': status.get('enabled') is True,
            'art_mode': True if mode == 'on' else False if mode == 'off' else None,
            'covered': status.get('covered') is True,
            'debug': {key: status.get('debug', {}).get(key) for key in
                      ('enabled', 'startedAt', 'expiresAt', 'records', 'bytes')},
            'provenance': 'TV foreground app, navigation observer and engine lifetime; Frame Home Art guard'}


def source_binding(source):
    session = hashlib.sha256(json.dumps([source['generation'], source['source_app']],
                                       separators=(',', ':')).encode()).hexdigest()[:12]
    return hashlib.sha256(json.dumps((session, source['navigation_epoch']),
                                    separators=(',', ':')).encode()).hexdigest()[:12]


def aligned_source(source_history, capture_seconds, app, navigation):
    """Bracket capture by source observations from the same engine instance.

    TV debug engineGeneration is a different counter from the process lifetime;
    never compare those two values. Missing brackets mean no native enrichment.
    """
    preceding = following = None
    for source in source_history:
        observed = number(source.get('observed_unix'))
        if observed is None:
            continue
        if observed <= capture_seconds and capture_seconds-observed <= 5:
            preceding = source
        if observed >= capture_seconds and observed-capture_seconds <= 10:
            following = source
            break
    if preceding is None or following is None:
        return None
    if any(s.get('source_app') != app or number(s.get('navigation_epoch')) != number(navigation)
           or s.get('art_mode') is not False for s in (preceding, following)):
        return None
    return source_binding(preceding) if source_binding(preceding) == source_binding(following) else None


def aligned_native(history, capture_seconds, app, navigation, expected_reference=None):
    """Do not attach today's metadata to historical frames or a new channel."""
    for observed, snapshot in reversed(history):
        if observed > capture_seconds:
            continue
        if capture_seconds-observed > 5:
            break
        ident = snapshot.get('identity', {})
        native = snapshot.get('native', {})
        event = number(native.get('event_observed_unix'))
        if (ident.get('source_app') == app and number(ident.get('epoch')) == number(navigation)
                and (expected_reference is None or ident.get('session_reference') == expected_reference)
                and native.get('usable') is True and event is not None
                and event <= capture_seconds):
            return snapshot
    return {'native': {'usable': False, 'reason': 'No fresh, same-session native observation preceding capture'},
            'context': {name: {'value': None, 'provenance': 'unavailable'}
                        for name in ('show', 'channel', 'category', 'show_started_unix')}}


def frame_payload(record, png, history, now, source_history=None):
    if record.get('schema') != 'commercial-break-debug/1':
        raise ValueError('unsupported_record')
    expiry = number(record.get('sessionExpiresAt'))
    if expiry is None or expiry/1000 <= now:
        raise ValueError('expired_record')
    evidence = record.get('evidence', {})
    capture = evidence.get('capture', {})
    stamp = number(capture.get('captureStartedAt'))
    if stamp is None or stamp/1000 > now+5 or now-stamp/1000 > 48*3600:
        raise ValueError('invalid_capture_time')
    if not png.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('not_png')
    before = evidence.get('contextBefore', {})
    session = before.get('session', {})
    app = before.get('foregroundApp', {}).get('value')
    nav = session.get('navigationGeneration')
    generation = session.get('engineGeneration')
    mode = capture.get('mode')
    same_session = evidence.get('decision', {}).get('sameSession') is True
    contaminated = mode == 'card-visible' or not same_session
    clean = mode in ('normal', 'masked', 'masked-fallback', 'panel-masked') and same_session
    status = 'contaminated' if contaminated else 'clean' if clean else 'unknown'
    expected = aligned_source(source_history or [], stamp/1000, app, nav)
    native = aligned_native(history if expected else [], stamp/1000, app, nav, expected)
    scope = [record.get('sessionId'), app, nav, generation,
             native.get('identity', {}).get('content_reference')]
    sid = hashlib.sha256(json.dumps(scope).encode()).hexdigest()[:24]
    return {'image_base64': base64.b64encode(png).decode(),
            'timestamp': datetime.fromtimestamp(stamp/1000, timezone.utc).isoformat(),
            'session_id': sid, 'source': app or 'unknown',
            'ui_profile': 'youtube_tv_480x270' if app == 'com.samsung.tv.cobalt-yttv' else None,
            'contamination': {'status': status, 'reasons': [] if clean else
                              ['card-visible, session changed, or unverified capture mode']},
            'metadata': {'capture_id': record.get('captureId'),
                         'debug_session_id': record.get('sessionId'),
                         'session_expires_unix': expiry/1000,
                         'tv_debug': record, 'native_metadata': native,
                         'label_provenance': 'unlabeled; Samsung verdict is comparison evidence, not human truth',
                         'ingested_unix': now}}


class Feed:
    def __init__(self, args):
        self.args = args
        self.token = args.token_file.read_text().strip()
        self.lab_token = args.lab_token_file.read_text().strip()
        if min(len(self.token), len(self.lab_token)) < 24:
            raise ValueError('tokens_too_short')
        self.lock = threading.RLock()
        self.history = deque(maxlen=180)
        self.source_history = deque(maxlen=180)
        self.seen = set()
        self.debug_active = False
        self.deadline = None
        self.debug_start = None
        self.clear_pending = False
        self.stats = {'accepted': 0, 'duplicates': 0, 'errors': 0,
                      'mode': 'observation-only', 'last_frame_unix': None}

    def lab(self, route, data):
        request = urllib.request.Request(self.args.lab_url+route,
            data=json.dumps(data).encode(), headers={'Authorization': 'Bearer '+self.lab_token,
                                                    'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)

    def state(self, parts):
        now = time.time()
        source, status, guard = (json.loads(parts[key]) for key in ('source', 'status', 'guard'))
        normalized = normalize_state(source, status, guard, now)
        debug = normalized['debug']
        enabled = debug.get('enabled') is True
        expiry = number(debug.get('expiresAt'))
        start = number(debug.get('startedAt'))
        with self.lock:
            if not enabled or (self.debug_start is not None and start != self.debug_start):
                self.clear_pending = True
            self.debug_active = enabled and expiry is not None and expiry/1000 > now
            self.deadline = expiry/1000 if expiry else None
            self.debug_start = start
            atomic_json(self.args.source_state, normalized)
            self.source_history.append(normalized)
            self.stats.update(last_state_unix=now, debug_active=self.debug_active,
                              session_expires_unix=self.deadline)
            atomic_json(self.args.status_file, self.stats)
        self.clear_if_needed()
        return b'CONTINUE' if self.debug_active else b'STOP'

    def clear_if_needed(self):
        with self.lock:
            if not self.clear_pending:
                return
            self.lab('/v1/clear', {})
            self.seen.clear()
            self.history.clear()
            self.source_history.clear()
            self.clear_pending = False
            self.stats['cleared_unix'] = time.time()

    def frame(self, parts):
        now = time.time()
        record = json.loads(parts['record'])
        key = record.get('captureId')
        with self.lock:
            if self.clear_pending or not self.debug_active or not self.deadline or now >= self.deadline:
                raise ValueError('debug_not_active')
            if key in self.seen:
                self.stats['duplicates'] += 1
                return b'OK'
            payload = frame_payload(record, parts['image'], list(self.history), now,
                                    list(self.source_history))
            if abs(payload['metadata']['session_expires_unix'] - self.deadline) > .001:
                raise ValueError('wrong_debug_session')
            # Enrichment happens only here; the TV's immutable evidence is retained.
            self.lab('/v1/frames', payload)
            self.seen.add(key)
            if len(self.seen) > 20000:
                self.seen = {key}
            self.stats['accepted'] += 1
            self.stats['last_frame_unix'] = now
            atomic_json(self.args.status_file, self.stats)
        return b'OK'

    def monitor(self):
        while True:
            try:
                with urllib.request.urlopen(self.args.dashboard_url+'/native-metadata', timeout=2) as r:
                    snapshot = json.load(r)
                with self.lock:
                    self.history.append((time.time(), snapshot))
            except Exception:
                pass
            with self.lock:
                if self.deadline and time.time() >= self.deadline:
                    self.debug_active = False
                    self.clear_pending = True
                    self.deadline = None
            try:
                self.clear_if_needed()
            except Exception:
                pass
            time.sleep(1)


def serve(args):
    feed = Feed(args)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.connection.settimeout(12)
            if (self.client_address[0] != args.tv_host or not
                hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+feed.token)):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BODY:
                    raise ValueError('size')
                content_type = self.headers.get('Content-Type', '')
                if not content_type.startswith('multipart/form-data;'):
                    raise ValueError('content_type')
                body = self.rfile.read(size)
                message = BytesParser(policy=default).parsebytes(
                    ('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
                parts = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True)
                         for part in message.iter_parts()}
                if self.path == '/tv-state':
                    answer = feed.state(parts)
                elif self.path == '/tv-record':
                    answer = feed.frame(parts)
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Length', str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)
            except Exception as error:
                with feed.lock:
                    feed.stats['errors'] += 1
                    feed.stats['last_error_type'] = type(error).__name__
                    atomic_json(args.status_file, feed.stats)
                self.send_error(400, 'sample unavailable or rejected')
    threading.Thread(target=feed.monitor, daemon=True).start()
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', required=True, help='Mac LAN address; only TV IP plus token accepted')
    parser.add_argument('--port', type=int, default=8796)
    parser.add_argument('--tv-host', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--lab-token-file', type=Path, required=True)
    parser.add_argument('--source-state', type=Path, required=True)
    parser.add_argument('--status-file', type=Path, required=True)
    parser.add_argument('--lab-url', default='http://127.0.0.1:8795')
    parser.add_argument('--dashboard-url', default='http://127.0.0.1:8792')
    serve(parser.parse_args())
