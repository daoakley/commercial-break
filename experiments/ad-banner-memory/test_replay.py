import json
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from replay import replay


class ReplaySafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        rgb = np.random.default_rng(71).integers(0, 256, (270, 480, 3), dtype=np.uint8)
        Image.fromarray(rgb).save(self.root / 'frame.png')

    def tearDown(self):
        self.temp.cleanup()

    def event(self, at, **extra):
        row = dict(captured_at=at, expires_at=time.time() + 60, session='A',
                   image='frame.png', clean=True, baseline_positive=False,
                   label='unknown')
        row.update(extra)
        return row

    def run_rows(self, rows):
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(rows))
        return replay(path)

    def test_teacher_response_must_precede_prediction(self):
        result = self.run_rows([
            self.event(0, trusted_ad=True, teacher_accepted_at=2),
            self.event(1, label='ad'), self.event(3, label='ad')])
        self.assertEqual(2, result['ad_frames'])
        self.assertEqual(1, result['combined_true_positive'])

    def test_navigation_without_image_clears_memory(self):
        result = self.run_rows([
            self.event(0, trusted_ad=True, teacher_accepted_at=0.1),
            self.event(1, session='B', image=None),
            self.event(2, label='program')])
        self.assertEqual(0, result['combined_false_positive'])

    def test_expired_evidence_cannot_be_reused(self):
        with self.assertRaises(ValueError):
            self.run_rows([self.event(0, expires_at=time.time() - 1)])


if __name__ == '__main__':
    unittest.main()
