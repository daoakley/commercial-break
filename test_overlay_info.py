import base64
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from server import Detector, Verdict
from viewing_context import ViewingContext


class OverlayInformationTests(unittest.TestCase):
    def test_unknown_title_and_insufficient_history_are_not_invented(self):
        c = ViewingContext()
        info = c.overlay_info(1000, {"app": "com.samsung.tv.cobalt-yttv"})
        self.assertEqual(info["title"], "")
        self.assertIsNone(info["typical_seconds"])
        self.assertIsNone(info["break_elapsed"])
        self.assertNotIn("countdown", info)

    def test_inferred_title_is_labeled_and_reset_clears_history(self):
        c = ViewingContext()
        c.observe(Verdict("program", .95, "Football", category="sports"), 100, False)
        c.observe(Verdict("ad", .95), 110, True)
        info = c.overlay_info(120, {})
        self.assertEqual(info["title"], "Likely: Football")
        self.assertEqual(info["break_elapsed"], 10)
        self.assertEqual(info["break_count"], 1)
        self.assertEqual({s[2] for s in info["timeline"]}, {"program", "covered"})
        c.reset()
        info = c.overlay_info(130, {})
        self.assertEqual(info["timeline"], [])
        self.assertEqual(info["title"], "")
        self.assertEqual(info["break_count"], 0)

    def test_outage_is_not_drawn_as_continuous_program(self):
        c = ViewingContext()
        c.observe(Verdict("program", .9), 100, False)
        c.observe(Verdict("ad", .9), 200, True)
        info = c.overlay_info(210, {})
        a, b = info["timeline"]
        self.assertLess(a[1], b[0])
        self.assertAlmostEqual(a[1] * 110, 30, places=1)

    def test_error_does_not_continue_covered_segment(self):
        c = ViewingContext()
        c.observe(Verdict("ad", .9), 100, True)
        c.observe(Verdict("uncertain"), 110, False, is_error=True)
        info = c.overlay_info(120, {})
        self.assertIsNone(info["break_elapsed"])
        self.assertEqual(info["timeline"][-1][2], "unknown")

    def test_payload_and_storage_are_bounded(self):
        c = ViewingContext()
        for i in range(3000):
            c.observe(Verdict("ad" if i % 2 else "program", .95, "é" * 180), i + 100, bool(i % 2))
        info = c.overlay_info(3100, {"channel": "é" * 120})
        payload = base64.b64encode(json.dumps(info, ensure_ascii=True, separators=(",", ":")).encode())
        self.assertLessEqual(len(c.timeline), 240)
        self.assertLessEqual(len(info["timeline"]), 80)
        self.assertLess(len(payload), 8192)

    def test_other_session_cannot_supply_card_context(self):
        class Vision:
            def classify(self, *args): return Verdict("program", .95, "New Show")
        d = Detector(Vision(), lambda: 1000)
        context = {"app": "com.samsung.tv.cobalt-yttv", "session": "new", "frame_sequence": "1"}
        d.process("tv", b"x", context)
        self.assertEqual(d.overlay_info("tv", dict(context, session="old")), {})
        self.assertEqual(d.overlay_info("tv", context)["title"], "Likely: New Show")

    def test_shell_transport_is_atomic_and_rejects_invalid_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            headers = root / "headers"
            value = {"version": 1, "title": "An ordinary title; $(not a command)"}
            encoded = base64.b64encode(json.dumps(value).encode()).decode()
            headers.write_text("X-Overlay-Info: " + encoded + "\r\n")
            # BSD base64 uses -D; this container-free test uses a portable decoder fake.
            decoder = root / "base64"
            decoder.write_text("#!/usr/bin/env python3\nimport base64,sys\nsys.stdout.buffer.write(base64.b64decode(sys.stdin.buffer.read(),validate=True))\n")
            decoder.chmod(0o700)
            script = 'STATE_DIR="$1"; PATH="$1:$PATH"; . "$2"; overlay_update_info "$3"'
            source = str(Path(__file__).with_name("tv-overlay.sh").resolve())
            subprocess.run(["/bin/sh", "-c", script, "sh", folder, source, str(headers)], check=True)
            self.assertEqual(json.loads((root / "overlay-info.json").read_text()), value)
            headers.write_text("X-Overlay-Info: invalid!\n")
            subprocess.run(["/bin/sh", "-c", script, "sh", folder, source, str(headers)], check=True)
            self.assertEqual(json.loads((root / "overlay-info.json").read_text()), value)

if __name__ == "__main__": unittest.main()
