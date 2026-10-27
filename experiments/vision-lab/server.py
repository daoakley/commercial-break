"""Loopback-only, bearer-authenticated local observation API. No TV control code."""
import base64
import binascii
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, urlparse

from PIL import Image, UnidentifiedImageError

from detector import Detector
from storage import Store

MAX_BODY = 8 * 1024**2
MAX_PIXELS = 3840 * 2160
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def validated_metadata(body):
    metadata = body.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    metadata = dict(metadata)
    for field in ("timestamp", "timestamp_unix", "session_id", "source", "contamination", "ui_profile"):
        if field in body:
            metadata[field] = body[field]
    session = metadata.get("session_id")
    if not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", session):
        raise ValueError("session_id is required (1..128 simple identifier characters)")
    raw = metadata.get("timestamp", metadata.get("timestamp_unix"))
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        timestamp = float(raw)
    elif isinstance(raw, str):
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timestamp requires timezone")
        timestamp = parsed.timestamp()
    else:
        raise ValueError("timestamp is required (ISO8601 with timezone or unix seconds)")
    if not math.isfinite(timestamp) or not 0 < timestamp < 32503680000:
        raise ValueError("invalid timestamp")
    if timestamp < time.time() - 48 * 3600:
        raise ValueError("capture exceeds maximum 48-hour retention")
    # Historical clean captures remain useful for labels/evaluation but cannot
    # advance real-time state or be silently relabelled as contaminated.
    contamination = metadata.get("contamination", {"status": "unknown", "reasons": []})
    if not isinstance(contamination, dict) or contamination.get("status") not in ("clean", "contaminated", "unknown"):
        raise ValueError("contamination.status must be clean/contaminated/unknown")
    reasons = contamination.get("reasons", [])
    if not isinstance(reasons, list) or not all(isinstance(reason, str) for reason in reasons):
        raise ValueError("contamination.reasons must be a list of strings")
    contamination = dict(contamination, reasons=list(reasons))
    metadata["live_decision_eligible"] = abs(timestamp - time.time()) <= 30
    if not metadata["live_decision_eligible"]:
        metadata["live_ineligible_reason"] = "historical_or_future_capture"
    expires = metadata.get("session_expires_unix")
    if expires is not None:
        if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not math.isfinite(expires):
            raise ValueError("session_expires_unix must be finite unix seconds")
        if expires <= time.time():
            raise ValueError("debug session expired")
    metadata.update(session_id=session, timestamp_unix=timestamp,
                    timestamp=datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                    source=str(metadata.get("source", "unspecified"))[:200], contamination=contamination)
    if len(json.dumps(metadata, allow_nan=False).encode()) > 64 * 1024:
        raise ValueError("metadata exceeds 64 KiB")
    return metadata


def decode_image(encoded):
    if not isinstance(encoded, str):
        raise ValueError("image_base64 must be a base64 string")
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > 5 * 1024**2:
        raise ValueError("compressed image exceeds 5 MiB")
    with Image.open(io.BytesIO(raw)) as source:
        if source.format not in ("PNG", "JPEG") or source.width * source.height > MAX_PIXELS:
            raise ValueError("PNG/JPEG up to 3840x2160 pixels required")
        if source.width < 32 or source.height < 18:
            raise ValueError("image too small")
        source.load()
        image = source.convert("RGB")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return image, out.getvalue()


