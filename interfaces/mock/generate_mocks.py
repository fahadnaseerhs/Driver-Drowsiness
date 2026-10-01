"""Generate standardised mock inputs/outputs for every interface in the pipeline.

    python interfaces/mock/generate_mocks.py

Why this exists
---------------
The guide is explicit: "No pair should wait for the preceding module to be
completed" and "Each downstream group must be able to develop against either the
real upstream output or standardised mock input." This script is that standard
mock input. It is deterministic -- no randomness, no seeds -- so two students on
two machines get byte-identical files and can compare results meaningfully.

What it writes (into interfaces/mock/)
-------------------------------------
    mock_face.json      300 FaceResult     -- SG-1 output, the input for SG-2/SG-3
    mock_eye.json       300 EyeResult      -- SG-2 output, the input for SG-4
    mock_yawn.json      300 YawnResult     -- SG-3 output, the input for SG-4
    mock_temporal.json  300 TemporalResult -- SG-4 output, the input for SG-5
    scenario.json       the ground-truth timeline the above were built from

The scripted 10-second scenario (300 frames @ 30 FPS)
----------------------------------------------------
    0.0 - 2.0 s   alert driver, two normal blinks (~120 ms each)
    2.2 - 3.4 s   a yawn (mouth wide open), eyes still mostly open
    4.0 - 5.0 s   alert, one normal blink
    5.2 - 7.0 s   SUSTAINED eye closure, 1.8 s  <-- must end in state=ALERT
    7.0 - 8.0 s   microsleeps: repeated long closures
    8.0 - 9.0 s   NO FACE (driver turns away)   <-- exercises empty behaviour
    9.0 - 10.0 s  recovery, eyes open

The landmarks are synthetic but geometrically consistent, so SG-2 and SG-3 can
run their real EAR/MAR maths on mock_face.json and get the curve the scenario
describes. They are NOT a substitute for real clips: use them for interface and
unit tests, and real data for the accuracy numbers that get graded.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from interfaces.contracts import (  # noqa: E402
    TARGET_FPS,
    BBox,
    EyeResult,
    EyeState,
    FaceResult,
    TemporalResult,
    YawnResult,
    to_dict,
)

OUT_DIR = Path(__file__).resolve().parent
N_FRAMES = 300
FPS = TARGET_FPS
DT = 1.0 / FPS

# Geometry of the synthetic driver face, in full-frame pixels.
FACE_CX, FACE_CY = 640.0, 360.0
FACE_W, FACE_H = 240.0, 300.0
EYE_HALF_W = 24.0                 # half the eye corner-to-corner width
EYE_DY = -40.0                    # eye centre offset from face centre
EYE_DX = 55.0                     # eye centre horizontal offset
MOUTH_DY = 80.0
MOUTH_HALF_W = 45.0

EAR_OPEN = 0.30                   # aperture/width ratio when fully open
EAR_CLOSED = 0.07
MAR_CLOSED = 0.05
MAR_YAWN = 0.65

# The two ratio definitions this mock is built to satisfy exactly, so SG-2 and
# SG-3 can run their real maths on mock_face.json and recover the scenario curve.
# These are the agreed V1 definitions -- if a sub-group changes them, say so in
# its README and regenerate nothing: the mock stays the reference.
#
#   EAR = (|p37-p41| + |p38-p40|) / (2 * |p36-p39|)        [0-indexed iBUG]
#   MAR = |p51-p57| / |p48-p54|                            [0-indexed iBUG]
#
# MAR_WIDTH_SCALE maps a target MAR onto the synthetic lip-ellipse half-height.
# With the simple |51-57| / |48-54| definition above the mapping is 1:1.
MAR_WIDTH_SCALE = 1.0

# SG-2 / SG-3 baseline thresholds. Duplicated in the module configs; these are
# only used here to label the mock outputs consistently with the scenario.
EAR_THRESHOLD = 0.21
MAR_THRESHOLD = 0.45
# A blink is a SHORT closure. Without these bounds the 1.8 s microsleep would be
# labelled as a blink in mock_eye.json, over-reporting blink rate to SG-4 and
# disagreeing with what a correct SG-2 produces. Keep in step with
# module_sg2/configs/default.yaml.
MIN_BLINK_S = 0.06
MAX_BLINK_S = 0.50


# --------------------------------------------------------------------------- #
# Scenario timeline
# --------------------------------------------------------------------------- #
def _closed_intervals() -> list[tuple[float, float]]:
    """Seconds during which the eyes are closed."""
    return [
        (0.70, 0.82),       # normal blink
        (1.60, 1.72),       # normal blink
        (2.80, 2.92),       # blink during the yawn
        (4.40, 4.54),       # normal blink
        (5.20, 7.00),       # SUSTAINED closure, 1.8 s -> ALERT
        (7.25, 7.60),       # microsleep
        (7.75, 7.98),       # microsleep
    ]


def _yawn_intervals() -> list[tuple[float, float]]:
    return [(2.20, 3.40)]


def _noface_intervals() -> list[tuple[float, float]]:
    return [(8.00, 9.00)]


def _in(t: float, spans: list[tuple[float, float]]) -> bool:
    return any(a <= t < b for a, b in spans)


def eye_open_fraction(t: float) -> float:
    """1.0 = fully open, 0.0 = fully closed, with a smooth lid transition."""
    for a, b in _closed_intervals():
        ramp = 0.04                       # 40 ms to close / open
        if a - ramp <= t < a:
            return 1.0 - (t - (a - ramp)) / ramp
        if a <= t < b:
            return 0.0
        if b <= t < b + ramp:
            return (t - b) / ramp
    return 1.0


def mouth_open_fraction(t: float) -> float:
    """0.0 = closed, 1.0 = full yawn, with a smooth rise and fall."""
    for a, b in _yawn_intervals():
        if a <= t < b:
            phase = (t - a) / (b - a)
            return math.sin(math.pi * phase) ** 0.5     # quick rise, slow fall
    return 0.0


# --------------------------------------------------------------------------- #
# Synthetic 68-point landmark generation
# --------------------------------------------------------------------------- #
def _eye_points(cx: float, cy: float, aperture: float) -> list[tuple[float, float]]:
    """Six points in iBUG order: outer corner, 2 upper lid, inner corner, 2 lower lid.

    Laid out so the standard EAR formula
        (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    evaluates to exactly ``aperture`` -- which keeps the mock honest.
    """
    w, h = EYE_HALF_W, aperture * EYE_HALF_W
    return [
        (cx - w, cy),              # p1 outer corner
        (cx - w / 3.0, cy - h),    # p2 upper
        (cx + w / 3.0, cy - h),    # p3 upper
        (cx + w, cy),              # p4 inner corner
        (cx + w / 3.0, cy + h),    # p5 lower
        (cx - w / 3.0, cy + h),    # p6 lower
    ]


def _lip_ellipse(cx: float, cy: float, half_w: float, half_h: float, n: int,
                 start: float) -> list[tuple[float, float]]:
    """n points anticlockwise around an ellipse, starting at angle ``start`` rad."""
    pts = []
    for i in range(n):
        a = start + 2.0 * math.pi * i / n
        pts.append((cx + half_w * math.cos(a), cy + half_h * math.sin(a)))
    return pts


def build_landmarks(t: float) -> list[tuple[float, float]]:
    """68 iBUG-ordered landmarks for the synthetic driver at time ``t``."""
    eo, mo = eye_open_fraction(t), mouth_open_fraction(t)
    # A gentle head sway so downstream code cannot assume a static face.
    sway_x = 6.0 * math.sin(2.0 * math.pi * t / 4.0)
    sway_y = 3.0 * math.sin(2.0 * math.pi * t / 6.0)
    cx, cy = FACE_CX + sway_x, FACE_CY + sway_y

    pts: list[tuple[float, float]] = []

    # 0-16 jaw line, 17-26 eyebrows, 27-35 nose: present and plausible so that
    # anything computing a face-relative normalisation has real numbers to use.
    for i in range(17):
        a = math.pi * (0.10 + 0.80 * i / 16.0)
        pts.append((cx - (FACE_W / 2) * math.cos(a), cy + (FACE_H / 2) * math.sin(a) * 0.55))
    for i in range(5):
        pts.append((cx - EYE_DX - 30 + 15 * i, cy + EYE_DY - 28 - (4 if i in (1, 2, 3) else 0)))
    for i in range(5):
        pts.append((cx + EYE_DX - 30 + 15 * i, cy + EYE_DY - 28 - (4 if i in (1, 2, 3) else 0)))
    for i in range(4):
        pts.append((cx, cy + EYE_DY + 12 * i))                      # 27-30 bridge
    for i in range(5):
        pts.append((cx - 16 + 8 * i, cy + EYE_DY + 46))             # 31-35 nostrils

    aperture = EAR_CLOSED + (EAR_OPEN - EAR_CLOSED) * eo
    pts += _eye_points(cx - EYE_DX, cy + EYE_DY, aperture)          # 36-41 left
    pts += _eye_points(cx + EYE_DX, cy + EYE_DY, aperture)          # 42-47 right

    mar = MAR_CLOSED + (MAR_YAWN - MAR_CLOSED) * mo
    mh = mar * MAR_WIDTH_SCALE * MOUTH_HALF_W
    pts += _lip_ellipse(cx, cy + MOUTH_DY, MOUTH_HALF_W, mh, 12, math.pi)        # 48-59
    pts += _lip_ellipse(cx, cy + MOUTH_DY, MOUTH_HALF_W * 0.72, mh * 0.72, 8, math.pi)  # 60-67

    assert len(pts) == 68, len(pts)
    return pts


def _roi_from(points: list[tuple[float, float]], pad: float,
              w: int = 1280, h: int = 720) -> BBox:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    return BBox(int(x0), int(y0), int(x1 - x0), int(y1 - y0)).clip(w, h)


# --------------------------------------------------------------------------- #
# Per-interface sequence builders
# --------------------------------------------------------------------------- #
def build_face_sequence() -> list[FaceResult]:
    out = []
    for i in range(N_FRAMES):
        t = i * DT
        if _in(t, _noface_intervals()):
            out.append(FaceResult.empty(i, round(t, 4), reason="no_face"))
            continue
        lm = build_landmarks(t)
        out.append(FaceResult(
            frame_id=i,
            timestamp=round(t, 4),
            valid=True,
            reason="",
            face_box=_roi_from(lm, pad=10.0),
            landmarks=[(round(x, 2), round(y, 2)) for x, y in lm],
            # Subject-relative, per the iBUG convention fixed in contracts.py:
            # 36:42 is the driver's RIGHT eye, 42:48 the driver's LEFT eye.
            right_eye_roi=_roi_from(lm[36:42], pad=8.0),
            left_eye_roi=_roi_from(lm[42:48], pad=8.0),
            mouth_roi=_roi_from(lm[48:60], pad=10.0),
            confidence=0.97,
            yaw_deg=round(4.0 * math.sin(2 * math.pi * t / 4.0), 2),
            pitch_deg=0.0,
            roll_deg=0.0,
        ))
    return out


def build_eye_sequence() -> list[EyeResult]:
    """SG-2's *expected* output for the scenario -- the reference SG-4 develops against."""
    out: list[EyeResult] = []
    closed_run = 0.0
    prev_closed = False
    for i in range(N_FRAMES):
        t = i * DT
        if _in(t, _noface_intervals()):
            closed_run, prev_closed = 0.0, False
            out.append(EyeResult.empty(i, round(t, 4), reason="no_eye_roi"))
            continue

        eo = eye_open_fraction(t)
        ear = EAR_CLOSED + (EAR_OPEN - EAR_CLOSED) * eo
        is_closed = ear < EAR_THRESHOLD
        # A blink is reported on the frame the closure ENDS, and only if the
        # closure was short enough to be a blink rather than a microsleep.
        blink_completed = (
            prev_closed and not is_closed
            and MIN_BLINK_S <= closed_run <= MAX_BLINK_S
        )
        closed_run = closed_run + DT if is_closed else 0.0
        prev_closed = is_closed

        out.append(EyeResult(
            frame_id=i, timestamp=round(t, 4), valid=True, reason="",
            ear_left=round(ear, 4), ear_right=round(ear, 4), ear=round(ear, 4),
            eye_state=EyeState.CLOSED if is_closed else EyeState.OPEN,
            blink_event=blink_completed,
            closure_duration_s=round(closed_run, 4),
            confidence=0.95,
        ))
    return out


def build_yawn_sequence() -> list[YawnResult]:
    out: list[YawnResult] = []
    open_run = 0.0
    prev_open = False
    for i in range(N_FRAMES):
        t = i * DT
        if _in(t, _noface_intervals()):
            open_run, prev_open = 0.0, False
            out.append(YawnResult.empty(i, round(t, 4), reason="no_mouth_roi"))
            continue

        mar = MAR_CLOSED + (MAR_YAWN - MAR_CLOSED) * mouth_open_fraction(t)
        wide = mar > MAR_THRESHOLD
        open_run = open_run + DT if wide else 0.0
        completed = prev_open and not wide
        prev_open = wide

        out.append(YawnResult(
            frame_id=i, timestamp=round(t, 4), valid=True, reason="",
            mar=round(mar, 4), yawn_flag=wide, yawn_event=completed,
            yawn_duration_s=round(open_run, 4), confidence=0.90,
        ))
    return out


def build_temporal_sequence(eyes: list[EyeResult], yawns: list[YawnResult],
                            window_s: float = 3.0) -> list[TemporalResult]:
    """SG-4's *expected* output -- the reference SG-5 develops against."""
    out: list[TemporalResult] = []
    win = int(window_s * FPS)
    for i in range(N_FRAMES):
        t = i * DT
        lo = max(0, i - win + 1)
        e_win = [e for e in eyes[lo:i + 1] if e.valid]
        y_win = [y for y in yawns[lo:i + 1] if y.valid]
        span = (i - lo + 1) * DT

        if not e_win:
            out.append(TemporalResult.empty(i, round(t, 4), reason="no_valid_eye_data"))
            continue

        closed = sum(1 for e in e_win if e.eye_state is EyeState.CLOSED)
        perclos = closed / len(e_win)
        blinks = sum(1 for e in e_win if e.blink_event)
        yawn_events = sum(1 for y in y_win if y.yawn_event)
        longest = max((e.closure_duration_s for e in e_win), default=0.0)
        avg_ear = sum(e.ear for e in e_win if e.ear is not None) / len(e_win)

        # Baseline fusion: PERCLOS dominates, sustained closure is decisive,
        # yawning contributes a smaller amount. SG-4/SG-5 must revisit these
        # weights with evidence (Labs 5-7); this is only a starting point.
        score = min(1.0, 0.60 * min(1.0, perclos / 0.40)
                    + 0.30 * min(1.0, longest / 1.50)
                    + 0.10 * min(1.0, yawn_events / 1.0))

        out.append(TemporalResult(
            frame_id=i, timestamp=round(t, 4), valid=True, reason="",
            window_s=round(span, 4), window_filled=(i - lo + 1) >= win,
            perclos=round(perclos, 4),
            blink_rate_per_min=round(blinks * 60.0 / max(span, 1e-6), 2),
            yawn_rate_per_min=round(yawn_events * 60.0 / max(span, 1e-6), 2),
            longest_closure_s=round(longest, 4),
            avg_ear=round(avg_ear, 4),
            drowsy_score=round(score, 4),
            confidence=round(len(e_win) / max(i - lo + 1, 1), 3),
        ))
    return out


# --------------------------------------------------------------------------- #
def _dump(name: str, payloads: list) -> Path:
    path = OUT_DIR / name
    path.write_text(
        json.dumps([to_dict(p) for p in payloads], indent=1) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    faces = build_face_sequence()
    eyes = build_eye_sequence()
    yawns = build_yawn_sequence()
    temporal = build_temporal_sequence(eyes, yawns)

    scenario = {
        "description": "Scripted 10 s driver-drowsiness scenario, 300 frames @ 30 FPS.",
        "fps": FPS,
        "n_frames": N_FRAMES,
        "frame_size": [1280, 720],
        "ground_truth": {
            "eyes_closed_s": _closed_intervals(),
            "yawn_s": _yawn_intervals(),
            "no_face_s": _noface_intervals(),
        },
        # TARGET behaviour -- what the team WANTS SG-5 to output. This is a design
        # goal for Labs 5-7, NOT a description of what the current baseline does.
        # The baseline presently raises ALERT at ~6.20 s and never clears it before
        # the clip ends (see documentation/baseline_findings.md). Do not "fix" that
        # by tuning against this synthetic clip -- tune on real data.
        "target_behaviour": {
            "alert_s": [[6.2, 8.0]],
            "states": {
                "OK": [[0.0, 5.2], [9.3, 10.0]],
                "WARN": [[5.2, 6.2]],
                "ALERT": [[6.2, 8.0]],
            },
        },
        "thresholds_used_to_label": {"ear": EAR_THRESHOLD, "mar": MAR_THRESHOLD},
        "note": (
            "Synthetic geometry for interface and unit tests. Accuracy figures "
            "that get graded must come from real clips -- see datasets/README.md."
        ),
    }
    (OUT_DIR / "scenario.json").write_text(
        json.dumps(scenario, indent=1) + "\n", encoding="utf-8")

    for name, seq in (("mock_face.json", faces), ("mock_eye.json", eyes),
                      ("mock_yawn.json", yawns), ("mock_temporal.json", temporal)):
        _dump(name, seq)

    n_alert = sum(1 for p in temporal if p.drowsy_score >= 0.70)
    print(f"wrote {N_FRAMES} frames per interface to {OUT_DIR}")
    print(f"  faces valid     : {sum(1 for f in faces if f.valid)}/{N_FRAMES}")
    print(f"  blinks labelled : {sum(1 for e in eyes if e.blink_event)}")
    print(f"  yawn events     : {sum(1 for y in yawns if y.yawn_event)}")
    print(f"  max EAR         : {max(e.ear for e in eyes if e.valid):.3f}")
    print(f"  min EAR         : {min(e.ear for e in eyes if e.valid):.3f}")
    print(f"  max MAR         : {max(y.mar for y in yawns if y.valid):.3f}")
    print(f"  peak drowsy_score: {max(p.drowsy_score for p in temporal):.3f}")
    print(f"  frames with drowsy_score >= 0.70: {n_alert}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
