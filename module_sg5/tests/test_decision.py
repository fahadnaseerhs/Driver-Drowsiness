"""SG-5 tests: hysteresis, dwell time, latching, the closure override.

This module owns risk R6 -- false alerts make the driver switch the system off --
so most of these tests are about NOT alerting, which is the harder half.
"""

from __future__ import annotations

import pytest

from interfaces.contracts import DrowsinessState, TemporalResult
from module_sg5.src.decision import DrowsinessDecider


def temporal(i: int, score: float, closure_s: float = 0.0,
             confidence: float = 1.0, valid: bool = True,
             current_closure_s: float | None = None) -> TemporalResult:
    if not valid:
        return TemporalResult.empty(i, i / 30.0, reason="no_valid_observations")
    # By default the ongoing closure equals the window max (a closure in progress).
    # Pass current_closure_s explicitly to model a closure that has already ended
    # while its value still sits in the window as longest_closure_s.
    if current_closure_s is None:
        current_closure_s = closure_s
    return TemporalResult(frame_id=i, timestamp=i / 30.0, valid=True, reason="",
                          window_s=3.0, window_filled=True, perclos=min(1.0, score),
                          longest_closure_s=closure_s,
                          current_closure_s=current_closure_s, drowsy_score=score,
                          confidence=confidence)


def drive(dec: DrowsinessDecider, scores, closure=0.0, confidence=1.0):
    """Feed a score sequence and return the resulting state track."""
    return [dec.process(temporal(i, s, closure, confidence)).state
            for i, s in enumerate(scores)]


# --- the happy paths -------------------------------------------------------- #
def test_low_score_stays_ok():
    d = DrowsinessDecider()
    states = drive(d, [0.1] * 60)
    assert set(states) == {DrowsinessState.OK}
    assert d.alert_count == 0


def test_high_score_eventually_alerts():
    d = DrowsinessDecider({"min_dwell_s": 0.4})
    states = drive(d, [0.9] * 60)
    assert states[-1] is DrowsinessState.ALERT
    assert d.alert_count == 1


def test_mid_score_reaches_warn_not_alert():
    d = DrowsinessDecider()
    states = drive(d, [0.50] * 60)
    assert states[-1] is DrowsinessState.WARN


def test_alert_flag_tracks_the_state():
    d = DrowsinessDecider()
    for i, s in enumerate([0.9] * 60):
        r = d.process(temporal(i, s))
        assert r.alert == (r.state is DrowsinessState.ALERT)


# --- not alerting: the R6 half ---------------------------------------------- #
def test_single_spike_does_not_raise_an_alert():
    """One noisy frame must never sound the alarm. Dwell time is what stops it."""
    d = DrowsinessDecider({"min_dwell_s": 0.40})
    states = drive(d, [0.1] * 20 + [0.95] + [0.1] * 20)
    assert DrowsinessState.ALERT not in states
    assert d.alert_count == 0


def test_hysteresis_prevents_flicker_on_the_boundary():
    """A score parked exactly on alert_on must not toggle every frame."""
    d = DrowsinessDecider({"alert_on": 0.70, "alert_off": 0.55, "min_dwell_s": 0.0})
    states = drive(d, [0.70] * 40)
    transitions = sum(1 for a, b in zip(states, states[1:], strict=False) if a is not b)
    assert transitions <= 1, f"state flickered {transitions} times"


def test_low_upstream_confidence_blocks_escalation():
    """Do not alert on a PERCLOS computed from a handful of observations."""
    d = DrowsinessDecider({"min_confidence": 0.50})
    states = drive(d, [0.95] * 60, confidence=0.2)
    assert DrowsinessState.ALERT not in states


def test_alert_clears_once_the_score_falls_and_the_latch_expires():
    d = DrowsinessDecider({"alert_latch_s": 0.5, "min_dwell_s": 0.2})
    for i, s in enumerate([0.95] * 40):
        d.process(temporal(i, s))
    assert d._state is DrowsinessState.ALERT
    last = None
    for j, s in enumerate([0.05] * 90):
        last = d.process(temporal(40 + j, s))
    assert last.state is DrowsinessState.OK