class Application:
    def __init__(self, store, token):
        if not token or len(token) < 24:
            raise ValueError("LAB_TOKEN or LAB_TOKEN_FILE must contain >=24 characters")
        self.store, self.token, self.detector = store, token, Detector()
        self.started = time.time()

    def ingest(self, body):
        metadata = validated_metadata(body)
        image, png = decode_image(body.get("image_base64"))
        if len(png) > self.store.max_bytes // 2:
            raise ValueError("decoded image exceeds storage allocation")
        self.store.prune()
        result = self.detector.observe(image, metadata, self.store.prototypes())
        record = {key: metadata[key] for key in
                  ("timestamp", "timestamp_unix", "session_id", "source", "contamination")}
        record.update(metadata=metadata, live_decision_eligible=metadata["live_decision_eligible"], **result)
        return self.store.add(png, record)


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CommercialVisionLab/1"

        def log_message(self, format, *args):
            pass  # Neither captured metadata nor credentials belong in logs.

        def respond(self, status, value):
            payload = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def authorized(self):
            value = self.headers.get("Authorization", "")
            return hmac.compare_digest(value.encode(), ("Bearer " + app.token).encode())

        def route(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path.startswith("/v1/"):
                path = path[3:]
            if path == "/frames":
                path = "/samples"
            return path, parse_qs(parsed.query)

        def do_GET(self):
            path, query = self.route()
            if path == "/":
                payload = Path(__file__).with_name("review.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(payload)
                return
            if path == "/health":
                return self.respond(200, {"ok": True, "observation_only": True})
            if not self.authorized():
                return self.respond(401, {"error": "unauthorized"})
            try:
                if path == "/status":
                    return self.respond(200, {**app.store.status(), "observation_only": True,
                                              "uptime_seconds": int(time.time() - app.started),
                                              "active_session_id": app.detector.session})
                if path in ("/samples", "/export"):
                    limit = int(query.get("limit", ["1000"])[0])
                    if not 1 <= limit <= 10000:
                        raise ValueError("limit must be 1..10000; use storage.py for full export")
                    return self.respond(200, {"samples": app.store.samples(limit)})
                if path == "/prototypes":
                    return self.respond(200, {"prototypes": [{k: v for k, v in item.items() if k != "points"}
                                                              for item in app.store.prototypes()]})
                match = re.fullmatch(r"/samples/([0-9a-f]{32})/image", path)
                if match:
                    with app.store.lock:
                        record = app.store.get(match.group(1))
                        payload = (app.store.root / record["image_path"]).read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                return self.respond(404, {"error": "not found"})
            except (ValueError, KeyError, FileNotFoundError):
                return self.respond(400, {"error": "invalid request or expired sample"})

        def do_POST(self):
            if not self.authorized():
                return self.respond(401, {"error": "unauthorized"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    return self.respond(413, {"error": "body must be 1 byte..8 MiB"})
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("chunked requests unsupported")
                body = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
                if not isinstance(body, dict):
                    raise ValueError("body must be an object")
                path, _ = self.route()
                if path == "/samples":
                    return self.respond(201, app.ingest(body))
                if path == "/labels":
                    ids = body.get("frame_ids", [])
                    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
                        raise ValueError("frame_ids must be a list")
                    rows = app.store.label(ids, body.get("label"), body.get("note", ""))
                    app.detector.reset()
                    return self.respond(200, {"labelled": len(rows)})
                if path == "/prototypes":
                    ids = body.get("frame_ids", [])
                    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
                        raise ValueError("frame_ids must be a list")
                    prototype = app.store.add_prototype(body.get("name"), ids)
                    app.detector.reset()
                    return self.respond(201, {k: v for k, v in prototype.items() if k != "points"})
                if path == "/sessions/reset":
                    app.detector.reset()
                    return self.respond(200, {"reset": True})
                if path == "/clear":
                    app.store.clear()
                    app.detector.reset()
                    return self.respond(200, {"cleared": True})
                return self.respond(404, {"error": "not found"})
            except (ValueError, TypeError, KeyError, binascii.Error, UnidentifiedImageError,
                    Image.DecompressionBombError, OSError) as error:
                return self.respond(400, {"error": str(error)[:240]})

        def do_DELETE(self):
            if not self.authorized():
                return self.respond(401, {"error": "unauthorized"})
            path, _ = self.route()
            if path == "/data":
                app.store.clear()
                app.detector.reset()
                return self.respond(200, {"cleared": True})
            match = re.fullmatch(r"/prototypes/([0-9a-f]{32})", path)
            if match:
                app.store.delete_prototype(match.group(1))
                app.detector.reset()
                return self.respond(200, {"deleted": True})
            return self.respond(404, {"error": "not found"})

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

    return Handler


def main():
    token = os.environ.get("LAB_TOKEN", "")
    if os.environ.get("LAB_TOKEN_FILE"):
        token = Path(os.environ["LAB_TOKEN_FILE"]).read_text().strip()
    store = Store(os.environ.get("LAB_DATA_DIR", "/data"),
                  retention_hours=min(float(os.environ.get("LAB_RETENTION_HOURS", "48")), 48),
                  max_bytes=int(os.environ.get("LAB_STORAGE_CAP_BYTES", str(512 * 1024**2))))
    app = Application(store, token)
    # 0.0.0.0 is solely for container's network namespace; compose publishes loopback.
    host = os.environ.get("LAB_BIND", "127.0.0.1")
    if host not in ("127.0.0.1", "0.0.0.0"):
        raise ValueError("LAB_BIND must be loopback or container wildcard")
    server = HTTPServer((host, int(os.environ.get("LAB_PORT", "8795"))), make_handler(app))
    stop = threading.Event()
    def maintenance():
        while not stop.wait(30):
            store.prune()
    threading.Thread(target=maintenance, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
