"""Bounded context with provenance. Timing predictions never order a mute."""

from dataclasses import dataclass, field
import statistics


CATEGORIES = {
    "sports": "Scoreboards, tickers, sponsor logos, replays and in-game promos are normal. A banner or logo alone is not an ad. Preserve live action in split-screen advertising.",
    "news": "Lower thirds, tickers, station logos, websites and branded reports are normal. Distinguish a full-screen external sales pitch from editorial coverage.",
    "movie": "Abrupt scene, lighting, actor and aspect-ratio changes can occur within the film. A new scene or scheduled film is not an ad without promotional evidence.",
    "series": "Opening titles, credits, recaps and scene changes are normal. A new episode may begin within the same app.",
    "documentary": "Products, factories, interviews, maps and company names can be editorial content. Require a distinct promotional segment.",
    "kids": "Bright colors, toys and animated characters can be normal content. Brightness and rapid cuts alone cannot distinguish an ad.",
    "music": "Music videos can have rapid edits, graphics and logos throughout. Require a clear standalone pitch.",
    "unknown": "Category is not established. Do not infer advertising solely from scene changes, brightness, logos or missing previous-show features.",
}
PRESENTATIONS = {"program", "full_screen_ad", "in_program_promotion", "split_screen", "menu", "own_card", "unknown"}


def prediction(values, minimum=3):
    """A deliberately broad observed interval, not a countdown guarantee."""
    if len(values) < minimum:
        return None
    median = statistics.median(values)
    mad = statistics.median(abs(v - median) for v in values)
    if median <= 0 or mad > median * .25:
        return None
    margin = max(5.0, mad * 3, median * .15)
    return {"median_seconds": round(median, 1),
            "range_seconds": [round(max(0, median - margin), 1), round(median + margin, 1)],
            "samples": len(values), "source": "observed_transitions", "controls_mute": False}


@dataclass
class ViewingContext:
    epoch: int = 0
    category: str = "unknown"
    candidate_category: str = "unknown"
    category_votes: int = 0
    program_name: str = ""
    name_confidence: float = 0
    first_seen: float = 0
    last_ad_observed: float = 0
    break_start: float = 0
    last_break_end: float = 0
    starts: list = field(default_factory=list)
    durations: list = field(default_factory=list)
    active_break: bool = False
    can_start_break: bool = True

    def reset(self):
        fresh = ViewingContext(epoch=self.epoch + 1)
        self.__dict__.update(fresh.__dict__)

    def observe(self, verdict, at, muted, *, is_error=False):
        if is_error:
            # A fail-open release is not evidence that a broadcast break ended.
            self.active_break = False
            self.can_start_break = False
            return
        if verdict.label == "program" and verdict.confidence >= .7:
            if not muted:
                self.can_start_break = True
            if not self.first_seen:
                self.first_seen = at
            if verdict.program:
                self.program_name = verdict.program[:180]
                self.name_confidence = verdict.confidence
            category = getattr(verdict, "category", "unknown")
            if category in CATEGORIES and category != "unknown":
                self.category_votes = self.category_votes + 1 if category == self.candidate_category else 1
                self.candidate_category = category
                if self.category_votes >= 2:
                    self.category = category
        if verdict.label == "ad" and verdict.confidence >= .7:
            self.last_ad_observed = at
        if muted and not self.active_break and self.can_start_break:
            self.break_start = at
            self.starts = (self.starts + [at])[-12:]
            self.active_break = True
            self.can_start_break = False
        elif self.active_break and not muted:
            if verdict.label == "program" and verdict.confidence >= .7:
                duration = at - self.break_start
                if 5 <= duration <= 900:
                    self.durations = (self.durations + [duration])[-12:]
                self.last_break_end = at
            self.active_break = False

    def snapshot(self, now, metadata):
        gaps = [b - a for a, b in zip(self.starts, self.starts[1:]) if 60 <= b - a <= 3600]
        cadence = prediction(gaps)
        duration = prediction(self.durations)
        next_start = None
        expected_end = None
        if cadence and self.starts and not self.active_break:
            bounds = [self.starts[-1] + v for v in cadence["range_seconds"]]
            if bounds[1] >= now:
                next_start = {"unix_range": bounds, **cadence}
        if duration and self.active_break:
            bounds = [self.break_start + v for v in duration["range_seconds"]]
            if bounds[1] >= now:
                expected_end = {"unix_range": bounds, **duration}
        confirmed_title = str(metadata.get("title") or "")[:180]
        return {
            "epoch": self.epoch,
            "show": {"name": confirmed_title or self.program_name or None,
                     "source": "supplied_metadata" if confirmed_title else "vision_inference" if self.program_name else "unknown",
                     "confidence": None if confirmed_title else self.name_confidence or None},
            "channel": {"name": metadata.get("channel") or None,
                        "source": "supplied_metadata" if metadata.get("channel") else "unknown"},
            "category": {"value": self.category, "source": "repeated_vision_inference"},
            "category_expectations": CATEGORIES[self.category],
            "program_first_observed_unix": self.first_seen or None,
            "actual_broadcast_start_unix": None,
            "seconds_since_program_observed": round(now - self.first_seen, 1) if self.first_seen else None,
            "last_ad_observed_unix": self.last_ad_observed or None,
            "last_break_end_unix": self.last_break_end or None,
            "observed_break_start_unix": self.break_start if self.active_break else None,
            "predicted_next_break": next_start,
            "predicted_break_end": expected_end,
            "predicted_ad_sequence": None,
            "timing_caveat": "Observation times include detection delay. Predictions request checks; they never prove an ad or keep the TV muted.",
        }
