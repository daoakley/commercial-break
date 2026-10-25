"""Offline acoustic repetition experiment; never controls the TV."""

import argparse
import wave
from pathlib import Path

import numpy as np


RATE = 8000
WINDOW = 2048
HOP = 512
BANDS = np.geomspace(90, 3800, 25)


def pcm_to_mono(pcm_bytes):
    pcm = np.frombuffer(pcm_bytes, dtype="<i2")
    mono = pcm.reshape(-1, 2).astype(np.float32).mean(axis=1) / 32768.0
    return mono[:len(mono) // 6 * 6].reshape(-1, 6).mean(axis=1)


def read_wav(path):
    with wave.open(str(path)) as source:
        if (source.getnchannels(), source.getframerate(), source.getsampwidth()) != (2, 48000, 2):
            raise ValueError("expected 48 kHz stereo S16 WAV")
        return pcm_to_mono(source.readframes(source.getnframes()))


def descriptors(signal):
    if len(signal) < WINDOW:
        return np.empty((0, 24), dtype=np.float32)
    windows = np.lib.stride_tricks.sliding_window_view(signal, WINDOW)[::HOP]
    power = np.abs(np.fft.rfft(windows * np.hanning(WINDOW), axis=1)) ** 2
    freqs = np.fft.rfftfreq(WINDOW, 1 / RATE)
    bands = []
    for low, high in zip(BANDS[:-1], BANDS[1:]):
        choice = (freqs >= low) & (freqs < high)
        bands.append(power[:, choice].mean(axis=1))
    matrix = np.log1p(np.stack(bands, axis=1))
    matrix -= matrix.mean(axis=1, keepdims=True)
    length = np.linalg.norm(matrix, axis=1, keepdims=True)
    return (matrix / np.maximum(length, 1e-8)).astype(np.float32)


def best_match(template, candidate):
    if len(candidate) < len(template):
        return None
    scores = []
    for start in range(len(candidate) - len(template) + 1):
        score = float(np.mean(np.sum(template * candidate[start:start + len(template)], axis=1)))
        scores.append(score)
    best = int(np.argmax(scores))
    return round(scores[best], 4), round(best * HOP / RATE, 3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("template")
    parser.add_argument("candidates", nargs="+")
    parser.add_argument("--offset", type=float, default=0.0)
    options = parser.parse_args()
    signal = read_wav(Path(options.template))
    beginning = int(options.offset * RATE)
    template = descriptors(signal[beginning:beginning + 5 * RATE])
    print(f"template {options.template}: {len(template)} descriptor frames")
    for path in options.candidates:
        result = best_match(template, descriptors(read_wav(Path(path))))
        print(path, result)


if __name__ == "__main__":
    main()
