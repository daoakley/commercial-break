import unittest
from unittest.mock import patch
from types import SimpleNamespace
from native_ads import NativeAds, YOUTUBE_TV
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
        self.setUp();self.arm();self.now+=5.01;self.assertIsNone(self.take())

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
        with patch('sponsored_badge.present',return_value=False):
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
        d.process('tv',b'x',ctx);self.native=d.native_ads;self.identity=d.identities['tv'];self.arm();self.now+=6
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

if __name__=='__main__':unittest.main()
