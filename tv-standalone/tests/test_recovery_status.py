"""Recovery status must distinguish a fresh engine from a saved old snapshot."""
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'recovery.py'
spec = importlib.util.spec_from_file_location('commercial_break_recovery', SCRIPT)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def status(snapshot_at=None, connected=False, enabled=True):
    report = ('ActiveState=active\nSubState=running\n'
              '{"enabled":' + str(enabled).lower() + ',"queries":12,"matches":2}')
    return {
        'state': {
            'version': '0.1.1', 'bootId': 'test-boot', 'armed': True,
            'pid': 7, 'startedAt': 1000,
            'events': [{'at': 1200, 'kind': 'developer-host-restored',
                        'message': 'private computer address'}],
            'engine': None if snapshot_at is None else
            {'at': snapshot_at, 'report': report},
        },
        'platform': {
            'agent': {'connected': connected, 'uid': 0 if connected else None},
            'attempts': [{'connect': 'fail:sdbClosed'}],
        },
    }


class RecoveryStatusTests(unittest.TestCase):
    def test_closed_developer_connection_has_specific_hint_and_no_raw_event(self):
        result = recovery.summarize_status(status(), now=100)
        self.assertFalse(result['rootConnected'])
        self.assertEqual(result['lastRootFailure'], 'sdbClosed')
        self.assertIn('127.0.0.1', result['diagnosis'])
        self.assertNotIn('private computer address', str(result))

    def test_fresh_running_engine_and_saved_off_are_distinct(self):
        result = recovery.summarize_status(status(99_000, True), now=100)
        self.assertTrue(result['engineFresh'])
        self.assertTrue(result['engineServiceActive'])
        self.assertEqual(result['engine']['queries'], 12)
        self.assertIn('compare checks', result['diagnosis'])
        off = recovery.summarize_status(status(99_000, True, False), now=100)
        self.assertIn('switched Off', off['diagnosis'])

    def test_stale_snapshot_cannot_prove_engine_is_running(self):
        result = recovery.summarize_status(status(20_000, True), now=100)
        self.assertFalse(result['engineFresh'])
        self.assertIsNone(result['engineServiceActive'])
        self.assertIsNone(result['engine'])
        self.assertIn('No fresh proof', result['diagnosis'])
        disconnected = recovery.summarize_status(status(99_000, False), now=100)
        self.assertFalse(disconnected['engineFresh'])
        self.assertIsNone(disconnected['engineServiceActive'])
        self.assertIsNone(disconnected['engine'])
        future = recovery.summarize_status(status(110_000, True), now=100)
        self.assertFalse(future['engineFresh'])
        self.assertIsNone(future['engineSnapshotAgeSeconds'])


if __name__ == '__main__':
    unittest.main()
