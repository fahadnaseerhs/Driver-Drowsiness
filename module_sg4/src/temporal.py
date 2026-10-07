"""SG-4 Temporal Behaviour Analysis -- baseline: PERCLOS + sliding window.

Contract
--------
    IN   interfaces.contracts.EyeResult + YawnResult   (same frame_id)
    OUT  interfaces.contracts.TemporalResult           (perclos, rates, drowsy_score)

Decision matrix (Figma section 3)
---------------------------------
    PERCLOS + sliding window   weighted 56   BASELINE -- industry standard  <- here
    LSTM over frame cues       weighted 49   comparison, stretch goal

This is the module that makes the system a *drowsiness monitor* rather than a
frame classifier: "Drowsiness is inherently temporal; this module converts
observations into behavior" (guide, 2.2).

PERCLOS = the fraction of time within the window that the eyes are closed. It is
the standard fatigue measure (originally PERCLOS-P80). Computed here over VALID
frames only -- see the observation-gap note below, it matters.

Observation gaps
----------------
When SG-1 loses the face, SG-2/SG-3 return valid=False. Those frames carry no
information about eye closure, so including them as "open" would quietly dilute
PERCLOS and hide real drowsiness. This module therefore:
  * computes PERCLOS over valid frames only, and
  * reports ``confidence`` = valid/total in the window, so SG-5 can distrust a
    PERCLOS computed from very few observations, and
  * refuses to emit a decision-grade result when coverage falls below
    ``min_valid_fraction``.

Fusion weights below are a STARTING POINT taken from the Figma plan, not a
result. Labs 5-7 owe a sensitivity study: how does the F1 / false-alarm rate move
as these weights and the window length change? Risk R5 (thresholds overfit to the
recorded clips) is owned by this sub-group -- keep a held-out set untouched.
"""

from __future__ import annotations

from collections import deque

from interfaces.contracts import EyeResult, EyeState, TemporalResult, YawnResult


class TemporalAnalyser:
    """Sliding-window fusion of frame-level eye and yawn cues into behaviour."""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self.window_s = float(cfg.get("window_s", 3.0))
        self.fps_hint = float(cfg.get("fps_hint", 30.0))
        # Below this fraction of valid observations the window is not trustworthy.
        self.min_valid_fraction = float(cfg.get("min_valid_fraction", 0.5))

        # drowsy_score fusion. Each term saturates at 1.0 at its "reference" level,
        # then the weighted sum is clamped to [0, 1].
        self.w_perclos = float(cfg.get("w_perclos", 0.60))
        self.w_closure = float(cfg.get("w_closure", 0.30))
        self.w_yawn = float(cfg.get("w_yawn", 0.10))
        self.perclos_ref = float(cfg.get("perclos_ref", 0.40))      # PERCLOS 0.40 -> term = 1
        self.closure_ref_s = float(cfg.get("closure_ref_s", 1.50))  # 1.5 s closure -> term = 1
        self.yawn_ref = float(cfg.get("yawn_ref_events", 1.0))      # 1 yawn in window -> term = 1

        self.reset()

    def reset(self) -> None:
        """Clear the window. MUST be called between clips."""
        maxlen = max(2, int(self.window_s * self.fps_hint * 1.5))
        self._win: deque[tuple[float, EyeResult, YawnResult | None]] = deque(maxlen=maxlen)

    # ----------------------------------------------------------------------- #
    def process(self, eye: EyeResult, yawn: YawnResult | None = None) -> TemporalResult:
        """Push one frame of cues and return the current temporal state.

        ``yawn`` may be None if SG-3 is not running (degraded mode); the yawn term
        then contributes 0 and ``reason`` records it, rather than silently
        pretending the driver never yawns.
        """
        ts = eye.timestamp
        if yawn is not None and yawn.frame_id != eye.frame_id:
            # A real integration bug worth failing loudly on, not averaging over.
            return TemporalResult.empty(
                eye.frame_id, ts,
                reason=f"frame_id_mismatch:eye={eye.frame_id},yawn={yawn.frame_id}")

        self._win.append((ts, eye, yawn))
        # Drop anything older than the window.
        while len(self._win) > 1 and (ts - self._win[0][0]) > self.window_s:
            self._win.popleft()

        total = len(self._win)
        span = ts - self._win[0][0] if total > 1 else 0.0
        valid = [(t, e, y) for t, e, y in self._win if e.valid]

        if not valid:
            return TemporalResult.empty(eye.frame_id, ts, reason="no_valid_observations")

        coverage = len(valid) / total
        if coverage < self.min_valid_fraction:
            r = TemporalResult.empty(
                eye.frame_id, ts,
                reason=f"insufficient_coverage:{coverage:.2f}<{self.min_valid_fraction:.2f}")
            r.window_s = round(span, 4)
            r.confidence = round(coverage, 4)
            return r

        closed = sum(1 for _, e, _ in valid if e.eye_state is EyeState.CLOSED)
        perclos = closed / len(valid)
        blinks = sum(1 for _, e, _ in valid if e.blink_event)
        yawn_events = sum(1 for _, _, y in valid if y is not None and y.yawn_event)
        longest_closure = max((e.closure_duration_s for _, e, _ in valid), default=0.0)
        # The closure happening RIGHT NOW: the most-recent valid frame's ongoing
        # closure, and 0.0 the instant the eyes reopen. longest_closure above is a
        # backward-looking window max; SG-5 keys its sustained-closure override on
        # THIS so the alarm releases once a closure ends (fixes the stuck alarm).
        latest_eye = valid[-1][1]
        current_closure = (
            latest_eye.closure_duration_s
            if latest_eye.eye_state is EyeState.CLOSED else 0.0
        )
        ears = [e.ear for _, e, _ in valid if e.ear is not None]
        avg_ear = sum(ears) / len(ears) if ears else None

        # Rates per minute. Extrapolating from a very short span explodes the rate,
        # so require a reasonable span before reporting a rate at all.
        rate_span = max(span, 1e-6)
        can_rate = span >= min(1.0, self.window_s * 0.5)
        blink_rate = (blinks * 60.0 / rate_span) if can_rate else 0.0
        yawn_rate = (yawn_events * 60.0 / rate_span) if can_rate else 0.0

        score = (
            self.w_perclos * min(1.0, perclos / max(self.perclos_ref, 1e-6))
            + self.w_closure * min(1.0, longest_closure / max(self.closure_ref_s, 1e-6))
            + self.w_yawn * min(1.0, yawn_events / max(self.yawn_ref, 1e-6))
        )
        score = max(0.0, min(1.0, score))

        return TemporalResult(
            frame_id=eye.frame_id,
            timestamp=ts,
            valid=True,
            reason="" if yawn is not None else "no_yawn_input",
            window_s=round(span, 4),
            window_filled=span >= self.window_s * 0.95,
            perclos=round(perclos, 4),
            blink_rate_per_min=round(blink_rate, 2),
            yawn_rate_per_min=round(yawn_rate, 2),
            longest_closure_s=round(longest_closure, 4),
            current_closure_s=round(current_closure, 4),
            avg_ear=None if avg_ear is None else round(avg_ear, 4),
            drowsy_score=round(score, 4),
            confidence=round(coverage, 4),
        )
