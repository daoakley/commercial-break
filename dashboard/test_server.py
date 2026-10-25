import tempfile
import unittest
from server import Study

class StudyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.now=1000.
        self.study=Study(self.temp.name,lambda:self.now,lambda:self.now)
    def tearDown(self):self.temp.cleanup()
    def start(self,**kwargs):
        kwargs.setdefault('duration_seconds',300)
        return self.study.action(dict(kind='start',initial_state='program',source='YouTube TV',channel='FS1',show='Game A',**kwargs))
    def test_outside_window_and_expiry(self):
        with self.assertRaises(ValueError):self.study.action({'kind':'ad'})
        self.start();self.now+=300
        self.assertIsNone(self.study.snapshot()['active'])
        self.assertEqual(self.study.rows[-1]['effective_unix_ms'],1300000)
        with self.assertRaises(ValueError):self.study.action({'kind':'program'})
    def test_idempotency_and_undo(self):
        self.start();self.study.action({'kind':'ad','request_id':'one'})
        self.study.action({'kind':'ad','request_id':'one'})
        self.assertEqual(sum(r['kind']=='ad' for r in self.study.rows),1)
        self.assertEqual(self.study.action({'kind':'undo'})['state'],'program')
    def test_show_and_channel_boundaries(self):
        first=self.start()['active']['profile_id'];self.study.action({'kind':'end'})
        self.assertEqual(self.start()['active']['profile_id'],first)
        self.study.action({'kind':'end'})
        second=self.start(new_show=True)['active']['profile_id'];self.assertNotEqual(second,first)
        self.assertEqual(self.study.action({'kind':'channel_changed'})['state'],'uncertain')
        self.study.action({'kind':'end'})
        self.assertNotEqual(self.start()['active']['profile_id'],second)
    def test_planned_handoff_does_not_extend_window(self):
        self.start();self.now+=80
        replacement=Study(self.temp.name,lambda:self.now,lambda:self.now,resume_active=True)
        self.assertEqual(replacement.snapshot()['remaining_seconds'],220)
        self.assertEqual(len(replacement.rows),1)
    def test_unplanned_restart_closes_window(self):
        self.start();replacement=Study(self.temp.name,lambda:self.now,lambda:self.now)
        self.assertIsNone(replacement.active)
        self.assertEqual(replacement.rows[-1]['reason'],'server_restart')

    def test_long_window_and_persisted_extension(self):
        self.start(duration_seconds=900);self.now+=301
        self.assertIsNotNone(self.study.snapshot()['active'])
        self.study.action({'kind':'extend','request_id':'extra'})
        self.study.action({'kind':'extend','request_id':'extra'})
        replacement=Study(self.temp.name,lambda:self.now,lambda:self.now,resume_active=True)
        self.assertEqual(replacement.snapshot()['remaining_seconds'],899)
        self.assertEqual(replacement.snapshot()['active']['planned_end_unix_ms'],2200000)
        self.now=2200
        self.assertIsNone(replacement.snapshot()['active'])
        self.assertEqual(replacement.rows[-1]['effective_unix_ms'],2200000)

    def test_extension_limit_and_invalid_duration(self):
        for value in (True,0,3600,'900'):
            with self.assertRaises(ValueError):self.start(duration_seconds=value)
        self.start(duration_seconds=1800)
        for i in range(6):self.study.action({'kind':'extend'})
        with self.assertRaises(ValueError):self.study.action({'kind':'extend'})
        self.assertEqual(self.study.snapshot()['remaining_seconds'],3600)

    def test_extension_after_expiry_cannot_fill_unattended_time(self):
        self.start();self.now+=301
        with self.assertRaises(ValueError):self.study.action({'kind':'extend'})

if __name__=='__main__':unittest.main()
