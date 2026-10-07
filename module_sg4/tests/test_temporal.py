"""SG-4 tests: PERCLOS over a window, observation gaps, and the fusion score."""

from __future__ import annotations

import pytest

from interfaces.contracts import EyeResult, EyeState, YawnResult
from module_sg4.src.temporal import TemporalAnalyser


def eye(i: int, closed: bool, closure_s: float = 0.0, blink: bool = False,
        valid: bool = True) -> EyeResult:
    if not valid:
        return EyeResult.empty(i, i / 30.0, reason="no_face")
    return EyeResult(frame_id=i, timestamp=i / 30.0, valid=True, reason="",
                     ear=0.08 if closed else 0.30,
                     eye_state=EyeState.CLOSED if closed else EyeState.OPEN,
                     blink_event=blink, closure_duration_s=closure_s, confidence=0.9)


def yawn(i: int, event: bool = False, valid: bool = True) -> YawnResult:
    if not valid:
        return YawnResult.empty(i, i / 30.0, reason="no_face")
    return YawnResult(frame_id=i, timestamp=i / 30.0, valid=True, reason="",
                      mar=0.1, yawn_event=event, confidence=0.9)


def test_all_open_gives_zero_perclos_and_zero_score():
    a = TemporalAnalyser({"window_s": 3.0})
    r = None
    for i in range(90):
        r = a.process(eye(i, closed=False), yawn(i))
    assert r.valid and r.perclos == 0.0 and r.drowsy_score == 0.0


def test_all_closed_saturates_perclos_and_the_eye_terms_of_the_score():
    """Eyes shut throughout saturates the PERCLOS and closure terms (0.60 + 0.30).
    It does NOT reach 1.0 -- the remaining 0.10 is the yawn term, and a driver
    asleep with their mouth shut genuinely has no yawn evidence."""
    a = TemporalAnalyser({"window_s": 3.0})
    r = None
    for i in range(90):
        r = a.process(eye(i, closed=True, closure_s=i / 30.0), yawn(i))
    assert r.perclos == pytest.approx(1.0)
    assert r.drowsy_score == pytest.approx(0.90)


def test_score_reaches_one_only_when_every_cue_saturates():
    a = TemporalAnalyser({"window_s": 3.0})
    r = None
    for i in range(90):
        r = a.process(eye(i, closed=True, closure_s=i / 30.0),
                      yawn(i, event=(i == 10)))
    assert r.drowsy_score == pytest.approx(1.0)


def test_perclos_is_the_closed_fraction_of_the_window():
    """Half the window closed must give PERCLOS 0.5, not merely something near it."""
    a = TemporalAnalyser({"window_s": 3.0})
    r = None
    for i in range(90):
        r = a.process(eye(i, closed=(i % 2 == 0)), yawn(i))
    assert r.perclos == pytest.approx(0.5, abs=0.02)


def test_score_stays_within_zero_and_one():
    a = TemporalAnalyser({"window_s": 3.0})
    for i in range(120):
        r = a.process(eye(i, closed=True, closure_s=i / 30.0), yawn(i, event=(i % 20 == 0)))
        assert 0.0 <= r.drowsy_score <= 1.0


def test_invalid_frames_are_excluded_not_counted_as_open():
    """The important one. If a lost face counted as eyes-open, PERCLOS would be
    silently diluted and real drowsiness would be hidden."""
    a = TemporalAnalyser({"window_s": 3.0, "min_valid_fraction": 0.3})
    r = None
    for i in range(90):
        # Two thirds of frames unobserved; every observed frame has eyes closed.
        observed = (i % 3 == 0)
        r = a.process(eye(i, closed=True, closure_s=0.5, valid=observed),
                      yawn(i, valid=observed))
    assert r.valid
    assert r.perclos == pytest.approx(1.0), "PERCLOS must be over observed frames only"
    assert r.confidence == pytest.approx(1 / 3, abs=0.05), "coverage must be reported"


def test_low_coverage_refuses_to_decide():
    a = TemporalAnalyser({"window_s": 3.0, "min_valid_fraction": 0.5})
    r = None
    for i in range(90):
        r = a.process(eye(i, closed=True, valid=(i % 10 == 0)), yawn(i, valid=(i % 10 == 0)))
    assert r.valid is False
    assert "insufficient_coverage" in r.reason


def test_no_valid_observations_at_all():
    a = TemporalAnalyser()
    r = None
    for i in range(30):
        r = a.process(eye(i, closed=False, valid=False), yawn(i, valid=False))
    assert r.valid is False and r.reason == "no_valid_observations"


def test_frame_id_mismatch_is_reported_not_averaged_over():
    """A real integration bug -- SG-2 and SG-3 drifting out of step. Fail loudly."""
    a = TemporalAnalyser()
    r = a.process(eye(10, closed=False), yawn(7))
    assert r.valid is False
    assert "frame_id_mismatch" in r.reason


def test_missing_yawn_input_is_recorded_not_hidden():
    a = TemporalAnalyser()
    r = None
    for i in range(60):
        r = a.process(eye(i, closed=False), None)
    assert r.valid and r.reason == "no_yawn_input"
    assert r.yawn_rate_per_min == 0.0


def test_window_filled_flag_reflects_warm_up():
    a = TemporalAnalyser({"window_s": 3.0})
    first = a.process(eye(0, closed=False), yawn(0))
    assert not first.window_filled
    r = None
    for i in range(1, 100):
        r = a.process(eye(i, closed=False), yawn(i))
    assert r.window_filled


def test_old_frames_leave_the_window():
    """Closure early in a clip must stop influencing PERCLOS once it ages out."""
    a = TemporalAnalyser({"window_s": 1.0})
    for i in range(30):
        a.process(eye(i, closed=True, closure_s=i / 30.0), yawn(i))
    r = None
    for i in range(30, 90):
        r = a.process(eye(i, closed=False), yawn(i))
    assert r.perclos == 0.0


def test_current_closure_tracks_the_ongoing_closure_not_the_window_max():
    """current_closure_s is the closure happening NOW: it ramps while the eyes
    are closed and drops to 0 the frame they reopen, even though longest_closure_s
    still holds the peak closure that remains inside the window. SG-5 keys its
    override on this field to release the alarm after a closure ends."""
    a = TemporalAnalyser({"window_s": 3.0})
    r = None
    for i in range(45):  # 1.5 s of sustained closure
        r = a.process(eye(i, closed=True, closure_s=(i + 1) / 30.0), yawn(i))
    assert r.current_closure_s == pytest.approx(1.5, abs=0.05)
    assert r.longest_closure_s == pytest.approx(1.5, abs=0.05)
    # Eyes reopen: current drops to 0 immediately; the window max still lingers.
    r = a.process(eye(45, closed=False, closure_s=0.0), yawn(45))
    assert r.current_closure_s == 0.0
    assert r.longest_closure_s == pytest.approx(1.5, abs=0.05)


def test_reset_clears_the_window():
    a = TemporalAnalyser()
    for i in range(60):
        a.process(eye(i, closed=True, closure_s=1.0), yawn(i))
    a.reset()
    r = a.process(eye(0, closed=False), yawn(0))
    assert r.perclos == 0.0
