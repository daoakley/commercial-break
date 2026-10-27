"""Cross-language parity tests; all generated/private image fixtures stay under work/."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import numpy as np
from PIL import Image

TV = Path(__file__).resolve().parents[1]
ROOT = TV.parent
LAB = ROOT
spec = importlib.util.spec_from_file_location("pill_reference", LAB / "sponsored_badge.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
DOTNET = Path(os.environ.get("PILL_DOTNET", "dotnet"))
BUILD = None
DLL = None
ENV = dict(os.environ, DOTNET_ROLL_FORWARD="Major")


class SponsoredPillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global BUILD, DLL
        cls.build_temp = tempfile.TemporaryDirectory(prefix="sponsored-pill-")
        BUILD = Path(cls.build_temp.name) / "build"
        DLL = BUILD / "PillHarness.dll"
        project = TV / "tests/pill-harness/PillHarness.csproj"
        subprocess.run([str(DOTNET), "build", str(project), "-c", "Release", "-o", str(BUILD),
                        "-p:BaseIntermediateOutputPath=" + str(Path(cls.build_temp.name) / "obj") + "/",
                        "-p:UseSharedCompilation=false"], check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.build_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fixtures-")
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_harness(self, *args):
        result = subprocess.run([str(DOTNET), str(DLL), *map(str, args)], check=True, capture_output=True, text=True, env=ENV, timeout=15)
        return json.loads(result.stdout)

    def compare(self, rgb):
        image = Image.fromarray(rgb)
        fixture = self.directory / "frame.rgb"
        fixture.write_bytes(rgb.tobytes())
        result = self.run_harness(fixture)
        png = io.BytesIO()
        image.save(png, format="PNG")
        expected = reference.score(png.getvalue())
        self.assertAlmostEqual(result["score"], expected, delta=1e-9)
        self.assertEqual(result["present"], expected >= reference.THRESHOLD)
        self.assertEqual(result["threshold"], 300)
        self.assertEqual(result["template_sha256"], hashlib.sha256((LAB / "sponsored_template.json").read_bytes()).hexdigest())
        return result

    def test_random_rgb_rounding_and_uniform_negatives(self):
        for seed in range(4):
            self.compare(np.random.default_rng(seed).integers(0, 256, (270, 480, 3), dtype=np.uint8))
        for gray in (0, 127, 255):
            result = self.compare(np.full((270, 480, 3), gray, dtype=np.uint8))
            self.assertEqual(result["score"], 0)
            self.assertFalse(result["present"])

    def test_positive_template_shift_and_inversion(self):
        rgb = np.zeros((270, 480, 3), dtype=np.uint8)
        weights = np.asarray(reference._weights).reshape(12, 64)
        rgb[24:36, 18:82][weights > 0] = 255
        self.assertTrue(self.compare(rgb)["present"])
        self.assertFalse(self.compare(255-rgb)["present"])
        self.assertFalse(self.compare(np.roll(rgb, 30, axis=1))["present"])

    def test_nv12_matches_capture_conversion_with_padding_scaling_and_clipping(self):
        for width, height, pitch in ((480, 270, 512), (960, 540, 992), (1280, 720, 1280), (2, 2, 4)):
            with self.subTest(width=width, height=height, pitch=pitch):
                rng = np.random.default_rng(width)
                y = rng.integers(0, 256, (height, pitch), dtype=np.uint8)
                uv = rng.integers(0, 256, (height//2, pitch), dtype=np.uint8)
                sy = np.arange(270) * height // 270
                sx = np.arange(480) * width // 480
                luma = y[sy[:, None], sx[None, :]].astype(np.float64)
                u = uv[(sy//2)[:, None], ((sx//2)*2)[None, :]].astype(np.float64)-128
                v = uv[(sy//2)[:, None], ((sx//2)*2+1)[None, :]].astype(np.float64)-128
                rgb = np.stack((luma+1.402*v, luma-0.344*u-0.714*v, luma+1.772*u), axis=2).clip(0,255).astype(np.uint8)
                expected = self.compare(rgb)["score"]
                fixture = self.directory / "frame.nv12"
                fixture.write_bytes(y.tobytes() + uv.tobytes())
                result = self.run_harness("--nv12", fixture, width, height, pitch)
                self.assertAlmostEqual(result["score"], expected, delta=1e-9)

    def test_real_retained_frames_against_reference(self):
        directory = os.environ.get("PILL_PRIVATE_FIXTURES")
        candidates = list(Path(directory).glob("*.png")) if directory else []
        checked = 0
        for path in candidates:
            if path.exists():
                with Image.open(path) as image:
                    if image.size == (480, 270):
                        self.compare(np.asarray(image.convert("RGB")))
                        checked += 1
        if not checked:
            self.skipTest("No private retained 480x270 fixtures on this host")

    def test_invalid_geometry_and_bounded_allocation_free_benchmark(self):
        self.assertEqual(self.run_harness("--self-test"), {"self_test": True})
        fixture = self.directory / "black.rgb"
        fixture.write_bytes(bytes(480*270*3))
        result = self.run_harness(fixture, "--bench", 100)
        self.assertEqual(result["iterations"], 100)
        self.assertEqual(result["allocated_bytes"], 0)
        self.assertEqual(result["score"], 0)
        self.assertLess(result["elapsed_ms"], 5000)


if __name__ == "__main__":
    unittest.main()
