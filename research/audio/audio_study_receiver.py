"""Bounded local PCM study; audio never drives the TV mute decision."""

import collections
import csv
import hmac
import json
import math
import os
import re
import subprocess
import threading
import time
import wave
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from audio_boundary import find_candidates, rms_frames


TOKEN = os.environ["FRAME_TOKEN"]
OUT = Path(os.environ.get("AUDIO_STUDY_DIR", "./audio-study"))
OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
OUT.chmod(0o700)
SUMMARY = OUT / "seconds.csv"
BOUNDARIES = OUT / "boundaries.csv"
CLIPS = OUT / "transitions"
RING = collections.deque(maxlen=3)
PENDING = []
LOCK = threading.Lock()
LOG_PROCESS = None
CURRENT_VERDICT = ("", "", 0.0)
LAST_PROGRAM_SAVE = 0.0
LAST_AD_SAVE = 0.0
CHUNK_SECONDS = int(os.environ.get("AUDIO_CHUNK_SECONDS", "10"))
if CHUNK_SECONDS not in {2, 3, 10}:
    raise ValueError("AUDIO_CHUNK_SECONDS must be 2, 3, or 10")
FINGERPRINT_SHADOW = None
if os.environ.get("AUDIO_FINGERPRINT_LIBRARY"):
    from fingerprint_shadow import FingerprintShadow
    FINGERPRINT_SHADOW = FingerprintShadow(
        os.environ["AUDIO_FINGERPRINT_LIBRARY"], OUT / "fingerprint_scores.csv")


def stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="milliseconds")


def save_wav(path, chunks):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(b"".join(chunks))
    path.chmod(0o600)


def watch_detector():
    global LOG_PROCESS, CURRENT_VERDICT
    command = ["docker", "compose", "--env-file",
               os.environ.get("DETECTOR_ENV", str(Path(__file__).resolve().parents[2]/".env")),
               "logs", "--follow", "--timestamps", "--since", "1s", "detector"]
    process = subprocess.Popen(command,
                               cwd=os.environ.get("DETECTOR_PROJECT", str(Path(__file__).resolve().parents[2])),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, bufsize=1)
    LOG_PROCESS = process
    previous = None
    for line in process.stdout:
        match = re.search(r"decision=(MUTE|UNMUTE) label=(\w+) confidence=([0-9.]+)", line)
        if not match:
            continue
        action, label, confidence = match.groups()
        with LOCK:
            CURRENT_VERDICT = (action, label, float(confidence))
        if previous is not None and action != previous:
            with LOCK:
                PENDING.append({"name": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                                + "-" + action.lower(),
                                "pre": list(RING)[-2:], "post": [],
                                "label": label, "confidence": confidence})
            print(f"transition {action} label={label} confidence={confidence}", flush=True)
        previous = action
    error = process.stderr.read().strip()
    if error:
        print(f"detector log watcher stopped: {error[:200]}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        global LAST_PROGRAM_SAVE, LAST_AD_SAVE
        if self.path != "/pcm" or not hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + TOKEN
        ):
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            start = float(self.headers.get("X-Capture-Start-Unix", "0"))
        except ValueError:
            self.send_error(400)
            return
        if size != 48000 * 4 * CHUNK_SECONDS or not 0 < start <= time.time() + 60:
            self.send_error(400)
            return
        raw = self.rfile.read(size)
        if len(raw) != size:
            self.send_error(400)
            return
        if FINGERPRINT_SHADOW is not None:
            try:
                match = FINGERPRINT_SHADOW.observe(raw, start)
                if match is not None and match[0] >= .90:
                    print(f"shadow fingerprint candidate {match[1]} score={match[0]:.4f}",
                          flush=True)
            except Exception as error:
                print(f"shadow fingerprint observation failed: {type(error).__name__}",
                      flush=True)
        frames = rms_frames(raw)
        candidates = find_candidates(raw, base_offset_seconds=start)
        with SUMMARY.open("a", newline="") as file:
            writer = csv.writer(file)
            for second in range(CHUNK_SECONDS):
                part = frames[second * 100:(second + 1) * 100]
                writer.writerow([stamp(start + second),
                                 round(math.sqrt(sum(x * x for x in part) / len(part)), 1),
                                 round(min(part), 1),
                                 sum(x <= 25 for x in part)])
        with BOUNDARIES.open("a", newline="") as file:
            writer = csv.writer(file)
            for candidate in candidates:
                writer.writerow([stamp(candidate.offset_seconds), candidate.silence_ms,
                                 candidate.before_rms, candidate.during_rms,
                                 candidate.after_rms, candidate.depth])
        completed = []
        with LOCK:
            RING.append(raw)
            for item in PENDING:
                item["post"].append(raw)
                if len(item["post"]) >= 2:
                    completed.append(item)
            for item in completed:
                PENDING.remove(item)
        for item in completed:
            base = CLIPS / item["name"]
            save_wav(Path(str(base) + "-before.wav"), item["pre"])
            save_wav(Path(str(base) + "-after.wav"), item["post"])
            print(f"saved {item['name']} audio clips", flush=True)
        with LOCK:
            action, label, confidence = CURRENT_VERDICT
            keep_program = (action == "UNMUTE" and label == "program"
                            and confidence >= .9 and start - LAST_PROGRAM_SAVE >= 180)
            keep_ad = (action == "MUTE" and label == "ad"
                       and confidence >= .9 and start - LAST_AD_SAVE >= 60)
            if keep_program:
                LAST_PROGRAM_SAVE = start
            if keep_ad:
                LAST_AD_SAVE = start
        if keep_program:
            base = OUT / "program-samples" / str(int(start))
            save_wav(Path(str(base) + ".wav"), [raw])
            metadata = Path(str(base) + ".json")
            metadata.write_text(json.dumps({"start_unix": start, "label": label,
                                            "confidence": confidence}))
            metadata.chmod(0o600)
        if keep_ad:
            base = OUT / "ad-samples" / str(int(start))
            save_wav(Path(str(base) + ".wav"), [raw])
            metadata = Path(str(base) + ".json")
            metadata.write_text(json.dumps({"start_unix": start, "label": label,
                                            "confidence": confidence}))
            metadata.chmod(0o600)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        print(f"chunk {stamp(start)} candidate_boundaries={len(candidates)}", flush=True)


def main():
    if not SUMMARY.exists():
        with SUMMARY.open("w", newline="") as file:
            csv.writer(file).writerow(["at_utc", "rms", "min_10ms_rms", "quiet_10ms_frames"])
    if not BOUNDARIES.exists():
        with BOUNDARIES.open("w", newline="") as file:
            csv.writer(file).writerow(["at_utc", "silence_ms", "before_rms",
                                       "during_rms", "after_rms", "depth"])
    threading.Thread(target=watch_detector, daemon=True).start()
    server = HTTPServer((os.environ.get("AUDIO_STUDY_HOST", "127.0.0.1"),
                         int(os.environ.get("AUDIO_STUDY_PORT", "28975"))), Handler)
    server.timeout = 1
    duration = int(os.environ.get("AUDIO_STUDY_DURATION", "1800"))
    print(f"audio study receiver ready for {duration} seconds", flush=True)
    end = time.time() + duration
    while time.time() < end:
        server.handle_request()
    server.server_close()
    if LOG_PROCESS is not None and LOG_PROCESS.poll() is None:
        LOG_PROCESS.terminate()
    print("audio study receiver stopped", flush=True)


if __name__ == "__main__":
    main()
