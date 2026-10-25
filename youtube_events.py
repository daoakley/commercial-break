"""Personal-TV live onset relay. No playback, volume, navigation or queue commands.

Credentials stay in memory. Only state queries are sent to YouTube; fresh,
current-session ad starts are forwarded to the authenticated local detector.
"""
import argparse
import fcntl
import io
import json
import os
import socket
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = 'https://www.youtube.com/api/lounge'


def is_network_timeout(error):
    # socket.timeout only became an alias of TimeoutError in Python 3.10.
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    return isinstance(reason, (socket.timeout, TimeoutError))


class SessionChanged(Exception):
    pass


class Relay:
    def __init__(self, tv_host, detector_url, token, tv_id='frame-tv'):
        self.host, self.url, self.token, self.tv_id = tv_host, detector_url.rstrip('/'), token, tv_id
        self.binding = None
        self.seq = 0
        self.connection = ''
        self.pending = None
        self.content = None
        self.last_check = 0
        self.last_heartbeat = 0
        self.last_native = 0
        self.cloud = {}
        self.offset = 1
        self.poll_timeouts = 0

    def local(self, path, data=None):
        req = urllib.request.Request(self.url + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer '+self.token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=2) as r:
            body = r.read(100000)
            return json.loads(body) if path.endswith('status') else body

    def identity(self):
        for row in self.local('/v1/status'):
            identity = row.get('identity', {})
            if row.get('tv_id') == self.tv_id and identity.get('source_app') == 'com.samsung.tv.cobalt-yttv':
                return (identity.get('transport_session'), identity.get('epoch')) if identity.get('transport_session') else None
        return None

    def post(self, kind, **extra):
        self.seq += 1
        data = dict(tv_id=self.tv_id, session=self.binding[0], epoch=self.binding[1], connection=self.connection,
                    sequence=self.seq, observed_unix=time.time(), kind=kind, **extra)
        try:
            self.local('/v1/native-event', data)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                raise SessionChanged()
            raise

    def check(self):
        now = time.monotonic()
        if now-self.last_check > 2:
            self.last_check = now
            if self.identity() != self.binding:
                raise SessionChanged()
        if self.content and now-self.last_heartbeat > 5 and now-self.last_native < 20:
            self.post('heartbeat')
            self.last_heartbeat = now

    def event(self, kind, args):
        self.last_native = time.monotonic()
        self.check()
        data = args[0] if args and isinstance(args[0], dict) else {}
        if kind == 'nowPlaying' and isinstance(data.get('videoId'), str):
            content = data['videoId']
            if content != self.content:
                self.pending = None
            self.content = content
            self.post('playback', content_id=self.content)
        elif kind == 'adPlaying':
            try:
                position = float(data.get('currentTime', -1))
                duration = float(data.get('duration', 0))
                valid = (self.content and data.get('contentVideoId') == self.content
                         and isinstance(data.get('adVideoId'), str) and 0 <= position <= 2
                         and 0 < duration <= 900)
            except (ValueError, TypeError):
                valid = False
            self.pending = (time.monotonic(), data) if valid else None
        elif kind == 'onStateChange':
            if str(data.get('state')) == '1081' and self.pending:
                at, ad = self.pending
                self.pending = None
                if time.monotonic()-at <= 1:
                    self.post('ad_start', content_id=self.content, creative_id=ad['adVideoId'], player_state=1081)
                    print(json.dumps({'event': 'native_onset_forwarded', 'at_unix': time.time()}), flush=True)
        elif kind == 'onAdStateChange' and str(data.get('adState')) == '0':
            self.pending = None
            if self.content:
                self.post('ad_end')
        elif kind == 'loungeScreenDisconnected':
            raise SessionChanged()

    def google(self, path, data=None, params=None, timeout=10):
        url = BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
        req = urllib.request.Request(url,
            data=urllib.parse.urlencode(data).encode() if data is not None else None,
            headers={'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/x-www-form-urlencoded'})
        return urllib.request.urlopen(req, timeout=timeout)

    def common(self):
        return dict(name='Commercial Break', loungeIdToken=self.cloud['token'], SID=self.cloud['sid'],
                    AID=self.cloud['aid'], gsessionid=self.cloud['gsession'], device='REMOTE_CONTROL',
                    app='youtube-desktop', VER='8', v='2')

    def read_events(self, response, deadline):
        stream = io.TextIOWrapper(response, encoding='utf-8')
        while time.monotonic() < deadline:
            line = stream.readline(1048576).strip()
            if not line:
                return
            size = int(line)
            if not 0 < size <= 1048576:
                raise ValueError('invalid chunk')
            for aid, event in json.loads(stream.read(size)):
                self.cloud['aid'] = aid
                kind, *args = event
                if kind == 'c':
                    self.cloud['sid'] = args[0]
                elif kind == 'S':
                    self.cloud['gsession'] = args[0]
                else:
                    self.event(kind, args)

    def screen(self):
        # Use the TV's advertised application URL. GET does not launch an app.
        with urllib.request.urlopen('http://'+self.host+':7678/nservice/', timeout=3) as r:
            appurl = r.headers.get('Application-URL', '')
        if urllib.parse.urlsplit(appurl).hostname != self.host:
            raise ValueError('unexpected DIAL host')
        with urllib.request.urlopen(appurl.rstrip('/')+'/YouTubeTV', timeout=3) as r:
            fields = {e.tag.split('}')[-1]: e.text for e in ET.fromstring(r.read(65536)).iter()}
        if fields.get('state') != 'running' or not fields.get('screenId'):
            raise SessionChanged()
        return fields

    def run_connection(self, deadline):
        self.binding = self.identity()
        if not self.binding:
            return
        self.connection = uuid.uuid4().hex
        self.seq = 0
        self.content = self.pending = None
        self.cloud = {'aid': 0}
        screen = self.screen()
        with self.google('/pairing/get_lounge_token_batch', {'screen_ids': screen['screenId']}) as r:
            screens = json.load(r).get('screens', [])
        self.cloud['token'] = screens[0]['loungeToken']
        body = {'app': 'web', 'mdx-version': '3', 'name': 'Commercial Break', 'id': uuid.uuid4().hex,
                'device': 'REMOTE_CONTROL', 'capabilities': 'que,dsdtr,atp,vsp', 'magnaKey': 'cloudPairedDevice',
                'ui': 'false', 'deviceContext': 'user_agent=CommercialBreak&os_name=desktop',
                'theme': screen.get('theme') or 'cl', 'loungeIdToken': self.cloud['token']}
        try:
            with self.google('/bc/bind', body, {'RID': 1, 'VER': 8, 'CVER': 1, 'auth_failure_option': 'send_error'}) as r:
                self.read_events(r, deadline)
            self.offset = 1
            # Ask for a baseline; no mutating player commands exist in this relay.
            with self.google('/bc/bind', {'count': 1, 'ofs': 1, 'req0__sc': 'getNowPlaying'},
                             {**self.common(), 'RID': 2}) as r:
                r.read(65536)
            print(json.dumps({'event': 'native_connected', 'at_unix': time.time()}), flush=True)
            self.poll_session(deadline)
        finally:
            if self.content:
                try:
                    self.post('disconnect')
                except Exception:
                    pass
            if self.cloud.get('sid') and self.cloud.get('gsession'):
                try:
                    with self.google('/bc/bind', {'ui': '', 'TYPE': 'terminate',
                        'clientDisconnectReason': 'MDX_SESSION_DISCONNECT_REASON_DISCONNECTED_BY_USER'},
                        {**self.common(), 'CVER': 1, 'RID': 3, 'auth_failure_option': 'send_error'}, timeout=3) as r:
                        r.read(65536)
                except Exception:
                    pass
            self.cloud.clear()


    def poll_session(self, deadline):
        # A Python 3.9 socket timeout must not terminate/re-pair this client.
        while time.monotonic() < deadline:
            try:
                self.check()
                with self.google('/bc/bind', params={**self.common(), 'RID': 'rpc', 'CI': '0', 'TYPE': 'xmlhttp'},
                                 timeout=min(10, max(1, deadline-time.monotonic()))) as r:
                    self.read_events(r, deadline)
            except (OSError, urllib.error.URLError) as error:
                if not is_network_timeout(error):
                    raise
                self.poll_timeouts += 1
                continue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tv-host', required=True)
    parser.add_argument('--seconds', type=int, default=0)
    args = parser.parse_args()
    token = os.environ.get('FRAME_TOKEN', '')
    if len(token) < 24:
        raise SystemExit('FRAME_TOKEN required')
    lock = open('.native-events.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Native event relay already running')
    relay = Relay(args.tv_host, os.getenv('DETECTOR_URL', 'http://127.0.0.1:28471'), token,
                  os.getenv('TV_ID', 'frame-tv'))
    deadline = time.monotonic() + (args.seconds if args.seconds > 0 else 365*86400)
    while time.monotonic() < deadline:
        try:
            relay.run_connection(deadline)
        except KeyboardInterrupt:
            break
        except Exception as error:
            print(json.dumps({'event': 'native_reconnecting', 'reason': type(error).__name__}), flush=True)
        time.sleep(2)


if __name__ == '__main__':
    main()
