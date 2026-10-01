"""SG-5 Drowsiness Decision & Alert Logic -- baseline: weighted score + hysteresis.

Contract
--------
    IN   interfaces.contracts.TemporalResult   (drowsy_score + supporting evidence)
    OUT  interfaces.contracts.DecisionResult   (OK / WARN / ALERT + alert + evidence)

Decision matrix (Figma section 3)
---------------------------------
    Rule-based thresholds          weighted 49   BASELINE
    Weighted score + hysteresis    weighted 54   TARGET after baseline   <- here
    SVM / small MLP                weighted 50   comparison

This module owns the system's only safety-relevant output, and it owns risk R6:
"False alerts cause the driver to disable the system", mitigated by "hysteresis
plus a sustained-closure duration gate". Both are implemented below.

Three mechanisms keep nuisance alerts down -- all three matter, and you should be
able to show on real clips what happens when each is removed:

  1. ASYMMETRIC THRESHOLDS (hysteresis). Rising into a state needs a higher score
     than falling out of it, so a score hovering on a boundary does not flicker.
  2. DWELL TIME. A state must hold for ``min_dwell_s`` before it is adopted.
     A single noisy frame cannot raise an alert.
  3. LATCHING. Once ALERT fires it stays for at least ``alert_latch_s``, so the
     alert does not stutter off the instant the driver's eyes flick open.

A hard override exists for sustained closure: if the eyes have been closed for
longer than ``closure_override_s``, go straight to ALERT regardless of the score.
A driver with eyes shut for two seconds at speed is an emergency, and no amount
of window-averaging should be able to smooth that away.
"""

from __future__ import annotations

from interfaces.contracts import DecisionResult, DrowsinessState, TemporalResult


