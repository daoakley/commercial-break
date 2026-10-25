import unittest
from unittest.mock import Mock
from native_status import Metadata, MetadataRelay, number

class MetadataTests(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.m=Metadata(lambda:self.now);self.binding=('session',1);self.m.reset(self.binding)
 def event(self,kind,**data):self.m.event(kind,data,self.binding)
 def test_playback_and_content_change_clear_old_ad_fields(self):
  self.event('nowPlaying',videoId='private-a',currentTime='720',duration='7200',state='1',seekableStartTime='0',seekableEndTime='900')
  self.event('adPlaying',contentVideoId='private-a',adVideoId='creative',duration='60')
  a=self.m.snapshot(self.binding);self.assertEqual(a['position_seconds'],720);self.assertEqual(a['ad_events'],1)
  self.event('nowPlaying',videoId='private-b',currentTime='15',state='1')
  b=self.m.snapshot(self.binding);self.assertNotEqual(a['playback_reference'],b['playback_reference']);self.assertEqual(b['content_changes'],1)
  self.assertNotIn('last_inserted_ad_unix',b);self.assertNotIn('duration_seconds',b);self.assertNotIn('private',str(b))
 def test_stale_and_binding_changes_never_report_fresh(self):
  self.event('nowPlaying',videoId='id',currentTime=100);self.now+=46
  self.assertFalse(self.m.snapshot(self.binding)['fresh'])
  self.assertEqual(self.m.snapshot(('new',2)),{'connection':'waiting_for_youtube_tv'})
  self.m.event('nowPlaying',{'videoId':'old'},('old',0));self.assertEqual(self.m.content,'id')
 def test_wrong_content_ads_and_nonfinite_numbers(self):
  self.event('nowPlaying',videoId='id',duration='nan')
  self.event('adPlaying',contentVideoId='other',adVideoId='ad')
  self.assertEqual(self.m.snapshot(self.binding)['ad_events'],0);self.assertIsNone(number('inf'))
 def test_relay_post_cannot_actuate_detector(self):
  relay=MetadataRelay('tv',Mock(),self.m);relay.local=Mock(side_effect=AssertionError('No detector writes'))
  relay.post('ad_start',creative_id='id');relay.post('ad_end');relay.post('playback')
  relay.local.assert_not_called()

if __name__=='__main__':unittest.main()
