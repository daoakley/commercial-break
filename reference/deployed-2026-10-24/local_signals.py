"""Cheap, deterministic observation features; none are generic ad verdicts."""

import array
import json
import math
from pathlib import Path
import statistics
import struct
import sys
import zlib


def rgb_rows(png):
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not PNG")
    offset, packed, spec = 8, [], None
    while offset + 12 <= len(png):
        n = struct.unpack_from(">I", png, offset)[0]
        kind, data = png[offset + 4:offset + 8], png[offset + 8:offset + 8 + n]
        if offset + n + 12 > len(png):
            raise ValueError("truncated PNG")
        if kind == b"IHDR":
            spec = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            packed.append(data)
        offset += n + 12
        if kind == b"IEND":
            break
    if spec is None or spec[:3] != (480, 270, 8) or spec[3] not in (2, 6) or spec[4:] != (0, 0, 0):
        raise ValueError("unsupported capture format")
    bpp = 3 if spec[3] == 2 else 4
    stride = 480 * bpp
    raw = zlib.decompressobj().decompress(b"".join(packed), (stride + 1) * 270 + 1)
    if len(raw) != (stride + 1) * 270:
        raise ValueError("invalid decompressed size")
    previous = bytearray(stride)
    for y in range(270):
        start = y * (stride + 1)
        filter_kind = raw[start]
        row = bytearray(raw[start + 1:start + 1 + stride])
        if filter_kind not in range(5):
            raise ValueError("unsupported PNG filter")
        if filter_kind == 2:
            row = bytearray((a + b) & 255 for a, b in zip(row, previous))
        elif filter_kind:
            for i in range(stride):
                a = row[i - bpp] if i >= bpp else 0
                b = previous[i]
                c = previous[i - bpp] if i >= bpp else 0
                if filter_kind == 1:
                    predictor = a
                elif filter_kind == 3:
                    predictor = (a + b) // 2
                else:
                    p = a + b - c
                    da, db, dc = abs(p - a), abs(p - b), abs(p - c)
                    predictor = a if da <= db and da <= dc else b if db <= dc else c
                row[i] = (row[i] + predictor) & 255
        yield row, bpp
        previous = row


def visual_features(png):
    """Fixed-size spatial sample preserves central scene vs border differences."""
    grid, card_pixels, dark, margins = [], [], [], []
    for y, (row, bpp) in enumerate(rgb_rows(png)):
        def luma(x):
            at = x * bpp
            return (77 * row[at] + 150 * row[at + 1] + 29 * row[at + 2]) >> 8
        if y % 10 == 5:
            grid.extend(luma(x) for x in range(5, 480, 10))
        if 108 <= y < 144 and y % 2 == 0:
            card_pixels.extend(int(luma(x) > 50) for x in range(130, 350, 2))
        if y % 20 == 0 and not 100 <= y <= 150:
            dark.extend(luma(x) < 16 for x in range(20, 460, 20))
            margins.extend(luma(x) < 16 for x in (20, 40, 440, 460))
    return {"grid": grid, "mean_luma": sum(grid) / len(grid),
            "black_fraction": sum(v < 16 for v in grid) / len(grid),
            "card_pixels": card_pixels, "outer_dark_fraction": sum(dark) / len(dark),
            "card_margin_dark_fraction": sum(margins) / len(margins)}


_COVER_MASK = None
def own_card(features):
    global _COVER_MASK
    if _COVER_MASK is None:
        _COVER_MASK = json.loads(Path(__file__).with_name("cover_mask.json").read_text())["mask"]
    bits = features["card_pixels"]
    if len(bits) != len(_COVER_MASK) or features.get("card_margin_dark_fraction", features["outer_dark_fraction"]) < .98:
        return False
    union = sum(a or b for a, b in zip(bits, _COVER_MASK))
    intersection = sum(a and b for a, b in zip(bits, _COVER_MASK))
    return union > 100 and intersection / union >= .94


def visual_change(previous, current):
    if previous is None:
        return {"scene_delta": 0, "center_delta": 0, "border_delta": 0,
                "brightness_delta": 0, "scene_cut_candidate": False,
                "overlay_only_candidate": False}
    center, border = [], []
    for i, (a, b) in enumerate(zip(previous["grid"], current["grid"])):
        x, y = i % 48, i // 48
        (center if 9 <= x < 39 and 5 <= y < 22 else border).append(abs(a - b) / 255)
    c, b = statistics.mean(center), statistics.mean(border)
    delta = statistics.mean([abs(a - b) / 255 for a, b in zip(previous["grid"], current["grid"])])
    return {"scene_delta": round(delta, 3), "center_delta": round(c, 3),
            "border_delta": round(b, 3),
            "brightness_delta": round(abs(current["mean_luma"] - previous["mean_luma"]), 1),
            "scene_cut_candidate": delta > .22 and c > .20,
            "overlay_only_candidate": b > .15 and c < .06}


def audio_features(pcm, rate=48000):
    """Internal 48k stereo S16 PCM. Discarded after feature extraction."""
    if not pcm or len(pcm) % 4 or len(pcm) > rate * 4 * 3:
        raise ValueError("expected at most three seconds of complete stereo PCM")
    values = array.array("h")
    values.frombytes(pcm)
    if sys.byteorder != "little":
        values.byteswap()
    mono = [(values[i] + values[i + 1]) / 65536 for i in range(0, len(values), 12)]
    mean = statistics.mean(mono)
    mono = [v - mean for v in mono]
    rms = math.sqrt(sum(v * v for v in mono) / len(mono))
    peak = max(abs(v) for v in mono)
    windows = [mono[i:i + 80] for i in range(0, len(mono) - 79, 80)]
    energies = [math.sqrt(sum(v * v for v in w) / len(w)) for w in windows]
    return {"duration_seconds": len(pcm) / (rate * 4),
            "rms_dbfs": round(20 * math.log10(max(rms, 1e-9)), 2),
            "crest_db": round(20 * math.log10(max(peak, 1e-9) / max(rms, 1e-9)), 2),
            "silence_fraction": round(sum(v < .003 for v in energies) / max(1, len(energies)), 3),
            "zero_crossing_rate": round(sum(a * b < 0 for a, b in zip(mono, mono[1:])) / max(1, len(mono) - 1), 3),
            "controls_mute": False}