class DrowsinessDecider:
    """Score -> OK / WARN / ALERT with hysteresis, dwell time and latching."""

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        # Rising thresholds (score must exceed these to escalate).
        self.warn_on = float(cfg.get("warn_on", 0.45))
        self.alert_on = float(cfg.get("alert_on", 0.70))
        # Falling thresholds (score must drop below these to de-escalate).
        self.warn_off = float(cfg.get("warn_off", 0.35))
        self.alert_off = float(cfg.get("alert_off", 0.55))
        # A candidate state must persist this long before it is adopted.
        self.min_dwell_s = float(cfg.get("min_dwell_s", 0.40))
        # Once ALERT is raised, hold it at least this long.
        self.alert_latch_s = float(cfg.get("alert_latch_s", 1.50))
        # Sustained closure override -- bypasses the score entirely.
        self.closure_override_s = float(cfg.get("closure_override_s", 1.20))
        # Below this upstream confidence, refuse to escalate (R6: do not alert on
        # a PERCLOS computed from a handful of observations).
        self.min_confidence = float(cfg.get("min_confidence", 0.50))

        if not (self.warn_off <= self.warn_on and self.alert_off <= self.alert_on):
            raise ValueError("falling thresholds must be <= their rising counterparts")

        self.reset()

    def reset(self) -> None:
        """Clear all temporal state. MUST be called between clips."""
        self._state = DrowsinessState.OK
        self._candidate = DrowsinessState.OK
        self._candidate_since: float | None = None
        self._alert_since: float | None = None
        self.alert_count = 0

    # ----------------------------------------------------------------------- #
    def _target_state(self, score: float) -> DrowsinessState:
        """Where the score alone says we should be, applying hysteresis."""
        s = self._state
        if s is DrowsinessState.ALERT:
            if score < self.alert_off:
                return DrowsinessState.WARN if score >= self.warn_off else DrowsinessState.OK
            return DrowsinessState.ALERT
        if s is DrowsinessState.WARN:
            if score >= self.alert_on:
                return DrowsinessState.ALERT
            return DrowsinessState.WARN if score >= self.warn_off else DrowsinessState.OK
        # currently OK
        if score >= self.alert_on:
            return DrowsinessState.ALERT
        return DrowsinessState.WARN if score >= self.warn_on else DrowsinessState.OK

    def process(self, temporal: TemporalResult) -> DecisionResult:
        """TemporalResult -> DecisionResult. Always returns a decision."""
        ts = temporal.timestamp

        if not temporal.valid:
            # No trustworthy evidence. Hold a live ALERT through its latch (losing
            # the face mid-alert must not silence the alarm), otherwise fall to OK.
            latched = (
                self._state is DrowsinessState.ALERT
                and self._alert_since is not None
                and (ts - self._alert_since) < self.alert_latch_s
            )
            if not latched:
                self._state = DrowsinessState.OK
                self._candidate, self._candidate_since = DrowsinessState.OK, None
                self._alert_since = None
            return DecisionResult(
                frame_id=temporal.frame_id, timestamp=ts,
                valid=False, reason=temporal.reason or "upstream_invalid",
                state=self._state, drowsy_score=temporal.drowsy_score,
                alert=self._state is DrowsinessState.ALERT,
                evidence=("holding latched ALERT through observation gap"
                          if latched else f"no decision: {temporal.reason}"),
            )

        score = temporal.drowsy_score

        # --- hard override: sustained eye closure --------------------------- #
        override = temporal.longest_closure_s >= self.closure_override_s
        if override:
            target = DrowsinessState.ALERT
        elif temporal.confidence < self.min_confidence:
            # Not confident enough to escalate; decay toward OK but never jump up.
            target = DrowsinessState.OK if self._state is DrowsinessState.OK else self._state
        else:
            target = self._target_state(score)

        # --- dwell time ----------------------------------------------------- #
        if target is not self._candidate:
            self._candidate, self._candidate_since = target, ts
        dwell = ts - (self._candidate_since if self._candidate_since is not None else ts)

        # Escalation to ALERT via the override is immediate -- a dwell timer on an
        # emergency would be the wrong kind of caution.
        adopt = override or dwell >= self.min_dwell_s or target is self._state

        # --- alert latch ---------------------------------------------------- #
        if self._state is DrowsinessState.ALERT and target is not DrowsinessState.ALERT:
            if self._alert_since is not None and (ts - self._alert_since) < self.alert_latch_s:
                adopt = False                       # hold the alert

        if adopt and target is not self._state:
            if target is DrowsinessState.ALERT:
                self._alert_since = ts
                self.alert_count += 1
            elif self._state is DrowsinessState.ALERT:
                self._alert_since = None
            self._state = target

        return DecisionResult(
            frame_id=temporal.frame_id,
            timestamp=ts,
            valid=True,
            reason="",
            state=self._state,
            drowsy_score=score,
            alert=self._state is DrowsinessState.ALERT,
            evidence=self._explain(temporal, override),
            latency_ms=None,            # filled in by the pipeline, which owns the clock
        )

    # ----------------------------------------------------------------------- #
    def _explain(self, t: TemporalResult, override: bool) -> str:
        """Human-readable justification -- goes on the demo overlay and into
        failure analysis. Graded: "Alert thresholds and failure analysis" (RACI)."""
        if override:
            return (f"sustained closure {t.longest_closure_s:.2f}s "
                    f">= {self.closure_override_s:.2f}s -> ALERT")
        bits = [
            f"score {t.drowsy_score:.2f}",
            f"PERCLOS {t.perclos:.2f}",
            f"closure {t.longest_closure_s:.2f}s",
            f"blinks {t.blink_rate_per_min:.0f}/min",
            f"yawns {t.yawn_rate_per_min:.1f}/min",
        ]
        if not t.window_filled:
            bits.append(f"window only {t.window_s:.1f}s")
        if t.confidence < self.min_confidence:
            bits.append(f"LOW COVERAGE {t.confidence:.2f}")
        return f"{self._state.value}: " + ", ".join(bits)
