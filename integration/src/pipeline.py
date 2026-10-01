"""End-to-end pipeline: CAMERA -> SG-1 -> {SG-2, SG-3} -> SG-4 -> SG-5 -> ALERT.

This is the integration surface SG-6 deploys and every sub-group is graded against
at Integration Gates 1 (Lab 8) and 2 (Lab 11).

Three ways to run it, which is the point -- integration is progressive, not a
final-week event:

    # 1. No camera, no SG-1, no model weights. Replays mock_face.json.
    #    Works on day one, for everybody. Use this to prove your module wires up.
    python integration/run_pipeline.py --source mock

    # 2. A recorded clip through the real SG-1.
    python integration/run_pipeline.py --source datasets/samples/clip01.mp4

    # 3. Live camera (the demo path).
    python integration/run_pipeline.py --source 0 --display

Degraded operation is deliberate: if a module is missing or raises, the pipeline
records it in ``PipelineStats.module_errors`` and keeps going with that module's
empty payload. A pair being late must not stop the other four from integrating.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.timing import FPSMeter, Stopwatch  # noqa: E402
from interfaces.contracts import (  # noqa: E402
    DecisionResult,
    EyeResult,
    FaceResult,
    Frame,
    TemporalResult,
    YawnResult,
    validate,
)

STAGES = ("sg1_face", "sg2_eye", "sg3_yawn", "sg4_temporal", "sg5_decision")


@dataclass
class FrameOutput:
    """Everything the pipeline produced for one frame -- for logging and evaluation."""

    frame: Frame
    face: FaceResult
    eye: EyeResult
    yawn: YawnResult
    temporal: TemporalResult
    decision: DecisionResult


@dataclass
class PipelineStats:
    frames: int = 0
    timers: dict[str, Stopwatch] = field(default_factory=dict)
    module_errors: dict[str, int] = field(default_factory=dict)
    contract_violations: list[str] = field(default_factory=list)
    end_to_end: Stopwatch = field(default_factory=lambda: Stopwatch("end_to_end"))

    def report(self) -> dict[str, Any]:
        return {
            "frames": self.frames,
            "per_stage_ms": {k: v.summary() for k, v in self.timers.items()},
            "end_to_end": self.end_to_end.summary(),
            "module_errors": dict(self.module_errors),
            "contract_violations": self.contract_violations[:50],
            "contract_violation_count": len(self.contract_violations),
        }


class Pipeline:
    """Wires the five modules together and enforces the contract between them.

    Any stage may be None, in which case that stage emits its empty payload. This
    is what lets a pair develop before its upstream neighbour exists.
    """

    def __init__(
        self,
        sg1: Any = None,
        sg2: Any = None,
        sg3: Any = None,
        sg4: Any = None,
        sg5: Any = None,
        check_contracts: bool = True,
    ) -> None:
        self.sg1, self.sg2, self.sg3 = sg1, sg2, sg3
        self.sg4, self.sg5 = sg4, sg5
        self.check_contracts = check_contracts
        self.stats = PipelineStats()
        for name in STAGES:
            self.stats.timers[name] = Stopwatch(name)
        self.fps = FPSMeter()

    # ----------------------------------------------------------------------- #
    def reset(self) -> None:
        """Reset every stateful module. Call between clips -- SG-2/3/4/5 all hold
        temporal state, and leaking it across clips invalidates your metrics."""
        for m in (self.sg1, self.sg2, self.sg3, self.sg4, self.sg5):
            if m is not None and hasattr(m, "reset"):
                m.reset()

    def _guard(self, stage: str, fn, fallback):
        """Run one stage. On exception, record it and fall back to the empty payload."""
        try:
            with self.stats.timers[stage]:
                return fn()
        except Exception as exc:  # noqa: BLE001 -- one module must not kill the system
            self.stats.module_errors[f"{stage}:{type(exc).__name__}"] = (
                self.stats.module_errors.get(f"{stage}:{type(exc).__name__}", 0) + 1
            )
            return fallback()

    def _verify(self, payload: Any) -> None:
        if not self.check_contracts:
            return
        for err in validate(payload):
            self.stats.contract_violations.append(
                f"frame {payload.frame_id} {type(payload).__name__}: {err}")

    # ----------------------------------------------------------------------- #
    def process_frame(self, frame: Frame, face: FaceResult | None = None) -> FrameOutput:
        """Run one frame through every stage.

        ``face`` may be supplied directly to bypass SG-1 -- that is how the mock
        replay path works, and how SG-2..SG-5 integrate before SG-1 is ready.
        """
        fid, ts = frame.frame_id, frame.timestamp
        self.stats.end_to_end.__enter__()

        if face is None:
            face = (
                self._guard("sg1_face", lambda: self.sg1.process(frame),
                            lambda: FaceResult.empty(fid, ts, reason="sg1_error"))
                if self.sg1 is not None
                else FaceResult.empty(fid, ts, reason="sg1_not_configured")
            )
        self._verify(face)

        eye = (
            self._guard("sg2_eye", lambda: self.sg2.process(face),
                        lambda: EyeResult.empty(fid, ts, reason="sg2_error"))
            if self.sg2 is not None
            else EyeResult.empty(fid, ts, reason="sg2_not_configured")
        )
        self._verify(eye)

        yawn = (
            self._guard("sg3_yawn", lambda: self.sg3.process(face),
                        lambda: YawnResult.empty(fid, ts, reason="sg3_error"))
            if self.sg3 is not None
            else YawnResult.empty(fid, ts, reason="sg3_not_configured")
        )
        self._verify(yawn)

        temporal = (
            self._guard("sg4_temporal", lambda: self.sg4.process(eye, yawn),
                        lambda: TemporalResult.empty(fid, ts, reason="sg4_error"))
            if self.sg4 is not None
            else TemporalResult.empty(fid, ts, reason="sg4_not_configured")
        )
        self._verify(temporal)

        decision = (
            self._guard("sg5_decision", lambda: self.sg5.process(temporal),
                        lambda: DecisionResult.empty(fid, ts, reason="sg5_error"))
            if self.sg5 is not None
            else DecisionResult.empty(fid, ts, reason="sg5_not_configured")
        )

        self.stats.end_to_end.__exit__()
        # The pipeline owns the clock, so it -- not SG-5 -- fills in latency.
        decision.latency_ms = round(self.stats.end_to_end.last_ms, 3)
        self._verify(decision)

        self.stats.frames += 1
        self.fps.tick()
        return FrameOutput(frame, face, eye, yawn, temporal, decision)

    # ----------------------------------------------------------------------- #
    def run(self, source, faces: list[FaceResult] | None = None,
            limit: int | None = None, on_frame=None) -> list[FrameOutput]:
        """Drive the pipeline over a frame source.

        ``faces``: an optional pre-computed SG-1 output sequence (mock replay),
        indexed by position, used instead of calling SG-1.
        """
        out: list[FrameOutput] = []
        for i, frame in enumerate(source):
            if limit is not None and i >= limit:
                break
            face = faces[i] if faces is not None and i < len(faces) else None
            fo = self.process_frame(frame, face=face)
            out.append(fo)
            if on_frame is not None:
                on_frame(fo)
        return out


# --------------------------------------------------------------------------- #
def build_default_pipeline(need_sg1: bool, configs: dict[str, dict] | None = None) -> Pipeline:
    """Construct the pipeline from the baseline modules.

    SG-1 is imported lazily and only when ``need_sg1`` is True, because it pulls
    in MediaPipe -- the mock path must stay runnable with no models installed.
    Any module that fails to import is simply left out and the pipeline runs
    degraded, which is reported rather than hidden.
    """
    cfg = configs or {}
    sg1 = sg2 = sg3 = sg4 = sg5 = None
    missing: list[str] = []

    if need_sg1:
        try:
            from module_sg1.src.face_landmarks import FaceLandmarkDetector
            sg1 = FaceLandmarkDetector(cfg.get("sg1"))
        except Exception as exc:  # noqa: BLE001
            missing.append(f"SG-1 ({type(exc).__name__}: {exc})")

    for name, builder in (
        ("SG-2", lambda: __import__(
            "module_sg2.src.eye_state", fromlist=["EyeStateAnalyser"]
        ).EyeStateAnalyser(cfg.get("sg2"))),
        ("SG-3", lambda: __import__(
            "module_sg3.src.yawn_detect", fromlist=["YawnDetector"]
        ).YawnDetector(cfg.get("sg3"))),
        ("SG-4", lambda: __import__(
            "module_sg4.src.temporal", fromlist=["TemporalAnalyser"]
        ).TemporalAnalyser(cfg.get("sg4"))),
        ("SG-5", lambda: __import__(
            "module_sg5.src.decision", fromlist=["DrowsinessDecider"]
        ).DrowsinessDecider(cfg.get("sg5"))),
    ):
        try:
            built = builder()
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{name} ({type(exc).__name__}: {exc})")
            continue
        if name == "SG-2":
            sg2 = built
        elif name == "SG-3":
            sg3 = built
        elif name == "SG-4":
            sg4 = built
        else:
            sg5 = built

    if missing:
        print("[pipeline] running DEGRADED, modules unavailable: " + "; ".join(missing),
              file=sys.stderr)

    return Pipeline(sg1, sg2, sg3, sg4, sg5)


def wall_clock_now() -> float:
    return time.monotonic()
