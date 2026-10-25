"""Read-only YouTube TV event summary for the private dashboard.

Reuses the tested Lounge transport, but never forwards events to the detector.
No playback, mute, overlay or queue mutations. Raw IDs and tokens stay private.
"""
import fcntl
import hashlib
import math
from pathlib import Path
import importlib.util
import threading
import time

PROJECT = Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('cb_youtube_transport', PROJECT/'youtube_events.py')
transport=importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
Relay,SessionChanged=transport.Relay,transport.SessionChanged


def number(value):
    try:
        n=float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def reference(value):
    return hashlib.sha256(value.encode()).hexdigest()[:12] if isinstance(value,str) and value else None


class Metadata:
    def __init__(self, clock=time.time):
        self.clock=clock
        self.lock=threading.Lock()
        self.data={'connection':'connecting', 'content_changes':0, 'ad_events':0}
        self.content=None
        self.binding=None

    def reset(self, binding):
        with self.lock:
            self.binding=binding
            self.content=None
            self.data={'connection':'connecting', 'content_changes':0, 'ad_events':0}

    def connection(self, state):
        with self.lock:self.data['connection']=state

    def event(self, kind, data, binding):
        now=self.clock()
        with self.lock:
            if binding!=self.binding:return
            self.data.update(connection='connected',last_event_unix=now)
            if kind in ('nowPlaying','playlistModified') and isinstance(data.get('videoId'),str):
                content=data['videoId']
                if self.content != content:
                    changes=self.data['content_changes']+int(self.content is not None)
                    self.data={'connection':'connected','content_changes':changes,'ad_events':0,
                               'content_first_seen_unix':now,'last_event_unix':now}
                    self.content=content
                self.data['playback_reference']=reference(content)
            if kind in ('nowPlaying','onStateChange'):
                for source,target in [('currentTime','position_seconds'),('duration','duration_seconds'),
                    ('liveIngestionTime','live_ingestion_raw'),('seekableStartTime','seekable_start_seconds'),
                    ('seekableEndTime','seekable_end_seconds')]:
                    if source in data:self.data[target]=number(data[source])
                if 'currentTime' in data:self.data['position_observed_unix']=now
                if 'state' in data:
                    self.data['player_state']=str(data['state'])[:12]
                    self.data['state_observed_unix']=now
                if kind=='nowPlaying':self.data['now_playing_unix']=now
            elif kind=='adPlaying' and self.content and data.get('contentVideoId')==self.content:
                self.data.update(last_inserted_ad_unix=now,ad_events=self.data['ad_events']+1,
                    ad_reference=reference(data.get('adVideoId')),ad_duration_reported=number(data.get('duration')),
                    ad_position_reported=number(data.get('currentTime')),ad_state=str(data.get('adState',''))[:12])
            elif kind=='onAdStateChange':
                self.data['ad_state']=str(data.get('adState',''))[:12]
                self.data['ad_state_observed_unix']=now
            elif kind=='loungeScreenDisconnected':self.data['connection']='disconnected'

    def snapshot(self, binding):
        with self.lock:
            if binding is None or binding!=self.binding:
                return {'connection':'waiting_for_youtube_tv'}
            data=dict(self.data)
        age=self.clock()-data.get('last_event_unix',0)
        data['fresh']=data['connection']=='connected' and age<45
        data['event_age_seconds']=max(0,round(age,1)) if data.get('last_event_unix') else None
        return data


class MetadataRelay(Relay):
    def __init__(self, tv_host, live, metadata):
        super().__init__(tv_host, '', '')
        self.live,self.metadata=live,metadata
        self.last_query=0
        self.query_id=10

    def run_connection(self, deadline):
        self.last_query=time.monotonic()
        return super().run_connection(deadline)

    def identity(self):
        return self.live.native_binding()

    def post(self, kind, **extra):
        # Intentionally no detector writes, including native ad-onset writes.
        if kind=='disconnect':self.metadata.connection('reconnecting')

    def event(self, kind, args):
        self.last_native=time.monotonic()
        self.check()
        data=args[0] if args and isinstance(args[0],dict) else {}
        self.metadata.event(kind,data,self.binding)
        if kind=='nowPlaying':self.content=data.get('videoId')
        if kind=='loungeScreenDisconnected':raise SessionChanged()

    def check(self):
        now=time.monotonic()
        if now-self.last_check > 2:
            self.last_check=now
            binding=self.identity()
            if binding is None:
                raise SessionChanged()
            if binding!=self.binding:
                # A channel/navigation generation is not a broken cloud session.
                self.binding=binding
                self.content=self.pending=None
                self.metadata.reset(binding)
                self.last_query=0
        if self.cloud.get('sid') and self.cloud.get('gsession') and now-self.last_query>15:
            self.last_query=now
            self.offset+=1
            self.query_id=self.offset+1
            with self.google('/bc/bind',{'count':1,'ofs':self.offset,'req0__sc':'getNowPlaying'},
                {**self.common(),'RID':self.query_id},timeout=3) as r:
                r.read(65536)


class NativeStatus:
    def __init__(self, tv_host, live):
        self.live=live
        self.metadata=Metadata()
        self.relay=MetadataRelay(tv_host,live,self.metadata)
        self.file=None
        self.connection_count=0
        self.last_failure=None
        self.recent_failures=[]
        self.paused=False
        threading.Thread(target=self.run,daemon=True).start()

    def snapshot(self):
        result=self.metadata.snapshot(self.live.native_binding())
        if self.paused:result={'connection':'paused_after_failures'}
        result.update(connections=self.connection_count, poll_timeouts=self.relay.poll_timeouts,
                      last_failure=self.last_failure)
        return result

    def run(self):
        self.file=(PROJECT/'.native-events.lock').open('a')
        try:fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.metadata.connection('another_observer_active')
            return
        while True:
            binding=self.live.native_binding()
            if binding is None:
                self.metadata.reset(None)
                time.sleep(2)
                continue
            self.metadata.reset(binding)
            started=time.monotonic()
            try:
                self.connection_count+=1
                self.relay.run_connection(time.monotonic()+86400)
            except SessionChanged:
                self.metadata.connection('waiting_for_youtube_tv')
                if time.monotonic()-started<120:
                    self.last_failure='early_source_change'
                    self.paused=True
                    return
            except Exception as error:
                self.last_failure=type(error).__name__
                self.metadata.connection('reconnecting')
                now=time.monotonic()
                self.recent_failures=[t for t in self.recent_failures if now-t<300]+[now]
                # An unhealthy observer must stop, not keep pairing with the TV.
                if len(self.recent_failures)>=2:
                    self.paused=True
                    return
                print('Metadata transport failure: '+self.last_failure,flush=True)
            time.sleep(10)
