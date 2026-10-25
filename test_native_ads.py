import unittest
from unittest.mock import patch
from types import SimpleNamespace
from native_ads import NativeAds, YOUTUBE_TV, HINT_SECONDS
from server import Detector, Verdict
from youtube_events import Relay


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.now=1000.
        self.native=NativeAds(lambda:self.now)
        self.identity=SimpleNamespace(app=YOUTUBE_TV,session='agent-1',epoch=0)
        self.seq=0

    def event(self,kind,**extra):
        self.seq+=1
        return self.native.observe(dict(tv_id='tv',session='agent-1',epoch=0,connection='connection-123',
            sequence=self.seq,observed_unix=self.now,kind=kind,content_id='program-id',**extra),self.identity)

    def arm(self):
        self.assertTrue(self.event('playback'))
        self.assertTrue(self.event('ad_start',creative_id='creative-id',player_state=1081))

    def take(self):return self.native.take('tv','agent-1',YOUTUBE_TV,self.now,0)

    def test_once_only_and_age_bounded(self):
        self.arm();self.assertIsNotNone(self.take());self.assertIsNone(self.take())
        self.setUp();self.arm();self.now+=HINT_SECONDS+.01;self.assertIsNone(self.take())

    def test_navigation_or_epoch_cannot_inherit_event(self):
        self.arm()
        self.assertIsNone(self.native.take('tv','agent-2',YOUTUBE_TV,self.now,0))
        self.assertIsNone(self.native.take('tv','agent-1',YOUTUBE_TV,self.now,1))
        self.identity.epoch=1;self.assertFalse(self.event('heartbeat'))

    def test_missing_baseline_wrong_content_and_replay_rejected(self):
        self.assertFalse(self.event('ad_start',creative_id='id-1',player_state=1081))
        self.arm()
        self.assertFalse(self.event('ad_start',creative_id='creative-id',player_state=1081))
        d=dict(tv_id='tv',session='agent-1',epoch=0,connection='connection-123',sequence=self.seq,
            observed_unix=self.now,kind='ad_start',content_id='other-content',creative_id='id-2',player_state=1081)
        self.assertFalse(self.native.observe(d,self.identity))

    def test_end_disconnect_and_changed_program_revoke_unused_hint(self):
        for kind in ['ad_end','disconnect','playback']:
            self.setUp();self.arm()
            if kind=='playback':
                self.seq+=1
                self.native.observe(dict(tv_id='tv',session='agent-1',epoch=0,connection='connection-123',sequence=self.seq,
                    observed_unix=self.now,kind=kind,content_id='new-program'),self.identity)
            else:self.event(kind)
            self.assertIsNone(self.take())

    def test_stale_baseline_and_future_timestamp_rejected(self):
        self.event('playback');self.now+=26
        self.assertFalse(self.event('ad_start',creative_id='id-1',player_state=1081))
        self.assertFalse(self.native.observe(dict(tv_id='tv',session='agent-1',epoch=0,connection='connection-123',sequence=99,
            observed_unix=self.now+100,kind='playback',content_id='program-id'),self.identity))

    def test_native_onset_bypasses_model_but_native_end_cannot_unmute(self):
        class Vision:
            calls=0
            def classify(self,*args):
                self.calls+=1
                return Verdict('program',.95,'A show')
        vision=Vision();d=Detector(vision,lambda:self.now)
        ctx=dict(app=YOUTUBE_TV,session='agent-1',frame_sequence='1')
        d.process('tv',b'program',ctx)
        self.native=d.native_ads;self.identity=d.identities['tv']
        self.arm()
        with patch('server.NATIVE_ONSET_MODE','active'),patch('sponsored_badge.present',return_value=False):
            action,v=d.process('tv',b'new-ad',dict(ctx,frame_sequence='2'))
        self.assertEqual(action,'MUTE');self.assertEqual(v.evidence,'native YouTube ad onset')
        self.assertEqual(vision.calls,1)
        self.event('ad_end');self.assertTrue(d.state('tv').muted_by_detector)
        self.now+=1
        self.assertEqual(d.process('tv',b'return1',dict(ctx,frame_sequence='3'))[0],'MUTE')
        self.assertEqual(d.process('tv',b'return2',dict(ctx,frame_sequence='4'))[0],'UNMUTE')

    def test_expired_native_event_does_not_override_program(self):
        class Vision:
            def classify(self,*a):return Verdict('program',.9,'Show')
        d=Detector(Vision(),lambda:self.now);ctx=dict(app=YOUTUBE_TV,session='agent-1',frame_sequence='1')
        d.process('tv',b'x',ctx);self.native=d.native_ads;self.identity=d.identities['tv'];self.arm();self.now+=HINT_SECONDS+1
        self.assertEqual(d.process('tv',b'y',dict(ctx,frame_sequence='2'))[0],'UNMUTE')

    def test_relay_requires_paired_state_event_and_current_content(self):
        r=Relay('test.invalid','http://localhost','fake');r.check=lambda:None
        sent=[];r.post=lambda kind,**data:sent.append((kind,data))
        r.event('nowPlaying',[{'videoId':'program-id'}])
        ad={'contentVideoId':'program-id','adVideoId':'creative-id','currentTime':'0','duration':'60','adState':'-1'}
        r.event('adPlaying',[ad]);self.assertEqual(len(sent),1)
        r.event('onStateChange',[{'state':'1081'}]);self.assertEqual(sent[-1][0],'ad_start')
        r.event('onAdStateChange',[{'adState':'0'}]);self.assertEqual(sent[-1][0],'ad_end')
        n=len(sent);r.event('adPlaying',[dict(ad,contentVideoId='other')]);r.event('onStateChange',[{'state':'1081'}])
        self.assertEqual(len(sent),n)

    def test_epoch_only_reset_revokes_pending_onset(self):
        # Same connection, session and content but a new epoch (e.g. channel
        # change within the app) must not carry an armed hint across.
        self.arm()
        self.identity.epoch=1
        self.seq+=1
        self.assertTrue(self.native.observe(dict(tv_id='tv',session='agent-1',epoch=1,connection='connection-123',
            sequence=self.seq,observed_unix=self.now,kind='playback',content_id='program-id'),self.identity))
        self.assertIsNone(self.native.take('tv','agent-1',YOUTUBE_TV,self.now,1))
        self.assertIsNone(self.native.take('tv','agent-1',YOUTUBE_TV,self.now,0))

    def test_onset_arriving_during_model_call_is_used_without_waiting_a_cycle(self):
        class Vision:
            def __init__(s,native,arm):s.native,s.arm=native,arm
            def classify(s,*a):
                s.arm();return Verdict('program',.95,'A show')
        d=Detector(None,lambda:self.now);ctx=dict(app=YOUTUBE_TV,session='agent-1',frame_sequence='1')
        d.vision=Vision(d.native_ads,lambda:None);d.process('tv',b'program',ctx)
        self.native=d.native_ads;self.identity=d.identities['tv'];self.event('playback')
        def arm():
            self.event('ad_start',creative_id='creative-id',player_state=1081)
        d.vision.arm=arm
        with patch('server.NATIVE_ONSET_MODE','active'),patch('sponsored_badge.present',return_value=False):
            action,v=d.process('tv',b'pre-onset-frame',dict(ctx,frame_sequence='2'))
        self.assertEqual((action,v.evidence),('MUTE','native YouTube ad onset'))

    def test_shadow_mode_records_but_never_covers(self):
        class Vision:
            def classify(self,*a):return Verdict('program',.95,'A show')
        d=Detector(Vision(),lambda:self.now);ctx=dict(app=YOUTUBE_TV,session='agent-1',frame_sequence='1')
        d.process('tv',b'program',ctx);self.native=d.native_ads;self.identity=d.identities['tv'];self.arm()
        with patch('server.NATIVE_ONSET_MODE','shadow'),patch('sponsored_badge.present',return_value=False):
            action,v=d.process('tv',b'frame',dict(ctx,frame_sequence='2'))
        self.assertEqual((action,v.label),('UNMUTE','program'))
        self.assertEqual(d.native_ads.metrics()['used_starts'],1)

    def test_pod_end_wakes_a_covered_helper_once_and_only_for_the_same_playback(self):
        self.arm()
        self.assertFalse(self.native.take_end('tv','agent-1',YOUTUBE_TV,0))
        self.event('ad_end')
        self.assertFalse(self.native.take_end('tv','agent-1',YOUTUBE_TV,0))   # too fresh: next ad may follow
        self.now+=2
        self.assertFalse(self.native.take_end('tv','agent-2',YOUTUBE_TV,0))   # other navigation session
        self.assertFalse(self.native.take_end('tv','agent-1',YOUTUBE_TV,1))   # other epoch
        self.assertTrue(self.native.take_end('tv','agent-1',YOUTUBE_TV,0))
        self.assertFalse(self.native.take_end('tv','agent-1',YOUTUBE_TV,0))   # one-shot
        self.setUp();self.arm();self.event('ad_end');self.now+=21
        self.assertFalse(self.native.take_end('tv','agent-1',YOUTUBE_TV,0))   # stale

    def test_mid_pod_end_followed_by_next_ad_does_not_wake(self):
        self.arm();self.event('ad_end');self.now+=0.01
        self.event('ad_start',creative_id='creative-2',player_state=1081)
        self.now+=2
        self.assertFalse(self.native.take_end('tv','agent-1',YOUTUBE_TV,0))
        # The real pod end, with nothing after it, still wakes.
        self.event('ad_end');self.now+=2
        self.assertTrue(self.native.take_end('tv','agent-1',YOUTUBE_TV,0))

    def test_detector_wake_requires_cover_and_matching_session(self):
        class Vision:
            def classify(self,*a):return Verdict('ad',.95)
        d=Detector(Vision(),lambda:self.now);ctx=dict(app=YOUTUBE_TV,session='agent-1',frame_sequence='1')
        d.process('tv',b'ad1',ctx);d.process('tv',b'ad2',dict(ctx,frame_sequence='2'))
        self.assertTrue(d.state('tv').muted_by_detector)
        self.native=d.native_ads;self.identity=d.identities['tv'];self.event('playback');self.event('ad_end');self.now+=2
        self.assertFalse(d.wake('tv',{'session':'agent-9'}))
        self.assertTrue(d.wake('tv',{'session':'agent-1'}))
        self.assertFalse(d.wake('tv',{'session':'agent-1'}))
        # Uncovered: nothing to wake for even with a fresh end.
        self.event('ad_end');self.now+=2;d.state('tv').muted_by_detector=False
        self.assertFalse(d.wake('tv',{'session':'agent-1'}))

if __name__=='__main__':unittest.main()
