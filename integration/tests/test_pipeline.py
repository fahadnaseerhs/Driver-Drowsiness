"""Integration tests -- Lab 8 / Lab 11 gate behaviour, automated.

These run the whole chain on the mock driver. They need no camera, no model
weights and no Jetson, so they can run on every push from day one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from common.video import MockFaceSource
from integration.run_pipeline import check_scenario, intervals_from_states
from integration.src.pipeline import Pipeline, build_default_pipeline
from interfaces.contracts import DrowsinessState, Frame, validate
from module_sg2.src.eye_state import EyeStateAnalyser
from module_sg3.src.yawn_detect import YawnDetector
from module_sg4.src.temporal import TemporalAnalyser
from module_sg5.src.decision import DrowsinessDecider

MOCK_FACE = Path(__file__).resolve().parents[2] / "interfaces" / "mock" / "mock_face.json"


def full_pipeline() -> Pipeline:
    return Pipeline(sg1=None, sg2=EyeStateAnalyser(), sg3=YawnDetector(),
                    sg4=TemporalAnalyser(), sg5=DrowsinessDecider())


def run_on_mock(pipe: Pipeline):
    faces = MockFaceSource().load()
    frames = [Frame(f.frame_id, f.timestamp, None) for f in faces]
    pipe.reset()
    return pipe.run(frames, faces=faces)


@pytest.fixture(scope="module")
def outputs():
    if not MOCK_FACE.exists():
        pytest.skip("mock data not generated; run interfaces/mock/generate_mocks.py")
    return run_on_mock(full_pipeline())


# --------------------------------------------------------------------------- #
# Interface compliance -- this is what Lab 8 actually gates on.
# --------------------------------------------------------------------------- #
def test_every_payload_on_every_frame_is_contract_compliant(outputs):
    for fo in outputs:
        for p in (fo.face, fo.eye, fo.yawn, fo.temporal, fo.decision):
            errs = validate(p)
            assert errs == [], f"frame {fo.frame.frame_id} {type(p).__name__}: {errs}"


def test_frame_ids_stay_aligned_through_every_stage(outputs):
    """Any drift here means a module is dropping or duplicating frames."""
    for fo in outputs:
        ids = {fo.face.frame_id, fo.eye.frame_id, fo.yawn.frame_id,
               fo.temporal.frame_id, fo.decision.frame_id}
        assert ids == {fo.frame.frame_id}, f"frame_id drift: {ids}"


def test_no_module_raised_during_the_run(outputs):
    pipe = full_pipeline()
    run_on_mock(pipe)
    assert pipe.stats.module_errors == {}, pipe.stats.module_errors


def test_a_decision_exists_for_every_frame(outputs):
    assert len(outputs) == 300
    assert all(fo.decision is not None for fo in outputs)


# --------------------------------------------------------------------------- #
# System behaviour on the scripted scenario
# --------------------------------------------------------------------------- #
def test_the_alarm_fires_during_the_sustained_closure(outputs):
    ok, msgs = check_scenario(outputs)
    assert ok, "\n".join(msgs)


def test_no_alarm_while_the_driver_is_demonstrably_awake(outputs):
    """The first two seconds contain only normal blinks. An alert here is a false
    alarm, which is risk R6 and the single fastest way to fail the demo."""
    early = [fo for fo in outputs if fo.decision.timestamp < 2.0]
    assert early, "scenario is missing its opening seconds"
    assert not any(fo.decision.state is DrowsinessState.ALERT for fo in early)


def test_the_yawn_is_detected(outputs):
    """The scenario scripts exactly one yawn, at 2.2-3.4 s."""
    events = [fo for fo in outputs if fo.yawn.yawn_event]
    assert len(events) == 1, f"expected 1 yawn event, got {len(events)}"
    assert 2.2 <= events[0].yawn.timestamp <= 3.8


def test_blinks_are_detected_and_not_confused_with_the_long_closure(outputs):
    """The scenario scripts six short closures, but only FIVE are detectable blinks.

    A blink is reported when the eyes RE-OPEN. The sixth short closure ends at
    7.98 s and the lids finish opening at about 8.02 s -- inside the 8.0-9.0 s
    no-face gap -- so its completion is never observed. Five is the correct answer,
    and that is worth knowing: blink rate is systematically under-counted around
    tracking dropouts, which SG-4 should bear in mind when reading blink_rate.

    The 1.8 s microsleep must not appear here at all; it is a closure, not a blink.
    """
    blinks = [fo.eye.timestamp for fo in outputs if fo.eye.blink_event]
    assert len(blinks) == 5, f"expected 5 blinks, got {len(blinks)}: {blinks}"
    assert not any(5.2 <= t <= 7.1 for t in blinks), "the long closure was counted as a blink"


def test_the_observation_gap_is_reported_not_silently_filled(outputs):
    """8.0-9.0 s has no face. Those frames must say so rather than inventing data."""
    gap = [fo for fo in outputs if 8.05 <= fo.frame.timestamp <= 8.95]
    assert gap
    assert all(not fo.face.valid for fo in gap)
    assert all(fo.face.reason == "no_face" for fo in gap)
    assert all(not fo.eye.valid and fo.eye.reason for fo in gap)


def test_losing_the_face_mid_alert_does_not_silence_the_alarm(outputs):
    """The alarm is live when the driver turns away at 8.0 s. It must not drop out
    simply because we stopped being able to see them."""
    at_gap_start = [fo for fo in outputs if 8.0 <= fo.frame.timestamp <= 8.2]
    assert at_gap_start
    assert any(fo.decision.state is DrowsinessState.ALERT for fo in at_gap_start)


def test_state_track_is_not_chattering(outputs):
    """Hysteresis, dwell and latch exist to keep this number tiny. A demo whose
    alarm flickers reads as broken even when the detection is right."""
    runs = intervals_from_states(outputs)
    transitions = sum(len(v) for v in runs.values())
    assert transitions <= 6, f"state changed too often: {runs}"


def test_decision_carries_latency_and_evidence(outputs):
    """SG-6 profiles latency and the demo overlay shows evidence; both are contract."""
    for fo in outputs:
        assert fo.decision.latency_ms is not None
        assert fo.decision.latency_ms >= 0.0
        assert fo.decision.evidence


# --------------------------------------------------------------------------- #
# Degraded operation -- a late pair must not stop the others integrating.
# --------------------------------------------------------------------------- #
def test_pipeline_runs_with_sg3_missing(outputs):
    """SG-3 absent: SG-4 must still produce a score from eye evidence alone."""
    pipe = Pipeline(sg2=EyeStateAnalyser(), sg3=None,
                    sg4=TemporalAnalyser(), sg5=DrowsinessDecider())
    out = run_on_mock(pipe)
    assert pipe.stats.module_errors == {}
    assert out[-1].yawn.valid is False
    assert any(fo.temporal.valid for fo in out)
    assert any(fo.decision.state is DrowsinessState.ALERT for fo in out)


def test_pipeline_runs_with_every_module_missing():
    """Nothing configured at all: still no crash, and every payload explains itself."""
    pipe = Pipeline()
    faces = MockFaceSource().load()[:30]
    frames = [Frame(f.frame_id, f.timestamp, None) for f in faces]
    out = pipe.run(frames, faces=faces)
    assert len(out) == 30
    for fo in out:
        assert fo.eye.reason == "sg2_not_configured"
        assert fo.decision.reason == "sg5_not_configured"


def test_a_module_that_raises_is_contained_and_counted():
    """One module throwing must degrade the system, not kill the run."""
    class Exploding:
        def process(self, *_args):
            raise RuntimeError("boom")

        def reset(self):
            pass

    pipe = Pipeline(sg2=Exploding(), sg3=YawnDetector(),
                    sg4=TemporalAnalyser(), sg5=DrowsinessDecider())
    out = run_on_mock(pipe)
    assert len(out) == 300
    assert any("sg2_eye:RuntimeError" in k for k in pipe.stats.module_errors)
    assert all(fo.eye.reason == "sg2_error" for fo in out)


def test_reset_makes_a_second_run_identical():
    """State leaking between clips would quietly invalidate every metric you report."""
    pipe = full_pipeline()
    first = [fo.decision.state for fo in run_on_mock(pipe)]
    second = [fo.decision.state for fo in run_on_mock(pipe)]
    assert first == second


def test_build_default_pipeline_loads_the_four_pure_python_modules():
    pipe = build_default_pipeline(need_sg1=False)
    assert pipe.sg2 is not None and pipe.sg3 is not None
    assert pipe.sg4 is not None and pipe.sg5 is not None
