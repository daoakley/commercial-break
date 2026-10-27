"""Observation-only continuity for a recently confirmed ad's bottom graphic.

This is a matcher, not an ad classifier. It cannot operate playback controls.
Call ``advance`` for EVERY metadata event, including frames without images.
Only a fresh, clean, same-session positive from the existing strict Samsung
validator may call ``seed``. A matcher hit must never seed or renew itself.
"""
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


@dataclass
class Anchor:
    captured_at: float
    available_at: float
    session: str
    patch: np.ndarray


class BannerMemory:
    MAX_AGE = 120.0
    MAX_TEACHER_DELAY = 8.0
    CAPACITY = 32

    def __init__(self):
        self.anchors = []
        self.session = None
        self.last_at = None

    @staticmethod
    def patch(rgb):
        rgb = np.asarray(rgb, dtype=np.uint8)
        if rgb.shape != (270, 480, 3):
            return None
        return rgb[235:270, 30:450].copy()

    @staticmethod
    def useful(patch):
        if patch is None or float(patch.std()) < 15:
            return False
        gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150) > 0
        return all(edges[:, x:x + 140].mean() >= 0.005 for x in (0, 140, 280))

    @staticmethod
    def match(first, second):
        error = np.mean(np.abs(first.astype(np.int16) - second.astype(np.int16)))
        if error > 15:
            return False
        correlation = cv2.matchTemplate(first, second, cv2.TM_CCOEFF_NORMED)[0, 0]
        return float(correlation) >= 0.95

    def advance(self, at, session):
        """Apply reset/expiry even when no image is available to classify."""
        if self.session != session or (self.last_at is not None and at < self.last_at):
            self.anchors.clear()
        self.session = session
        self.last_at = at
        self.anchors = [
            anchor for anchor in self.anchors
            if 0 <= at - anchor.captured_at <= self.MAX_AGE
            and anchor.session == session
        ]

    def query(self, rgb, at, session):
        self.advance(at, session)
        patch = self.patch(rgb)
        return self.useful(patch) and any(
            anchor.available_at <= at and self.match(anchor.patch, patch)
            for anchor in self.anchors
        )

    def seed(self, rgb, at, session, verified_positive=False, clean=False,
             available_at: Optional[float] = None):
        """Record a trusted positive after its response, never a local match.

        ``at`` is capture time; ``available_at`` is Samsung response/acceptance
        time. Future responses cannot influence earlier query frames.
        Verification includes exact capture identity and current session; the
        caller must use the application's existing strict Samsung validator.
        """
        available_at = at if available_at is None else available_at
        if not verified_positive or not clean:
            return False
        if not 0 <= available_at - at <= self.MAX_TEACHER_DELAY:
            return False
        if self.session is not None and self.session != session:
            return False
        patch = self.patch(rgb)
        if not self.useful(patch):
            return False
        if self.session is None:
            self.session = session
            self.last_at = at
        self.anchors.append(Anchor(at, available_at, session, patch))
        self.anchors = self.anchors[-self.CAPACITY:]
        return True
