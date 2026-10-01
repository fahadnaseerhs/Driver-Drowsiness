"""SG-3 tests: MAR maths, the sustained-opening requirement, failure handling."""

from __future__ import annotations

import math

import pytest

from interfaces.contracts import LANDMARK_COUNT, BBox, FaceResult
from module_sg3.src.yawn_detect import YawnDetector, mouth_aspect_ratio


def lips(cx: float, cy: float, half_w: float, mar: float):
    """12 outer-lip points on an ellipse whose |p51-p57| / |p48-p54| equals ``mar``."""
    half_h = mar * half_w
    return [(cx + half_w * math.cos(math.pi + 2 * math.pi * i / 12),
             cy + half_h * math.sin(math.pi + 2 * math.pi * i / 12)) for i in range(12)]


def face_with_mar(frame_id: int, ts: float, mar: float) -> FaceResult:
    lm = [(0.0, 0.0)] * LANDMARK_COUNT
    lm[48:60] = lips(350, 300, 45, mar)
    return FaceResult(frame_id=frame_id, timestamp=ts, valid=True, reason="",
                      face_box=BBox(250, 150, 220, 260), landmarks=lm, confidence=0.9)


# --- the maths -------------------------------------------------------------- #
@pytest.mark.parametrize("mar", [0.05, 0.2, 0.45, 0.65])
def test_mar_recovers_the_value_it_was_built_from(mar):
    lm = [(0.0, 0.0)] * LANDMARK_COUNT
    lm[48:60] = lips(0, 0, 45, mar)
    assert mouth_aspect_ratio(lm) == pytest.approx(mar, abs=1e-9)


def test_mar_is_scale_invariant():
    """Leaning towards the camera widens the mouth in pixels; MAR must not move."""
    a = [(0.0, 0.0)] * LANDMARK_COUNT
    b = [(0.0, 0.0)] * LANDMARK_COUNT
    a[48:60] = lips(0, 0, 90, 0.5)
    b[48:60] = lips(0, 0, 20, 0.5)
    assert mouth_aspect_ratio(a) == pytest.approx(mouth_aspect_ratio(b), abs=1e-9)


def test_mar_on_collapsed_mouth_is_none():
    assert mouth_aspect_ratio([(3.0, 3.0)] * LANDMARK_COUNT) is None
    assert mouth_aspect_ratio([(0.0, 0.0)] * 10) is None


# --- the state machine ------------------------------------------------------ #
def test_closed_mouth_is_not_a_yawn():
    d = YawnDetector()
    r = d.process(face_with_mar(0, 0.0, 0.05))
    assert r.valid and not r.yawn_flag and not r.yawn_event


def test_sustained_opening_reports_a_yawn():
    d = YawnDetector({"min_yawn_s": 0.80})
    seq = [0.05] * 5 + [0.65] * 40 + [0.05] * 5      # 1.33 s wide open
    events = [d.process(face_with_mar(i, i / 30.0, m)).yawn_event
              for i, m in enumerate(seq)]
    assert sum(events) == 1
    assert d.yawn_count == 1


def test_brief_openings_are_not_yawns():
    """Talking opens the mouth repeatedly but briefly. If this test fails the system
    cries yawn at every conversation, which walks straight into risk R6."""
    d = YawnDetector({"min_yawn_s": 0.80})
    seq = ([0.05] * 3 + [0.60] * 6) * 6              # 200 ms openings, repeated
    events = [d.process(face_with_mar(i, i / 30.0, m)).yawn_event
              for i, m in enumerate(seq)]
    assert sum(events) == 0
    assert d.yawn_count == 0


def test_implausibly_long_opening_is_treated_as_tracking_failure():
    """A landmark stuck wide open is a tracking failure, not a four-second yawn.
    Once flagged it must STAY flagged until the mouth genuinely closes, and it
    must never be converted into a yawn_event on the way out."""
    d = YawnDetector({"max_yawn_s": 2.0, "min_yawn_s": 0.8})
    results = [d.process(face_with_mar(i, i / 30.0, 0.65)) for i in range(120)]
    assert results[-1].valid is False
    assert results[-1].reason == "implausible_mouth_open"
    assert not any(r.yawn_event for r in results), "stuck mouth must not count as a yawn"
    assert d.yawn_count == 0

    # The latch clears only when the mouth actually closes.
    closed = [d.process(face_with_mar(120 + i, (120 + i) / 30.0, 0.05)) for i in range(5)]
    assert closed[-1].valid is True
    assert not any(r.yawn_event for r in closed)


def test_upstream_invalid_propagates():
    d = YawnDetector()
    r = d.process(FaceResult.empty(4, 0.13, reason="no_face"))
    assert r.valid is False and r.reason == "no_face"


def test_reset_clears_state():
    d = YawnDetector()
    for i in range(30):
        d.process(face_with_mar(i, i / 30.0, 0.65))
    d.reset()
    assert d.process(face_with_mar(0, 0.0, 0.65)).yawn_duration_s == 0.0
