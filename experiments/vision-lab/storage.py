"""Local SQLite/PNG observation store; manual labels never come from native metadata."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import time
import uuid


class Store:
    def __init__(self, directory, retention_hours=48, max_bytes=512 * 1024**2):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / "frames").mkdir(exist_ok=True, mode=0o700)
        self.retention = min(float(retention_hours), 48) * 3600
        self.max_bytes = int(max_bytes)
        if self.retention <= 0 or self.max_bytes < 16 * 1024**2:
            raise ValueError("positive retention and storage cap >=16 MiB required")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "lab.sqlite3", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS samples (id TEXT PRIMARY KEY, received REAL, size INTEGER, record TEXT)")
        self.db.execute("CREATE INDEX IF NOT EXISTS sample_age ON samples(received)")
        self.db.execute("CREATE TABLE IF NOT EXISTS prototypes (id TEXT PRIMARY KEY, record TEXT)")
        self.db.commit()
        self.prune()

    def _bytes(self):
        return sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())

    def add(self, png, record):
        with self.lock:
            frame_id = uuid.uuid4().hex
            path = self.root / "frames" / (frame_id + ".png")
            received = time.time()
            expires = min(received + self.retention, record["timestamp_unix"] + self.retention,
                          record.get("metadata", {}).get("session_expires_unix", float("inf")))
            record = dict(record, frame_id=frame_id, received_unix=received,
                          expires_unix=expires,
                          image_path=str(path.relative_to(self.root)), manual_label=None,
                          label_source=None)
            path.write_bytes(png)
            try:
                self.db.execute("INSERT INTO samples VALUES (?,?,?,?)",
                                (frame_id, received, len(png), json.dumps(record, allow_nan=False)))
                self.db.commit()
            except Exception:
                path.unlink(missing_ok=True)
                raise
            self.prune()
            return record

    def get(self, frame_id):
        with self.lock:
            row = self.db.execute("SELECT record FROM samples WHERE id=?", (frame_id,)).fetchone()
            if not row:
                raise KeyError("sample not retained")
            return json.loads(row[0])

    def samples(self, limit=1000):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute(
                "SELECT record FROM samples ORDER BY received DESC LIMIT ?", (limit,))]

    def label(self, ids, label, note=""):
        if label not in ("ad", "program", "unknown") or not 1 <= len(ids) <= 1000:
            raise ValueError("label must be ad/program/unknown; supply 1..1000 frame_ids")
        with self.lock:
            rows = [self.get(frame_id) for frame_id in ids]
            for row in rows:
                row.update(manual_label=label, label_source="human", label_note=str(note)[:2000],
                           labelled_unix=time.time())
                self.db.execute("UPDATE samples SET record=? WHERE id=?", (json.dumps(row), row["frame_id"]))
            # Relabeling supporting evidence invalidates existing prototypes.
            for prototype in self.prototypes():
                if label != "ad" and set(ids).intersection(prototype["frame_ids"]):
                    self.db.execute("DELETE FROM prototypes WHERE id=?", (prototype["prototype_id"],))
            self.db.commit()
            return rows

    def prototypes(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute("SELECT record FROM prototypes")]

    def add_prototype(self, name, frame_ids):
        from PIL import Image
        from detector import fingerprint
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("name must be 1..100 characters")
        if not 3 <= len(frame_ids) <= 32 or len(set(frame_ids)) != len(frame_ids):
            raise ValueError("prototype requires 3..32 distinct frames")
        with self.lock:
            if len(self.prototypes()) >= 32:
                raise ValueError("prototype library limited to 32 sequences; delete an old prototype first")
            rows = [self.get(frame_id) for frame_id in frame_ids]
            if any(row["manual_label"] != "ad" or row["contamination"]["status"] != "clean" for row in rows):
                raise ValueError("all prototype frames must be clean and manually labelled ad")
            if len({row["session_id"] for row in rows}) != 1:
                raise ValueError("prototype frames must share one session")
            times = [row["timestamp_unix"] for row in rows]
            if any(b <= a or b - a > 6 for a, b in zip(times, times[1:])) or times[-1] - times[0] < 2:
                raise ValueError("frames must be chronological, span >=2 seconds, gaps <=6 seconds")
            points = []
            for row in rows:
                offset = row["timestamp_unix"] - times[0]
                if points and offset - points[-1]["offset"] < 1.0:
                    continue
                with Image.open(self.root / row["image_path"]) as image:
                    points.append({"offset": offset,
                                   "vector": fingerprint(image).tolist()})
            if len(points) < 3:
                raise ValueError("prototype needs three frames spaced at least one second apart")
            prototype = {"prototype_id": uuid.uuid4().hex, "name": name.strip(),
                         "frame_ids": frame_ids, "points": points, "label_source": "human",
                         "created_unix": time.time()}
            payload = json.dumps(prototype)
            if self._bytes() + len(payload) > self.max_bytes:
                raise ValueError("storage cap reached")
            self.db.execute("INSERT INTO prototypes VALUES (?,?)", (prototype["prototype_id"], payload))
            self.db.commit()
            return prototype

    def delete_prototype(self, prototype_id):
        with self.lock:
            self.db.execute("DELETE FROM prototypes WHERE id=?", (prototype_id,))
            self.db.commit()
            self.db.execute("VACUUM")

    def clear(self):
        with self.lock:
            self.db.execute("DELETE FROM samples")
            self.db.execute("DELETE FROM prototypes")
            self.db.commit()
            for path in (self.root / "frames").glob("*.png"):
                path.unlink()
            for directory in ("artifacts", "experiments"):
                path = self.root / directory
                if path.is_symlink():
                    path.unlink()
                elif path.exists():
                    shutil.rmtree(path)
            self.db.execute("VACUUM")

    def prune(self, now=None):
        with self.lock:
            current = time.time() if now is None else now
            cutoff = current - self.retention
            deleted = False
            rows = self.db.execute("SELECT id,received,size,record FROM samples ORDER BY received").fetchall()
            remaining = len(rows)
            total = self._bytes()
            for frame_id, received, size, payload in rows:
                expires = json.loads(payload).get("expires_unix", received + self.retention)
                if received >= cutoff and expires > current and total <= self.max_bytes and remaining <= 100000:
                    continue
                (self.root / "frames" / (frame_id + ".png")).unlink(missing_ok=True)
                self.db.execute("DELETE FROM samples WHERE id=?", (frame_id,))
                total -= size
                remaining -= 1
                deleted = True
            self.db.commit()
            # Recover orphan captures after a process interrupted an insert.
            known = {row[0] for row in self.db.execute("SELECT id FROM samples")}
            for prototype in self.prototypes():
                if not set(prototype["frame_ids"]).issubset(known):
                    self.db.execute("DELETE FROM prototypes WHERE id=?", (prototype["prototype_id"],))
                    deleted = True
            self.db.commit()
            if deleted:
                self.db.execute("VACUUM")
            # Derived exports/models cannot outlive their supporting observations.
            # Conservatively drop derived files whenever any source rows expire or
            # are evicted; also honor explicit artifact expiry where supplied.
            for directory in ("artifacts", "experiments"):
                for path in (self.root / directory).rglob("*"):
                    if not path.is_file():
                        continue
                    expiry = path.stat().st_mtime + self.retention
                    if path.suffix == ".json" and path.stat().st_size < 16 * 1024**2:
                        try:
                            artifact = json.loads(path.read_text())
                            value = artifact.get("expires_unix") if isinstance(artifact, dict) else None
                            if isinstance(value, (int, float)):
                                expiry = min(expiry, value)
                        except (ValueError, OSError):
                            pass
                    if deleted or not known or current >= expiry or self._bytes() > self.max_bytes:
                        path.unlink()
            for path in (self.root / "frames").glob("*.png"):
                if path.stem not in known:
                    path.unlink()

    def status(self):
        with self.lock:
            return {"samples": self.db.execute("SELECT count(*) FROM samples").fetchone()[0],
                    "prototypes": self.db.execute("SELECT count(*) FROM prototypes").fetchone()[0],
                    "storage_bytes": self._bytes(), "storage_cap_bytes": self.max_bytes,
                    "retention_hours": self.retention / 3600}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export"])
    parser.add_argument("--data-dir", default=os.environ.get("LAB_DATA_DIR", "data"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    # Read-only export: does not initialize a Store or trigger retention pruning.
    connection = sqlite3.connect("file:" + str(Path(args.data_dir).resolve() / "lab.sqlite3") + "?mode=ro", uri=True)
    with open(args.output, "w", encoding="utf-8") as output:
        for row in connection.execute("SELECT record FROM samples ORDER BY received"):
            output.write(row[0] + "\n")
