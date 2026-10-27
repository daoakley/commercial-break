import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image

from detector import Detector, fingerprint
from server import Application, make_handler, validated_metadata
from storage import Store


def scene(seed):
    # Distinct color texture per image; avoid testing against static scenes only.
    pixels = np.random.default_rng(seed).integers(0, 256, (18, 32, 3), dtype=np.uint8)
    return Image.fromarray(pixels).resize((480, 270), Image.Resampling.NEAREST)


def encoded(image):
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def metadata(timestamp, session="test", status="clean"):
    return {"timestamp_unix": timestamp, "session_id": session,
            "contamination": {"status": status, "reasons": []}}


def prototype(images):
    return {"prototype_id": "test", "name": "human labelled sequence",
            "points": [{"offset": i, "vector": fingerprint(image).tolist()}
                       for i, image in enumerate(images)]}


class DetectionTests(unittest.TestCase):
    def test_sequence_needs_order_time_and_multiple_frames(self):
        images = [scene(i) for i in range(3)]
        refs = [prototype(images)]
        detector = Detector()
        self.assertEqual(detector.observe(images[0], metadata(0), refs)["decision"], "unknown")
        self.assertEqual(detector.observe(images[1], metadata(1), refs)["decision"], "unknown")
        result = detector.observe(images[2], metadata(2), refs)
        self.assertEqual(result["decision"], "ad")
        self.assertEqual(result["evidence"][0]["type"], "human_confirmed_ad_sequence")
        detector.reset()
        for i, image in enumerate(reversed(images)):
            self.assertEqual(detector.observe(image, metadata(i), refs)["decision"], "unknown")
        detector.reset()
        for i, image in enumerate(images):
            self.assertEqual(detector.observe(image, metadata(i * .1), refs)["decision"], "unknown")
        detector.reset()
        for image, stamp in ((images[0], 0), (scene(9), .5), (images[1], 1), (scene(10), 1.5)):
            detector.observe(image, metadata(stamp), refs)
        self.assertEqual(detector.observe(images[2], metadata(2), refs)["decision"], "ad")

    def test_session_contamination_and_duplicate_timestamp_reset(self):
        images = [scene(i) for i in range(3)]
        refs = [prototype(images)]
        for last in (metadata(2, "new"), metadata(2, status="contaminated"), metadata(1)):
            detector = Detector()
            detector.observe(images[0], metadata(0), refs)
            detector.observe(images[1], metadata(1), refs)
            self.assertEqual(detector.observe(images[2], last, refs)["decision"], "unknown")
        detector = Detector()
        for i in range(3):
            self.assertEqual(detector.observe(images[0], metadata(i), [prototype([images[0]] * 3)])["decision"], "unknown")

    def test_badge_requires_exact_profile_and_two_frames(self):
        template = json.loads(Path(__file__).with_name("sponsored_template.json").read_text())
        pixels = np.zeros((270, 480, 3), dtype=np.uint8)
        weights = np.asarray(template["weights"]).reshape(12, 64)
        pixels[24:36, 18:82][weights > 0] = 255
        image = Image.fromarray(pixels)
        detector = Detector()
        for t in (0, 1):
            self.assertEqual(detector.observe(image, metadata(t), [])["decision"], "unknown")
        detector.reset()
        first = dict(metadata(0), ui_profile="youtube_tv_480x270")
        second = dict(metadata(1), ui_profile="youtube_tv_480x270")
        self.assertEqual(detector.observe(image, first, [])["decision"], "unknown")
        self.assertEqual(detector.observe(image, second, [])["decision"], "ad")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name, max_bytes=16 * 1024**2)

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def add(self, i=0, **extra):
        record = dict(metadata(time.time() - 3 + i), source="test", metadata={},
                      decision="unknown", evidence=[])
        record.update(extra)
        return self.store.add(encoded(scene(i)), record)

    def test_manual_provenance_required_and_relabelling_invalidates(self):
        rows = [self.add(i) for i in range(3)]
        ids = [row["frame_id"] for row in rows]
        with self.assertRaises(ValueError):
            self.store.add_prototype("ad", ids)
        self.store.label(ids, "ad")
        self.store.add_prototype("ad", ids)
        self.assertEqual(len(self.store.prototypes()), 1)
        self.store.label([ids[1]], "program")
        self.assertEqual(self.store.prototypes(), [])
        self.assertEqual(self.store.get(ids[1])["label_source"], "human")

    def test_retention_expiry_and_clear_remove_artifacts(self):
        record = self.add(metadata={"session_expires_unix": time.time() + 1})
        self.store.prune(time.time() + 2)
        with self.assertRaises(KeyError):
            self.store.get(record["frame_id"])
        record = self.add()
        self.store.prune(time.time() + 48 * 3600 + 1)
        self.assertEqual(self.store.samples(), [])
        self.add()
        artifacts = Path(self.temp.name) / "artifacts"
        artifacts.mkdir()
        (artifacts / "export.jsonl").write_text("{}")
        self.store.clear()
        self.assertFalse(artifacts.exists())
        self.assertEqual(list((Path(self.temp.name) / "frames").glob("*.png")), [])
        self.assertEqual(self.store.samples(), [])

    def test_cap_removes_oldest(self):
        record = dict(metadata(time.time()), metadata={})
        first = self.store.add(b"x" * (10 * 1024**2), record)
        second = self.store.add(b"y" * (10 * 1024**2), record)
        with self.assertRaises(KeyError):
            self.store.get(first["frame_id"])
        self.assertEqual(self.store.get(second["frame_id"])["frame_id"], second["frame_id"])
        self.assertLessEqual(self.store.status()["storage_bytes"], 16 * 1024**2)


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.app = Application(self.store, "test-secret-token-that-is-long-enough")
        self.server = HTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.db.close()
        self.temp.cleanup()

    def request(self, path, body=None, auth=True, method=None):
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer " + self.app.token
        request = Request(self.url + path, data=json.dumps(body).encode() if body is not None else None,
                          headers=headers, method=method)
        with urlopen(request, timeout=3) as response:
            return response.status, response.read()

    def test_auth_ingest_export_native_not_truth_clear(self):
        self.assertEqual(self.request("/health", auth=False)[0], 200)
        with self.assertRaises(HTTPError) as caught:
            self.request("/v1/status", auth=False)
        self.assertEqual(caught.exception.code, 401)
        body = {"image_base64": base64.b64encode(encoded(scene(5))).decode(),
                "metadata": dict(metadata(time.time()), native={"ad": True}, manual_label="ad")}
        code, raw = self.request("/v1/frames", body)
        record = json.loads(raw)
        self.assertEqual(code, 201)
        self.assertEqual(record["decision"], "unknown")
        self.assertIsNone(record["manual_label"])
        self.assertTrue(record["metadata"]["native"]["ad"])
        self.assertEqual(self.request("/v1/samples/" + record["frame_id"] + "/image")[0], 200)
        self.assertEqual(len(json.loads(self.request("/v1/export")[1])["samples"]), 1)
        self.request("/v1/labels", {"frame_ids": [record["frame_id"]], "label": "program"})
        self.request("/v1/data", method="DELETE")
        self.assertEqual(json.loads(self.request("/v1/status")[1])["samples"], 0)

    def test_bad_input_and_stale_capture(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/v1/samples", {"image_base64": "broken", "metadata": metadata(time.time())})
        self.assertEqual(caught.exception.code, 400)
        result = validated_metadata({"metadata": metadata(time.time() - 60)})
        self.assertEqual(result["contamination"]["status"], "clean")
        self.assertFalse(result["live_decision_eligible"])
        with self.assertRaises(ValueError):
            validated_metadata({"metadata": metadata(time.time() - 49 * 3600)})
        with self.assertRaises(ValueError):
            validated_metadata({"metadata": dict(metadata(time.time()), timestamp="2026-01-01T01:01:01")})

    def test_historical_ingest_preserves_label_eligibility(self):
        body = {"image_base64": base64.b64encode(encoded(scene(5))).decode(),
                "metadata": metadata(time.time() - 100)}
        record = json.loads(self.request("/v1/samples", body)[1])
        self.assertEqual(record["contamination"]["status"], "clean")
        self.assertEqual(record["decision"], "unknown")
        self.assertFalse(record["live_decision_eligible"])
        self.request("/v1/labels", {"frame_ids": [record["frame_id"]], "label": "ad"})
        self.assertEqual(self.store.get(record["frame_id"])["manual_label"], "ad")


if __name__ == "__main__":
    unittest.main()