# --- the latch -------------------------------------------------------------- #
def test_alert_is_held_for_the_latch_duration():
    """The alarm must not stutter off the instant the eyes flick open."""
    d = DrowsinessDecider({"alert_latch_s": 1.0, "min_dwell_s": 0.1})
    for i in range(30):
        d.process(temporal(i, 0.95))
    assert d._state is DrowsinessState.ALERT
    # Score collapses immediately; within the latch the alert must persist.
    r = d.process(temporal(30, 0.0))
    assert r.state is DrowsinessState.ALERT
    assert r.alert is True


def test_alert_survives_an_observation_gap_within_the_latch():
    """Losing the face mid-alert must not silence the alarm."""
    d = DrowsinessDecider({"alert_latch_s": 1.0, "min_dwell_s": 0.1})
    for i in range(30):
        d.process(temporal(i, 0.95))
    r = d.process(temporal(31, 0.0, valid=False))
    assert r.state is DrowsinessState.ALERT
    assert r.valid is False, "the decision is still reported as unsupported"
    assert "latched" in r.evidence.lower()


def test_state_falls_to_ok_when_a_gap_outlasts_the_latch():
    d = DrowsinessDecider({"alert_latch_s": 0.2, "min_dwell_s": 0.1})
    for i in range(30):
        d.process(temporal(i, 0.95))
    last = None
    for j in range(60):
        last = d.process(temporal(30 + j, 0.0, valid=False))
    assert last.state is DrowsinessState.OK


# --- the override ----------------------------------------------------------- #
def test_sustained_closure_overrides_a_low_score_immediately():
    """Eyes shut for 1.5 s is an emergency; no amount of window-averaging may
    smooth it away, and no dwell timer may delay it."""
    d = DrowsinessDecider({"closure_override_s": 1.20, "min_dwell_s": 2.0})
    r = d.process(temporal(0, score=0.05, closure_s=1.5))
    assert r.state is DrowsinessState.ALERT
    assert "sustained closure" in r.evidence


def test_closure_just_below_the_override_does_not_fire():
    d = DrowsinessDecider({"closure_override_s": 1.20})
    r = d.process(temporal(0, score=0.05, closure_s=1.0))
    assert r.state is DrowsinessState.OK


def test_window_max_closure_alone_does_not_force_alert():
    """Regression for the stuck alarm: a long closure that has ALREADY ENDED
    still sits in the window as longest_closure_s, but the eyes are open now
    (current_closure_s == 0). The override must key on the CURRENT closure, so a
    low score with no ongoing closure stays OK."""
    d = DrowsinessDecider({"closure_override_s": 1.20})
    r = d.process(temporal(0, score=0.05, closure_s=1.80, current_closure_s=0.0))
    assert r.state is DrowsinessState.OK, "window-max closure must not fire the override"


def test_override_releases_when_the_closure_ends_so_the_alert_can_clear():
    """The whole bug: with the eyes reopened the override must let go, and the
    alarm must clear once the score falls and the latch expires -- even though
    longest_closure_s is still high in the window."""
    d = DrowsinessDecider({"closure_override_s": 1.20, "alert_latch_s": 0.5,
                           "min_dwell_s": 0.2})
    # Eyes closed and still closing: override fires, we are in ALERT.
    for i in range(40):
        d.process(temporal(i, score=0.2, closure_s=1.5, current_closure_s=1.5))
    assert d._state is DrowsinessState.ALERT
    # Eyes reopen: current closure is 0 though the 1.5 s closure lingers as the
    # window max; score has fallen. The alarm must de-escalate to OK.
    last = None
    for j in range(90):
        last = d.process(temporal(40 + j, score=0.05, closure_s=1.5,
                                   current_closure_s=0.0))
    assert last.state is DrowsinessState.OK, "override still pinning ALERT after recovery"


def test_an_ongoing_long_closure_still_alerts_immediately():
    """Safety must survive the fix: eyes shut NOW for >= the override still goes
    straight to ALERT, bypassing dwell."""
    d = DrowsinessDecider({"closure_override_s": 1.20, "min_dwell_s": 2.0})
    r = d.process(temporal(0, score=0.05, closure_s=1.5, current_closure_s=1.5))
    assert r.state is DrowsinessState.ALERT
    assert "sustained closure" in r.evidence


# --- housekeeping ----------------------------------------------------------- #
def test_evidence_is_always_populated():
    """The overlay and the failure analysis both read this field."""
    d = DrowsinessDecider()
    for i, s in enumerate([0.1, 0.5, 0.9, 0.3]):
        assert d.process(temporal(i, s)).evidence


