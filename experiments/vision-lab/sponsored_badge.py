"""Detect YouTube TV's fixed upper-left Sponsored pill in a 480x270 PNG.

This intentionally recognizes a specific app UI overlay, not arbitrary uses of
the word 'sponsored' in program footage. The PNG reference decoder uses the
standard library; the decoded-image fast path uses NumPy.
"""

import json
import os
import struct
import zlib

import numpy as np

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "sponsored_template.json")
with open(TEMPLATE_PATH, encoding="utf-8") as _file:
    _template = json.load(_file)
_weights = _template["weights"]
_image_weights = np.asarray(_weights, dtype=np.float64).reshape((12, 64))
THRESHOLD = 300.0


def score_image(image):
    """Same score as score(PNG), directly from a decoded 480x270 PIL image.

    Integer luma rounding and 3x3 neighborhoods match the reference decoder;
    alpha is ignored just as it is for RGBA PNG. Ordered Python reduction retains
    reference floating-point summation behavior, including threshold boundaries.
    """
    if image.size != (480, 270):
        raise ValueError("unsupported capture format")
    rgb = np.asarray(image.crop((17, 23, 83, 37)).convert("RGB"), dtype=np.int32)
    gray = (299 * rgb[:, :, 0] + 587 * rgb[:, :, 1] +
            114 * rgb[:, :, 2] + 500) // 1000
    surround = sum(gray[y:y + 12, x:x + 64] for y in range(3) for x in range(3))
    high_pass = gray[1:13, 1:65] - surround / 9.0
    total = 0
    for value in (high_pass * _image_weights).ravel().tolist():
        total += value
    return total / 1000.0


def _paeth(a, b, c):
    p = a + b - c
    da, db, dc = abs(p - a), abs(p - b), abs(p - c)
    return a if da <= db and da <= dc else b if db <= dc else c


def _top_left_gray(png):
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not PNG")
    chunks = []
    offset = 8
    width = height = color = depth = interlace = None
    while offset + 12 <= len(png):
        length = struct.unpack_from(">I", png, offset)[0]
        kind = png[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(png):
            raise ValueError("truncated PNG")
        data = png[offset + 8:offset + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", data)
        elif kind == b"IDAT":
            chunks.append(data)
        elif kind == b"IEND":
            break
        offset = end
    if (width, height, depth, interlace) != (480, 270, 8, 0) or color not in (2, 6):
        raise ValueError("unsupported capture format")
    bpp = 4 if color == 6 else 3
    stride = width * bpp
    needed = (stride + 1) * 38
    raw = zlib.decompressobj().decompress(b"".join(chunks), needed)
    if len(raw) != needed:
        raise ValueError("incomplete PNG rows")
    previous = bytearray(stride)
    gray = []
    for y in range(38):
        start = y * (stride + 1)
        filter_type = raw[start]
        row = bytearray(raw[start + 1:start + 1 + stride])
        if filter_type not in (0, 1, 2, 3, 4):
            raise ValueError("unsupported PNG filter")
        if filter_type:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                above = previous[i]
                upper_left = previous[i - bpp] if i >= bpp else 0
                predictor = (0 if filter_type == 0 else
                             left if filter_type == 1 else
                             above if filter_type == 2 else
                             (left + above) // 2 if filter_type == 3 else
                             _paeth(left, above, upper_left))
                row[i] = (row[i] + predictor) & 255
        gray.append([((299 * row[x * bpp] + 587 * row[x * bpp + 1] +
                       114 * row[x * bpp + 2] + 500) // 1000)
                     for x in range(17, 83)])
        previous = row
    return gray


def score(png):
    """Matched high-frequency badge score; ordinary footage is usually below 100."""
    gray = _top_left_gray(png)
    total = 0
    index = 0
    for y in range(24, 36):
        for x in range(1, 65):
            surround = sum(gray[yy][xx] for yy in (y - 1, y, y + 1)
                           for xx in (x - 1, x, x + 1))
            high_pass = gray[y][x] - surround / 9
            total += high_pass * _weights[index]
            index += 1
    return total / 1000


def present(png):
    try:
        return score(png) >= THRESHOLD
    except (ValueError, zlib.error, struct.error):
        return False
