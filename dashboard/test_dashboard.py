import json
import base64
import struct
import threading
import time
import unittest
from unittest.mock import patch, Mock
from screen_capture import ScreenCapture, decode_capture, capture_tv, COMMAND
from live_status import LiveStatus

PNG=b'\x89PNG\r\n\x1a\n'+b'\0'*8+struct.pack('>II',480,270)+b'data'
DATA={'observed_unix':123,'app':'example','heartbeat_age_seconds':2,'cover_active':False,'muted':True}

def result(): return PNG,DATA,480,270

def finished(capture):
    until=time.monotonic()+1
    while capture.snapshot()['phase']=='capturing' and time.monotonic()<until: time.sleep(.005)
    return capture.snapshot()

class DashboardTests(unittest.TestCase):
    def test_decode_whitelists_data_and_rejects_non_images(self):
        def raw(image):
            return json.dumps({'result':{'stdout':'DATA_BEGIN\n'+json.dumps(dict(DATA,token='secret'))+'\nDATA_END\nIMAGE_BEGIN\n'+base64.b64encode(image).decode()+'\nIMAGE_END'}})
        png,data,w,h=decode_capture(raw(PNG))
        self.assertEqual((w,h),(480,270));self.assertNotIn('token',data)
        with self.assertRaises(ValueError):decode_capture(raw(b'not image'))
    def test_duplicate_clicks_share_one_capture(self):
        gate=threading.Event();calls=[]
        def runner(host):calls.append(host);gate.wait(1);return result()
        c=ScreenCapture('tv',runner);first=c.start()
        self.assertEqual(c.start()['started_unix'],first['started_unix'])
        gate.set();self.assertEqual(finished(c)['phase'],'ready');self.assertEqual(calls,['tv'])
    def test_failure_preserves_last_image_and_timestamp(self):
        c=ScreenCapture('tv',lambda host:result());c.start();old=finished(c)
        def fail(host):raise TimeoutError()
        c.runner=fail;c.state['finished_unix']=0;c.start();new=finished(c)
        self.assertEqual(new['phase'],'error');self.assertIn('30 seconds',new['error'])
        self.assertEqual(new['captured_unix'],old['captured_unix']);self.assertEqual(c.image_bytes(),PNG)
    def test_process_timeout_kills_process_group(self):
        import subprocess
        process=Mock(pid=123)
        process.communicate.side_effect=[subprocess.TimeoutExpired('capture',30),(b'',None)]
        with patch('screen_capture.subprocess.Popen',return_value=process),patch('screen_capture.os.killpg') as kill:
            with self.assertRaises(TimeoutError):capture_tv('tv')
            kill.assert_called_once();self.assertEqual(process.communicate.call_args_list[0].kwargs,{'timeout':30})
    def test_status_does_not_expose_private_ids_or_credentials(self):
        row={'identity':{'transport_session':'private','youtube_playback_id':'private','observed_unix':123,'source_app':'com.samsung.tv.cobalt-yttv'},'token':'secret','viewing_context':{'show':{'name':'Movie','source':'vision_inference'}}}
        data=LiveStatus.summarize(row)
        self.assertNotIn('private',json.dumps(data));self.assertNotIn('secret',json.dumps(data));self.assertEqual(data['source'],'YouTube TV')
        live=LiveStatus(None,'http://localhost');live.data=data;live.received=time.time()
        self.assertFalse(live.snapshot()['fresh']);self.assertTrue(live.snapshot()['connected'])
        live.received=0;self.assertFalse(live.snapshot()['connected'])
    def test_capture_does_not_change_controls_or_drop_cover(self):
        for forbidden in ('SetSpeakerMute','overlay_release','panel-mask-enabled','touch '):
            self.assertNotIn(forbidden,COMMAND)
        self.assertIn('CAPTURE_OVERLAY_PAUSE_FILE= CAPTURE_OVERLAY_ACK_FILE=',COMMAND)

if __name__=='__main__':unittest.main()
