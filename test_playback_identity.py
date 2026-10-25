import threading
import unittest
from playback_identity import PlaybackIdentity
from server import Detector, Verdict


def context(session='agent-100', sequence=1, **extra):
    return dict(app='youtube-tv', session=session, frame_sequence=sequence, **extra)


class IdentityTests(unittest.TestCase):
    def test_older_navigation_rejected_even_if_never_seen(self):
        identity=PlaybackIdentity()
        identity.admit(context('agent-100',1))
        identity.admit(context('agent-300',3))
        self.assertFalse(identity.admit(context('agent-200',2))[0])
        self.assertEqual(identity.session,'agent-300')

    def test_agent_restart_and_old_agent_cannot_return(self):
        identity=PlaybackIdentity()
        identity.admit(context('old-agent-100',100))
        self.assertTrue(identity.admit(context('new-agent-0',1))[0])
        self.assertFalse(identity.admit(context('old-agent-200',101))[0])

    def test_sequence_cannot_repeat_disappear_or_go_backwards(self):
        identity=PlaybackIdentity();identity.admit(context(sequence=5))
        for sequence in [4,5,None,'',True,'bogus']:
            self.assertFalse(identity.admit(context(sequence=sequence))[0])
        self.assertTrue(identity.admit(context(sequence=6))[0])

    def test_missing_session_is_not_a_new_identity(self):
        identity=PlaybackIdentity();identity.admit(context())
        self.assertFalse(identity.admit(context('',2))[0])

    def test_navigation_clears_previous_channel_and_show(self):
        identity=PlaybackIdentity();identity.admit(context(channel='FS1',title='Game'))
        identity.admit(context('agent-200',2))
        data=identity.snapshot()
        self.assertIsNone(data['channel']['name'])
        self.assertIsNone(data['show']['name'])
        self.assertIsNone(data['youtube_playback_id'])
        self.assertEqual(data['epoch'],1)


class ConcurrentResultTests(unittest.TestCase):
    def test_channel_reset_does_not_wait_for_old_ai_and_old_result_cannot_commit(self):
        entered,release=threading.Event(),threading.Event()
        class Vision:
            def classify(self,png,ctx):
                if png==b'old-ad':
                    entered.set();release.wait(3)
                    return Verdict('ad',.99)
                return Verdict('program',.99,'Game')
        d=Detector(Vision());d.process('tv',b'program',context(sequence=1))
        results=[]
        old=threading.Thread(target=lambda:results.append(d.process('tv',b'old-ad',context(sequence=2))))
        old.start();self.assertTrue(entered.wait(1))
        reset_done=threading.Event()
        def reset():
            results.append(d.process('tv',b'new-session',context('agent-200',3)))
            reset_done.set()
        new=threading.Thread(target=reset);new.start()
        try:
            self.assertTrue(reset_done.wait(.5),'session reset waited behind classification')
            self.assertFalse(d.state('tv').muted_by_detector)
            self.assertEqual(d.state('tv').program,'')
            self.assertEqual(d.state('tv').ad_starts,[])
        finally:
            release.set();old.join(2);new.join(2)
        self.assertTrue(all(r[0]=='UNMUTE' for r in results))
        self.assertIn('obsolete playback result',[r[1].evidence for r in results])
        self.assertEqual(d.state('tv').session,'agent-200')
        self.assertEqual(d.state('tv').viewing.starts,[])

    def test_late_same_session_frame_does_not_overwrite_new_program(self):
        entered,release=threading.Event(),threading.Event()
        class Vision:
            def classify(self,png,ctx):
                if png==b'slow':
                    entered.set();release.wait(3)
                    return Verdict('ad',.99)
                return Verdict('program',.99,'Current show')
        d=Detector(Vision());d.process('tv',b'baseline',context(sequence=1))
        result=[]
        thread=threading.Thread(target=lambda:result.append(d.process('tv',b'slow',context(sequence=2))))
        thread.start();self.assertTrue(entered.wait(1))
        try:d.process('tv',b'current',context(sequence=3))
        finally:release.set();thread.join(2)
        self.assertEqual(result[0][1].evidence,'obsolete playback result')
        self.assertFalse(d.state('tv').muted_by_detector)
        self.assertEqual(d.state('tv').program,'Current show')

    def test_unknown_foreground_never_calls_classifier(self):
        class Never:
            def classify(self,*args):raise AssertionError('unknown app reached model')
        d=Detector(Never())
        action,verdict=d.process('tv',b'frame',dict(context(),app=''))
        self.assertEqual(action,'UNMUTE')
        self.assertEqual(verdict.evidence,'foreground app unavailable')

if __name__=='__main__':unittest.main()
