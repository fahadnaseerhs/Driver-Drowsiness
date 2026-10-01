"""SG-3 Yawn & Facial-Cue Analysis -- baseline: Mouth Aspect Ratio (MAR).

Contract
--------
    IN   interfaces.contracts.FaceResult   (68 landmarks + mouth ROI from SG-1)
    OUT  interfaces.contracts.YawnResult   (mar, yawn_flag, yawn_event, yawn_duration_s)

Decision matrix (Figma section 3)
---------------------------------
    Mouth Aspect Ratio (MAR)    weighted 49   BASELINE   <- implemented here
    MobileNet yawn classifier   weighted 49   comparison

The whole reason SG-3 exists as a separate module is independence from SG-2: eye
closure and yawning fail in different conditions, so SG-4 can still see evidence
when one cue drops out (Figma: "improves robustness to single-cue failure").
Keep that independence -- do not reach into SG-2's output from here.

MAR definition frozen for V1 (0-indexed iBUG):
    MAR = |p51 - p57| / |p48 - p54|
          (outer-lip top centre to bottom centre, over mouth corner to corner)
Normalising by mouth width makes MAR scale-invariant, so the driver leaning
towards or away from the camera does not change it. Matches mock_yawn.json.

Known weakness to measure, not hide: MAR cannot tell a yawn from talking,
singing or laughing. That is why ``yawn_event`` requires a sustained opening --
and why SG-4 looks at rate over a window rather than any single event.
"""

from __future__ import annotations

import math

from interfaces.contracts import FaceResult, YawnResult


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def mouth_aspect_ratio(landmarks: list[tuple[float, float]]) -> float | None:
    """MAR from the full 68-point set. None if the mouth landmarks are degenerate."""
    if len(landmarks) < 58:
        return None
    width = _dist(landmarks[48], landmarks[54])
    if width < 1e-6:
        return None
    return _dist(landmarks[51], landmarks[57]) / width


class YawnDetector:
    """MAR-based yawn detection with a sustained-opening requirement."""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self.mar_threshold = float(cfg.get("mar_threshold", 0.45))
        self.hysteresis = float(cfg.get("hysteresis", 0.05))
        # A yawn is long. Talking opens the mouth briefly and repeatedly; requiring
        # a sustained opening is the cheapest discriminator available.
        self.min_yawn_s = float(cfg.get("min_yawn_s", 0.80))
        # Guard against a stuck landmark holding yawn_flag true forever.
        self.max_yawn_s = float(cfg.get("max_yawn_s", 10.0))
        self.reset()

    def reset(self) -> None:
        """Clear all temporal state. MUST be called between clips."""
        self._is_open = False
        self._open_s = 0.0
        self._last_ts: float | None = None
        # Set once an opening has run implausibly long. While it is set we report
        # invalid and refuse to count, until the mouth genuinely closes again.
        # Without this latch a landmark stuck wide open would re-trip the limit
        # every max_yawn_s seconds AND emit a bogus yawn_event when it finally
        # cleared -- see test_implausibly_long_opening_is_treated_as_tracking_failure.
        self._implausible = False
        self.yawn_count = 0

    # ----------------------------------------------------------------------- #
    def process(self, face: FaceResult) -> YawnResult:
        """FaceResult -> YawnResult. Never raises; returns valid=False with a reason."""
        ts = face.timestamp
        dt = 0.0 if self._last_ts is None else max(0.0, ts - self._last_ts)
        self._last_ts = ts

        if not face.valid or len(face.landmarks) < 58:
            self._is_open, self._open_s = False, 0.0
            return YawnResult.empty(face.frame_id, ts,
                                    reason=face.reason or "upstream_invalid")

        mar = mouth_aspect_ratio(face.landmarks)
        if mar is None:
            self._is_open, self._open_s = False, 0.0
            return YawnResult.empty(face.frame_id, ts, reason="degenerate_mouth_landmarks")

        lo = self.mar_threshold - self.hysteresis
        hi = self.mar_threshold + self.hysteresis

        # While latched, stay invalid until the mouth actually closes.
        if self._implausible:
            if mar <= lo:
                self._implausible = False
            else:
                return YawnResult.empty(face.frame_id, ts, reason="implausible_mouth_open")

        was_open = self._is_open
        if self._is_open:
            self._is_open = mar >= lo
        else:
            self._is_open = mar > hi

        yawn_event = False
        if self._is_open:
            self._open_s += dt
            if self._open_s > self.max_yawn_s:
                # Implausibly long: treat as a tracking failure, not a yawn, and
                # latch so the next frames do not start counting a fresh "yawn".
                self._is_open, self._open_s = False, 0.0
                self._implausible = True
                return YawnResult.empty(face.frame_id, ts, reason="implausible_mouth_open")
        else:
            if was_open and self._open_s >= self.min_yawn_s:
                yawn_event = True
                self.yawn_count += 1
            self._open_s = 0.0

        return YawnResult(
            frame_id=face.frame_id,
            timestamp=ts,
            valid=True,
            reason="",
            mar=round(mar, 4),
            yawn_flag=self._is_open,
            yawn_event=yawn_event,
            yawn_duration_s=round(self._open_s, 4),
            confidence=round(face.confidence, 4),
        )
