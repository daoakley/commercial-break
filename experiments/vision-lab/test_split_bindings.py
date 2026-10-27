import unittest
from train import group_keys, grouped_split


class SplitBindingTests(unittest.TestCase):
    def test_native_availability_does_not_create_independent_sessions(self):
        metadata = {'tv_debug': {'sessionId': 'debug', 'evidence': {'contextBefore': {
            'session': {'engineGeneration': 1, 'navigationGeneration': 10},
            'foregroundApp': {'value': 'yttv'}}}}}
        rows = [{'session_id': str(i), 'manual_label': 'ad' if i%2 else 'program',
                 'label_source': 'human', 'contamination': {'status': 'clean'}, 'metadata': metadata}
                for i in range(6)]
        shared = group_keys(rows[0]).intersection(group_keys(rows[1]))
        self.assertTrue(any(x.startswith('physical_playback:') for x in shared))
        with self.assertRaisesRegex(ValueError, 'insufficient_data'):
            grouped_split(rows)

    def test_same_native_content_groups_different_navigation(self):
        rows = [{'session_id': str(i), 'metadata': {'native_metadata': {
            'identity': {'content_reference': 'one-content'}}}} for i in range(2)]
        self.assertIn('native_content:one-content', group_keys(rows[0]) & group_keys(rows[1]))


if __name__ == '__main__':
    unittest.main()
