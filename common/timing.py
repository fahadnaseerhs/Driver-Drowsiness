"""FPS and latency measurement.

Jetson Readiness is 10% of the sub-group mark and the Figma KPIs are FPS, false-alarm
rate and alert latency. Every module reports through this class so the numbers in
``module_sgN/results/`` are produced the same way and are comparable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Stopwatch:
    """Per-stage wall-clock timer. Use as a context manager."""

    name: str = "stage"
    samples: list[float] = field(default_factory=list)
    _t0: float = 0.0

    def __enter__(self) -> Stopwatch:
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.samples.append((time.perf_counter() - self._t0) * 1000.0)

    @property
    def last_ms(self) -> float:
        return self.samples[-1] if self.samples else 0.0

    def summary(self) -> dict[str, float]:
        """mean / p50 / p95 / max latency in ms, plus the implied FPS ceiling."""
        if not self.samples:
            return {"n": 0}
        s = sorted(self.samples)
        n = len(s)
        mean = sum(s) / n
        return {
            "n": n,
            "mean_ms": round(mean, 3),
            "p50_ms": round(s[n // 2], 3),
            "p95_ms": round(s[min(n - 1, int(0.95 * n))], 3),
            "max_ms": round(s[-1], 3),
            "fps_ceiling": round(1000.0 / mean, 2) if mean > 0 else 0.0,
        }


class FPSMeter:
    """Rolling frames-per-second over the last ``window`` frames."""

    def __init__(self, window: int = 60) -> None:
        self.window = window
        self._times: list[float] = []

    def tick(self) -> float:
        self._times.append(time.perf_counter())
        if len(self._times) > self.window:
            self._times.pop(0)
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0
