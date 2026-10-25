"""Read-only detector summary. Credentials and private IDs stay on the server."""
import json
from pathlib import Path
import threading
import time
import urllib.request


class LiveStatus:
    def __init__(self, env_file, url):
        self.data = None
        self.received = 0
        self.binding = None
        self.token = ''
        self.url = url.rstrip('/')+'/v1/status'
        self.lock = threading.Lock()
        if env_file:
            for line in Path(env_file).read_text().splitlines():
                if line.startswith('FRAME_TOKEN='):
                    self.token = line.split('=', 1)[1].strip().strip('\"\'')
        if self.token:
            threading.Thread(target=self.run, daemon=True).start()

    def snapshot(self):
        with self.lock:
            if self.data is None:
                return None
            data = dict(self.data)
            data['received_unix'] = self.received
            data['connected'] = time.time()-self.received <= 12
            data['frame_age_seconds'] = max(0, round(time.time()-data['frame_observed_unix'], 1)) if data['frame_observed_unix'] else None
            data['fresh'] = data['connected'] and data['frame_age_seconds'] is not None and data['frame_age_seconds'] < 45
            return data

    def native_binding(self):
        with self.lock:
            if self.data and time.time()-self.received <= 12 and self.data['app']=='com.samsung.tv.cobalt-yttv' and time.time()-(self.data['frame_observed_unix'] or 0)<45:
                return self.binding
            return None

    @staticmethod
    def summarize(row):
        identity = row.get('identity', {})
        context = row.get('viewing_context', {})
        app = identity.get('source_app')
        return dict(show=context.get('show'), channel=context.get('channel'),
            category=context.get('category'), covered=row.get('muted_by_detector'),
            first_observed=context.get('program_first_observed_unix'),
            broadcast_start=context.get('actual_broadcast_start_unix'),
            last_ad=context.get('last_ad_observed_unix'),
            last_break_end=context.get('last_break_end_unix'),
            break_start=context.get('observed_break_start_unix'),
            predicted_next_break=context.get('predicted_next_break'),
            predicted_break_end=context.get('predicted_break_end'),
            source='YouTube TV' if app == 'com.samsung.tv.cobalt-yttv' else app or 'Unknown source',
            app=app, frame_observed_unix=identity.get('observed_unix'),
            frame_sequence=identity.get('frame_sequence'), epoch=identity.get('epoch'),
            native_metrics=row.get('native_ad_metrics'))

    def run(self):
        while True:
            try:
                req = urllib.request.Request(self.url, headers={'Authorization': 'Bearer '+self.token})
                with urllib.request.urlopen(req, timeout=2) as r:
                    rows = json.load(r)
                row = next((x for x in rows if x.get('tv_id') == 'frame-tv'), None)
                if row:
                    with self.lock:
                        identity=row.get('identity',{})
                        self.binding=(identity.get('transport_session'),identity.get('epoch')) if identity.get('transport_session') else None
                        self.data = self.summarize(row)
                        self.received = time.time()
            except Exception:
                pass
            time.sleep(2)