def test_inconsistent_thresholds_are_rejected_at_construction():
    with pytest.raises(ValueError):
        DrowsinessDecider({"alert_on": 0.4, "alert_off": 0.8})


def test_reset_clears_state():
    d = DrowsinessDecider()
    for i in range(60):
        d.process(temporal(i, 0.95))
    d.reset()
    assert d._state is DrowsinessState.OK
    assert d.alert_count == 0


# --- reset(): no state may leak from one clip into the next ----------------- #
def test_reset_clears_the_latch_so_a_low_score_frame_does_not_stay_alerting():
    """reset() must drop the latch and the alert timestamp, not just the state.

    Catches a reset() that forgets ``_alert_since``: the state would read OK, but the
    first frame of the next clip would be judged against a stale alert timestamp and the
    old latch could pin ALERT again. A clip boundary has to be a clean slate.
    """
    d = DrowsinessDecider({"alert_latch_s": 1.50, "min_dwell_s": 0.20})
    for i in range(60):
        d.process(temporal(i, 0.95))
    assert d._state is DrowsinessState.ALERT, "setup failed: never got into ALERT"

    d.reset()
    assert d._state is DrowsinessState.OK
    assert d.alert_count == 0
    assert d._alert_since is None, "the alert timestamp survived reset()"
    assert d._candidate_since is None, "the dwell timer survived reset()"

    # A single quiet frame, at a timestamp well inside the old latch window, must be
    # judged on its own evidence rather than held by the previous clip's alert.
    r = d.process(temporal(60, 0.05))
    assert r.state is DrowsinessState.OK
    assert r.alert is False


def test_a_new_clip_after_a_latched_alert_begins_in_ok():
    """Per-clip metrics are meaningless if state leaks across the boundary.

    Catches a reset() that is never able to clear a LIVE latched ALERT -- the previous
    clip ends mid-alarm, which is exactly the case the evaluation harness hits, and the
    new clip must not open with the alarm already sounding.
    """
    d = DrowsinessDecider({"alert_latch_s": 1.50, "min_dwell_s": 0.20})
    for i in range(60):
        d.process(temporal(i, 0.95))
    assert d._state is DrowsinessState.ALERT

    d.reset()
    # Clip two restarts the clock at 0, as every module's run.py and the pipeline do.
    first = d.process(temporal(0, 0.10))
    assert first.state is DrowsinessState.OK
    assert d.alert_count == 0, "the new clip inherited the previous clip's alert count"


# --- the 8c9c079 fix, pinned ------------------------------------------------ #
def test_the_override_releases_on_reopen_and_the_state_then_leaves_alert():
    """The unit-level pin for commit 8c9c079: the override keys on current_closure_s.

    Fails if anyone points the override back at longest_closure_s. With the eyes reopened,
    current_closure_s is 0 while longest_closure_s is still 1.80 s (the ended closure sits
    in SG-4's window for a whole window_s). Keyed on the window max the override would
    keep forcing ALERT and the state could never leave it; keyed on the current closure it
    lets go, and the latch then expires and the state falls to OK.

    The score is held just under alert_off throughout the recovery so that ONLY the
    override can be what pins ALERT -- otherwise a passing test would prove nothing.
    """
    d = DrowsinessDecider({"closure_override_s": 1.20, "alert_latch_s": 0.50,
                           "min_dwell_s": 0.20})
    # Eyes shut and still shut: the override fires and we are latched in ALERT.
    for i in range(30):
        r = d.process(temporal(i, score=0.10, closure_s=1.80, current_closure_s=1.80))
    assert r.state is DrowsinessState.ALERT
    assert "sustained closure" in r.evidence, "ALERT came from the score, not the override"

    # The instant the eyes reopen the override must stop claiming an emergency, even
    # though the window still remembers the 1.80 s closure.
    first_after = d.process(temporal(30, score=0.10, closure_s=1.80, current_closure_s=0.0))
    assert "sustained closure" not in first_after.evidence, \
        "override still firing on a closure that has already ended"
    assert first_after.state is DrowsinessState.ALERT, "the latch should still hold here"

    # Past the latch the state must actually leave ALERT.
    last = None
    for j in range(60):
        last = d.process(temporal(31 + j, score=0.10, closure_s=1.80, current_closure_s=0.0))
    assert last.state is not DrowsinessState.ALERT, \
        "override keyed on longest_closure_s is pinning ALERT after recovery"
    assert last.state is DrowsinessState.OK
    assert last.alert is False
