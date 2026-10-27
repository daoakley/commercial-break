import unittest
from host_feed import aligned_native, aligned_source, source_binding, frame_payload, normalize_state


class FeedTests(unittest.TestCase):
    def test_no_future_or_other_channel_metadata(self):
        native = {'identity': {'source_app': 'yttv', 'epoch': 20.0},
                  'native': {'usable': True, 'event_observed_unix': 99}}
        self.assertFalse(aligned_native([(101, native)], 100, 'yttv', 20)['native']['usable'])
        self.assertFalse(aligned_native([(99, native)], 100, 'yttv', 21)['native']['usable'])
        self.assertTrue(aligned_native([(99, native)], 100, 'yttv', 20)['native']['usable'])

    def test_stale_state_rejected(self):
        with self.assertRaises(ValueError):
            normalize_state({'observed_unix': 1, 'source_app': 'yttv'}, {}, {}, 100)

    def test_engine_restart_invalidates_bracket(self):
        before = {'observed_unix': 99, 'source_app': 'yttv', 'navigation_epoch': 20,
                  'generation': 'old', 'art_mode': False}
        after = dict(before, observed_unix=101, generation='new')
        self.assertIsNone(aligned_source([before, after], 100, 'yttv', 20))
        self.assertEqual(aligned_source([before, dict(before, observed_unix=101)], 100, 'yttv', 20),
                         source_binding(before))
        self.assertIsNone(aligned_source([before], 100, 'yttv', 20))

    def test_native_reference_must_match_source(self):
        snapshot = {'identity': {'source_app': 'yttv', 'epoch': 20, 'session_reference': 'old'},
                    'native': {'usable': True, 'event_observed_unix': 98}}
        self.assertFalse(aligned_native([(99, snapshot)], 100, 'yttv', 20, 'new')['native']['usable'])

    def test_native_guard_unknown_not_false(self):
        source = {'observed_unix': 100, 'source_app': 'yttv', 'generation': '1-2', 'navigation_epoch': 9}
        self.assertIsNone(normalize_state(source, {}, {}, 100)['art_mode'])
        self.assertFalse(normalize_state(source, {}, {'guard': {'artMode': 'off'}}, 100)['art_mode'])

    def record(self):
        return {'schema': 'commercial-break-debug/1', 'sessionId': 's', 'captureId': 'c',
                'sessionExpiresAt': 200000, 'evidence': {
                    'capture': {'captureStartedAt': 100000, 'mode': 'normal'},
                    'contextBefore': {'foregroundApp': {'value': 'yttv'},
                                      'session': {'navigationGeneration': 20, 'engineGeneration': 1}},
                    'decision': {'sameSession': True}, 'samsung': {'verdict': 'ad'}}}

    def test_native_verdict_is_not_training_truth(self):
        payload = frame_payload(self.record(), b'\x89PNG\r\n\x1a\n', [], 101)
        self.assertNotIn('manual_label', payload)
        self.assertEqual(payload['contamination']['status'], 'clean')
        self.assertFalse(payload['metadata']['native_metadata']['native']['usable'])

    def test_channel_reset_and_cover_contamination(self):
        r = self.record()
        a = frame_payload(r, b'\x89PNG\r\n\x1a\n', [], 101)
        r['evidence']['contextBefore']['session']['navigationGeneration'] = 21
        r['evidence']['capture']['mode'] = 'card-visible'
        b = frame_payload(r, b'\x89PNG\r\n\x1a\n', [], 101)
        self.assertNotEqual(a['session_id'], b['session_id'])
        self.assertEqual(b['contamination']['status'], 'contaminated')
        with self.assertRaises(ValueError):
            frame_payload(r, b'\x89PNG\r\n\x1a\n', [], 201)


if __name__ == '__main__':
    unittest.main()
