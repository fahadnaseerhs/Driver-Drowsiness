"""System-level metrics. One implementation, so every report is comparable.

The guide grades "Experimentation & Quantitative Evaluation" at 25% of the
sub-group mark, and the Figma KPIs are F1, false-positive rate and alert latency.
Those are defined here rather than recomputed differently in five notebooks.

EVENT-LEVEL, NOT FRAME-LEVEL
---------------------------
Frame-level accuracy is misleading for this problem. A system that is 97% correct
per frame can still miss every microsleep, because closed-eye frames are rare. A
detector that always says "awake" would score well on frames and be worthless.

What matters is: did we raise an alarm during each genuine drowsy episode, and how
many alarms did we raise when nothing was happening. So the primary metrics here
match episodes, not frames.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EventMetrics:
    """Episode-level detection performance."""

    true_positives: int = 0            # ground-truth episodes with an alarm
    false_negatives: int = 0           # ground-truth episodes missed
    false_positives: int = 0           # alarms with no ground-truth episode
    latencies_s: list[float] = field(default_factory=list)   # alarm time - episode start

    @property
    def recall(self) -> float:
        """Of the real drowsy episodes, what fraction did we catch? Misses are
        the safety-critical failure."""
        d = self.true_positives + self.false_negatives
        return self.true_positives / d if d else 0.0

    @property
    def precision(self) -> float:
        """Of the alarms we raised, what fraction were real?"""
        d = self.true_positives + self.false_positives
        return self.true_positives / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def mean_latency_s(self) -> float:
        return sum(self.latencies_s) / len(self.latencies_s) if self.latencies_s else 0.0

    def as_dict(self) -> dict:
        return {
            "true_positives": self.true_positives,
            "false_negatives": self.false_negatives,
            "false_positives": self.false_positives,
            "recall": round(self.recall, 4),
            "precision": round(self.precision, 4),
            "f1": round(self.f1, 4),
            "mean_alert_latency_s": round(self.mean_latency_s, 3),
            "max_alert_latency_s": round(max(self.latencies_s), 3) if self.latencies_s else None,
        }


def to_intervals(timestamps: list[float], flags: list[bool],
                 max_gap_s: float = 0.2) -> list[tuple[float, float]]:
    """Collapse a boolean track into [start, end] intervals, bridging tiny gaps.

    The gap tolerance matters: an alarm that drops for one frame and comes back is
    one alarm, not two, and counting it as two would wrongly inflate the false
    positive count.
    """
    out: list[tuple[float, float]] = []
    start = prev = None
    for t, f in zip(timestamps, flags, strict=False):
        if f:
            if start is None:
                start = t
            elif prev is not None and (t - prev) > max_gap_s:
                out.append((start, prev))
                start = t
            prev = t
        elif start is not None and prev is not None and (t - prev) > max_gap_s:
            out.append((start, prev))
            start = prev = None
    if start is not None and prev is not None:
        out.append((start, prev))
    return out


def score_events(
    ground_truth: list[tuple[float, float]],
    predicted: list[tuple[float, float]],
    tolerance_s: float = 1.0,
) -> EventMetrics:
    """Match predicted alarm intervals against ground-truth drowsy episodes.

    A ground-truth episode counts as detected if a predicted alarm overlaps it or
    begins within ``tolerance_s`` after it ends -- the system is allowed a moment to
    accumulate evidence, which is inherent to any temporal method.

    A predicted alarm matching no episode is a false positive. That is the number
    which decides whether a real driver leaves the system switched on (risk R6),
    so report it prominently and never average it away.
    """
    m = EventMetrics()
    matched: set[int] = set()

    for gt_start, gt_end in ground_truth:
        hit: int | None = None
        for i, (p_start, p_end) in enumerate(predicted):
            if p_start <= gt_end + tolerance_s and p_end >= gt_start:
                if hit is None:
                    hit = i
                matched.add(i)
        if hit is None:
            m.false_negatives += 1
        else:
            m.true_positives += 1
            m.latencies_s.append(max(0.0, predicted[hit][0] - gt_start))

    m.false_positives = len(predicted) - len(matched)
    return m


def false_alarms_per_hour(false_positives: int, duration_s: float) -> float:
    """The number that actually predicts whether a driver disables the system.

    Report this alongside precision: "precision 0.8" sounds fine until it turns out
    to mean twelve spurious alarms an hour.
    """
    return false_positives * 3600.0 / duration_s if duration_s > 0 else 0.0
