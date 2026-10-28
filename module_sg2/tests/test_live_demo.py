"""SG-2 live demo: the pure helpers only (no camera, no OpenCV, no MediaPipe)."""

from __future__ import annotations

import pytest

from interfaces.contracts import EyeResult, EyeState
from module_sg2.live_demo import BlinkRate, alert_active


def closed_for(seconds: float, valid: bool = True) -> EyeResult:
    return EyeResult(frame_id=0, timestamp=0.0, valid=valid, reason="" if valid else "no_face",
                     ear=0.08, eye_state=EyeState.CLOSED, closure_duration_s=seconds)


def test_alert_fires_only_after_the_closure_threshold():
    assert not alert_active(closed_for(1.4), alert_s=1.5)
    assert alert_active(closed_for(1.5), alert_s=1.5)


def test_alert_never_fires_on_an_unobserved_driver():
    assert not alert_active(closed_for(5.0, valid=False), alert_s=1.5)


def test_blink_rate_waits_for_warmup_then_reports_per_minute():
    r = BlinkRate(window_s=60.0, warmup_s=10.0)
    assert r.update(0.0, False) is None
    assert r.update(5.0, True) is None                  # 5 s of history: too little
    assert r.update(20.0, True) == pytest.approx(2 * 60.0 / 20.0)


def test_blink_rate_forgets_blinks_outside_the_window():
    r = BlinkRate(window_s=60.0, warmup_s=10.0)
    r.update(0.0, True)
    assert r.update(61.0, False) == pytest.approx(0.0)
