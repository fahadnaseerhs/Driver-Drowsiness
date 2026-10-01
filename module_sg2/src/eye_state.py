"""SG-2 Eye State & Blink Analysis -- baseline: Eye Aspect Ratio (EAR).

Contract
--------
    IN   interfaces.contracts.FaceResult   (68 landmarks + eye ROIs from SG-1)
    OUT  interfaces.contracts.EyeResult    (ear, eye_state, blink_event, closure_duration_s)

Decision matrix (Figma section 3)
---------------------------------
    Eye Aspect Ratio (EAR)   weighted 49   BASELINE -- fast, explainable  <- here
    MobileNetV2 classifier   weighted 49   comparison, fallback for glasses

EAR and the CNN tie on the weighted score, which is exactly why you must run the
comparison rather than argue about it: EAR is cheap and explainable but degrades
on glasses and low light (risk R1), the CNN is robust but costs memory and FPS.
The deliverable for Labs 5-6 is a measured table, not a preference.

EAR definition frozen for V1 (0-indexed iBUG):
    EAR = (|p37-p41| + |p38-p40|) / (2 * |p36-p39|)      per eye
    ear = mean of the two eyes that are available
Change this and interfaces/mock/mock_eye.json stops matching -- raise it with the
team first.

Why this module is stateful
---------------------------
A blink is not a frame property. ``closure_duration_s`` and ``blink_event`` need
memory of previous frames, so the detector keeps a small state machine. That
state must be resettable between clips, or clip N+1 inherits clip N's closure.
"""

from __future__ import annotations

import math

from interfaces.contracts import LEFT_EYE_IDX, RIGHT_EYE_IDX, EyeResult, EyeState, FaceResult


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio(points: list[tuple[float, float]]) -> float | None:
    """EAR for one eye, given its 6 iBUG points in order. None if degenerate.

    ``points`` must be [outer corner, upper, upper, inner corner, lower, lower].
    """
    if len(points) != 6:
        return None
    width = _dist(points[0], points[3])
    if width < 1e-6:
        return None                     # zero-width eye: landmark collapse
    vertical = _dist(points[1], points[5]) + _dist(points[2], points[4])
    return vertical / (2.0 * width)


class EyeStateAnalyser:
    """EAR-based eye state with blink counting and sustained-closure tracking."""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        # Threshold is deliberately a config value, not a constant: Lab 5 is a
        # parameter study and Lab 13 may need a per-subject calibration.
        self.ear_threshold = float(cfg.get("ear_threshold", 0.21))
        # A blink must last at least this long to count, which rejects single-frame
        # landmark jitter being counted as a blink (inflating blink rate for SG-4).
        self.min_blink_s = float(cfg.get("min_blink_s", 0.06))
        # ...and at most this long; longer than this is not a blink, it is a
        # closure, and SG-4 should see it as PERCLOS, not as a blink event.
        self.max_blink_s = float(cfg.get("max_blink_s", 0.50))
        # Hysteresis on the threshold stops chattering when EAR sits on the line.
        self.hysteresis = float(cfg.get("hysteresis", 0.02))
        # Per-subject normalisation: divide EAR by the running open-eye baseline.
        # Off by default -- turn it on only with evidence (Lab 5).
        self.normalise = bool(cfg.get("normalise_by_baseline", False))
        self.baseline_alpha = float(cfg.get("baseline_alpha", 0.01))

        self.reset()

    def reset(self) -> None:
        """Clear all temporal state. MUST be called between clips."""
        self._is_closed = False
        self._closure_s = 0.0
        self._last_ts: float | None = None
        self._open_baseline: float | None = None
        self.blink_count = 0

    # ----------------------------------------------------------------------- #
    def process(self, face: FaceResult) -> EyeResult:
        """FaceResult -> EyeResult. Never raises; returns valid=False with a reason."""
        ts = face.timestamp
        dt = 0.0 if self._last_ts is None else max(0.0, ts - self._last_ts)
        self._last_ts = ts

        if not face.valid or len(face.landmarks) < 48:
            # Upstream gave us nothing. Do NOT carry the closure forward: an
            # unobserved driver is not a closed-eye driver. Report honestly and
            # let SG-4 decide what an observation gap means.
            self._is_closed = False
            self._closure_s = 0.0
            return EyeResult.empty(face.frame_id, ts,
                                   reason=face.reason or "upstream_invalid")

        lm = face.landmarks
        ear_r = eye_aspect_ratio([lm[i] for i in RIGHT_EYE_IDX])
        ear_l = eye_aspect_ratio([lm[i] for i in LEFT_EYE_IDX])
        available = [e for e in (ear_r, ear_l) if e is not None]
        if not available:
            self._is_closed, self._closure_s = False, 0.0
            return EyeResult.empty(face.frame_id, ts, reason="degenerate_eye_landmarks")

        ear = sum(available) / len(available)

        # Optional per-subject normalisation against the running open baseline.
        ear_eff = ear
        if self.normalise:
            if self._open_baseline is None:
                self._open_baseline = ear
            elif not self._is_closed:
                a = self.baseline_alpha
                self._open_baseline = (1 - a) * self._open_baseline + a * ear
            if self._open_baseline and self._open_baseline > 1e-6:
                ear_eff = ear / self._open_baseline * 0.30   # scale to the open-eye nominal

        # Schmitt trigger: fall below (T - h) to close, rise above (T + h) to open.
        lo = self.ear_threshold - self.hysteresis
        hi = self.ear_threshold + self.hysteresis
        was_closed = self._is_closed
        if self._is_closed:
            self._is_closed = ear_eff <= hi
        else:
            self._is_closed = ear_eff < lo

        blink_event = False
        if self._is_closed:
            self._closure_s += dt
        else:
            if was_closed:
                # Closure just ended -- was it a blink, or a longer closure?
                if self.min_blink_s <= self._closure_s <= self.max_blink_s:
                    blink_event = True
                    self.blink_count += 1
            self._closure_s = 0.0

        return EyeResult(
            frame_id=face.frame_id,
            timestamp=ts,
            valid=True,
            reason="",
            ear_left=None if ear_l is None else round(ear_l, 4),
            ear_right=None if ear_r is None else round(ear_r, 4),
            ear=round(ear, 4),
            eye_state=EyeState.CLOSED if self._is_closed else EyeState.OPEN,
            blink_event=blink_event,
            closure_duration_s=round(self._closure_s, 4),
            # Two eyes agreeing is worth more than one eye guessing.
            confidence=round(face.confidence * (1.0 if len(available) == 2 else 0.6), 4),
        )
