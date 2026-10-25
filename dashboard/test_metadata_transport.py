import socket
import tempfile
from pathlib import Path
import native_status
import unittest
import urllib.error
from unittest.mock import Mock, patch
from native_status import transport, Metadata, MetadataRelay, NativeStatus

class TransportTests(unittest.TestCase):
 def relay(self):
  r=transport.Relay('tv','','');r.cloud={'token':'test','sid':'same-session','aid':3,'gsession':'same-gsession'}
  r.check=Mock();return r
 def test_python39_socket_timeout_retries_same_session(self):
  r=self.relay();clock=[0];response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
  r.google=Mock(side_effect=[socket.timeout('timed out'),response]);r.read_events=Mock(side_effect=lambda *args:clock.__setitem__(0,2))
  with patch.object(transport.time,'monotonic',side_effect=lambda:clock[0]):r.poll_session(1)
  self.assertEqual(r.poll_timeouts,1);self.assertEqual(r.google.call_count,2)
  for call in r.google.call_args_list:self.assertEqual(call.kwargs['params']['SID'],'same-session');self.assertNotIn('data',call.kwargs)
  self.assertEqual(r.cloud['sid'],'same-session')
 def test_timeout_in_status_query_does_not_disconnect(self):
  r=self.relay();clock=[0];r.check=Mock(side_effect=[urllib.error.URLError(socket.timeout()),None])
  response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
  r.google=Mock(return_value=response);r.read_events=Mock(side_effect=lambda *args:clock.__setitem__(0,2))
  with patch.object(transport.time,'monotonic',side_effect=lambda:clock[0]):r.poll_session(1)
  self.assertEqual(r.check.call_count,2);self.assertEqual(r.poll_timeouts,1);self.assertEqual(r.google.call_count,1)
 def test_non_timeout_failure_is_not_swallowed(self):
  r=self.relay();r.google=Mock(side_effect=urllib.error.HTTPError('private',410,'Gone',None,None))
  with self.assertRaises(urllib.error.HTTPError):r.poll_session(transport.time.monotonic()+1)
 def test_channel_change_rebinds_metadata_without_new_cloud_session(self):
  live=Mock();live.native_binding.return_value=('same-agent-next-channel',2)
  m=Metadata();m.reset(('previous-channel',1));m.event('nowPlaying',{'videoId':'old','currentTime':100},('previous-channel',1))
  r=MetadataRelay('tv',live,m);r.binding=('previous-channel',1);r.content='old';r.last_check=0
  # No cloud session is initialized in this unit test: no queries may be sent.
  r.google=Mock(side_effect=AssertionError('Do not re-pair'))
  with patch.object(transport.time,'monotonic',return_value=100):r.check()
  self.assertEqual(r.binding,live.native_binding.return_value);self.assertIsNone(r.content)
  self.assertNotIn('position_seconds',m.snapshot(r.binding));r.google.assert_not_called()
 def test_query_sequence_is_monotonic_and_matches_protocol(self):
  live=Mock();live.native_binding.return_value=('a',1);m=Metadata();r=MetadataRelay('tv',live,m)
  r.binding=('a',1);r.cloud={'token':'test','sid':'sid','aid':1,'gsession':'g'};r.offset=1
  response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);r.google=Mock(return_value=response)
  with patch.object(transport.time,'monotonic',return_value=100):
   for _ in range(2):r.last_query=0;r.check()
  calls=r.google.call_args_list
  self.assertEqual([c.args[1]['ofs'] for c in calls],[2,3]);self.assertEqual([c.args[2]['RID'] for c in calls],[3,4])
  self.assertTrue(all(c.args[1]['req0__sc']=='getNowPlaying' for c in calls))

class StabilityGuardTests(unittest.TestCase):
 def observer(self, failure):
  observer=NativeStatus.__new__(NativeStatus)
  observer.live=Mock();observer.live.native_binding.return_value=('a',1)
  observer.metadata=Mock();observer.relay=Mock();observer.relay.run_connection.side_effect=failure
  observer.file=None;observer.connection_count=0;observer.last_failure=None;observer.recent_failures=[];observer.paused=False
  return observer
 def run_guard(self, observer):
  with tempfile.TemporaryDirectory() as directory,patch.object(native_status,'PROJECT',Path(directory)),patch.object(native_status.time,'sleep'),patch.object(native_status.time,'monotonic',return_value=100):
   observer.run()
   observer.file.close()
 def test_repeated_failure_stops_instead_of_pairing_forever(self):
  observer=self.observer(RuntimeError('test'))
  self.run_guard(observer)
  self.assertTrue(observer.paused);self.assertEqual(observer.connection_count,2)
 def test_early_source_exit_stops_after_first_attempt(self):
  observer=self.observer(native_status.SessionChanged())
  self.run_guard(observer)
  self.assertTrue(observer.paused);self.assertEqual(observer.connection_count,1)
  self.assertEqual(observer.last_failure,'early_source_change')

if __name__=='__main__':unittest.main()
