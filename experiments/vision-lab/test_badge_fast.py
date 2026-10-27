import io
import unittest

import numpy as np
from PIL import Image

import sponsored_badge


class FastBadgeTests(unittest.TestCase):
    def compare(self, image):
        data = io.BytesIO()
        image.save(data, format="PNG")
        original = sponsored_badge.score(data.getvalue())
        optimized = sponsored_badge.score_image(image)
        self.assertEqual(original, optimized)
        self.assertEqual(original >= 300.0, optimized >= 300.0)

    def test_random_rgb_and_rgba_exact_luma_rounding(self):
        for seed in range(8):
            for channels in (3, 4):
                pixels = np.random.default_rng(seed).integers(0, 256, (270, 480, channels), dtype=np.uint8)
                self.compare(Image.fromarray(pixels))

    def test_black_white_and_positive_template(self):
        self.compare(Image.new("RGB", (480, 270), "black"))
        self.compare(Image.new("RGBA", (480, 270), (255, 255, 255, 0)))
        pixels = np.zeros((270, 480, 3), dtype=np.uint8)
        weights = np.asarray(sponsored_badge._weights).reshape(12, 64)
        pixels[24:36, 18:82][weights > 0] = 255
        image = Image.fromarray(pixels)
        self.compare(image)
        self.assertGreater(sponsored_badge.score_image(image), 300)
        self.assertEqual(sponsored_badge.THRESHOLD, 300.0)

    def test_wrong_resolution_rejected(self):
        with self.assertRaises(ValueError):
            sponsored_badge.score_image(Image.new("RGB", (1920, 1080)))


if __name__ == "__main__":
    unittest.main()
