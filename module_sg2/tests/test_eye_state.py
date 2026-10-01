"""SG-2 tests: EAR maths, the blink state machine, and upstream-failure handling."""

from __future__ import annotations

import pytest

from interfaces.contracts import LANDMARK_COUNT, BBox, EyeState, FaceResult
from module_sg2.src.eye_state import EyeStateAnalyser, eye_aspect_ratio


def eye_hexagon(cx: float, cy: float, half_w: float, aperture: float):
    """Six iBUG-ordered eye points whose EAR is exactly ``aperture``."""
    h = aperture * half_w
    return [
        (cx - half_w, cy), (cx - half_w / 3, cy - h), (cx + half_w / 3, cy - h),
        (cx + half_w, cy), (cx + half_w / 3, cy + h), (cx - half_w / 3, cy + h),
    ]


def face_with_aperture(frame_id: int, ts: float, aperture: float) -> FaceResult:
    lm = [(0.0, 0.0)] * LANDMARK_COUNT
    lm[36:42] = eye_hexagon(300, 200, 24, aperture)
    lm[42:48] = eye_hexagon(400, 200, 24, aperture)
    return FaceResult(frame_id=frame_id, timestamp=ts, valid=True, reason="",
                      face_box=BBox(250, 120, 220, 260), landmarks=lm, confidence=0.9)


# --- the maths -------------------------------------------------------------- #
@pytest.mark.parametrize("aperture", [0.05, 0.12, 0.21, 0.30, 0.45])
def test_ear_recovers_the_aperture_it_was_built_from(aperture):
    assert eye_aspect_ratio(eye_hexagon(0, 0, 24, aperture)) == pytest.approx(aperture, abs=1e-9)


def test_ear_is_scale_invariant():
    """A driver leaning closer must not change EAR -- only lid position should."""
    near = eye_aspect_ratio(eye_hexagon(0, 0, 48, 0.25))
    far = eye_aspect_ratio(eye_hexagon(0, 0, 12, 0.25))
    assert near == pytest.approx(far, abs=1e-9)


def test_ear_on_collapsed_eye_is_none_not_a_crash():
    assert eye_aspect_ratio([(5.0, 5.0)] * 6) is None
    assert eye_aspect_ratio([(0.0, 0.0)] * 3) is None


# --- the state machine ------------------------------------------------------ #
def test_open_eye_reports_open():
    a = EyeStateAnalyser()
    r = a.process(face_with_aperture(0, 0.0, 0.30))
    assert r.valid and r.eye_state is EyeState.OPEN
    assert r.closure_duration_s == 0.0


def test_closed_eye_accumulates_closure_duration():
    a = EyeStateAnalyser({"ear_threshold": 0.21})
    for i in range(30):                      # 1 second at 30 FPS, eyes shut
        r = a.process(face_with_aperture(i, i / 30.0, 0.08))
    assert r.eye_state is EyeState.CLOSED
    assert r.closure_duration_s == pytest.approx(29 / 30.0, abs=0.02)


def test_a_short_closure_counts_as_a_blink():
    a = EyeStateAnalyser({"min_blink_s": 0.06, "max_blink_s": 0.50})
    seq = [0.30] * 5 + [0.08] * 4 + [0.30] * 5      # ~133 ms closure
    events = [a.process(face_with_aperture(i, i / 30.0, ap)).blink_event
              for i, ap in enumerate(seq)]
    assert sum(events) == 1, "exactly one blink should be reported"
    assert a.blink_count == 1


def test_a_long_closure_is_not_counted_as_a_blink():
    """This matters: counting a 2 s microsleep as a blink would inflate the blink
    rate SG-4 sees while hiding the closure that actually signals drowsiness."""
    a = EyeStateAnalyser({"max_blink_s": 0.50})
    seq = [0.30] * 5 + [0.08] * 60 + [0.30] * 5     # 2 s closure
    events = [a.process(face_with_aperture(i, i / 30.0, ap)).blink_event
              for i, ap in enumerate(seq)]
    assert sum(events) == 0
    assert a.blink_count == 0


def test_single_frame_jitter_is_not_a_blink():
    a = EyeStateAnalyser({"min_blink_s": 0.06})
    seq = [0.30] * 5 + [0.08] + [0.30] * 5          # 33 ms -- one frame
    events = [a.process(face_with_aperture(i, i / 30.0, ap)).blink_event
              for i, ap in enumerate(seq)]
    assert sum(events) == 0


def test_hysteresis_prevents_chattering_on_the_threshold():
    """An EAR sitting exactly on the threshold must not flip state every frame."""
    a = EyeStateAnalyser({"ear_threshold": 0.21, "hysteresis": 0.02})
    states = [a.process(face_with_aperture(i, i / 30.0, 0.21)).eye_state
              for i in range(20)]
    assert len(set(states)) == 1, f"state chattered: {states}"


def test_upstream_invalid_propagates_and_does_not_carry_closure_forward():
    a = EyeStateAnalyser()
    for i in range(10):                              # build up a closure
        a.process(face_with_aperture(i, i / 30.0, 0.08))
    r = a.process(FaceResult.empty(10, 10 / 30.0, reason="no_face"))
    assert r.valid is False
    assert r.reason == "no_face"
    # An unobserved driver is not a closed-eye driver.
    nxt = a.process(face_with_aperture(11, 11 / 30.0, 0.30))
    assert nxt.closure_duration_s == 0.0


def test_reset_clears_state_between_clips():
    a = EyeStateAnalyser()
    for i in range(20):
        a.process(face_with_aperture(i, i / 30.0, 0.08))
    a.reset()
    r = a.process(face_with_aperture(0, 0.0, 0.08))
    assert r.closure_duration_s == 0.0
    assert a.blink_count == 0
