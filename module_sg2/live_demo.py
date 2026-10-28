"""Run SG-2 Eye State & Blink Analysis live: webcam -> SG-1 -> SG-2 -> HUD.

    python module_sg2/live_demo.py                          # laptop webcam 0
    python module_sg2/live_demo.py --source 1               # another camera
    python module_sg2/live_demo.py --source clip.mp4        # a recorded clip
    python module_sg2/live_demo.py --dump module_sg2/results/live01.json

This is a demo and evidence tool, not a pipeline stage. It reuses the real modules
unchanged: SG-1's FaceLandmarkDetector builds the FaceResult and SG-2's
EyeStateAnalyser turns it into an EyeResult, so the HUD shows exactly what SG-4
would receive.

The on-screen DROWSINESS ALERT is a local stand-in for SG-4/SG-5: it fires when
``closure_duration_s`` passes ``--alert-s``. The team's real decision (PERCLOS
window + hysteresis) lives in SG-4/SG-5 -- do not tune those from here.

Keys:  q / Esc quit    r reset counters    [ / ] EAR threshold -/+ 0.01    m mirror
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.config import load_config  # noqa: E402
from interfaces.contracts import (  # noqa: E402
    LEFT_EYE_IDX,
    RIGHT_EYE_IDX,
    EyeResult,
    EyeState,
    FaceResult,
    validate,
)
from module_sg2.src.eye_state import EyeStateAnalyser  # noqa: E402

DEFAULT_CONFIG = Path(__file__).parent / "configs" / "default.yaml"
SG1_CONFIG = ROOT / "module_sg1" / "configs" / "default.yaml"
WINDOW = "SG-2 Eye / Blink Analysis  (q to quit)"

# BGR colours
GREEN, RED, YELLOW, WHITE, GREY = (80, 220, 80), (40, 40, 235), (40, 210, 240), (245, 245, 245), (150, 150, 150)


# --------------------------------------------------------------------------- #
# Pure helpers -- no OpenCV, so tests/test_live_demo.py runs in bare CI.
# --------------------------------------------------------------------------- #
class BlinkRate:
    """Blinks per minute over a sliding window, from EyeResult.blink_event."""

    def __init__(self, window_s: float = 60.0, warmup_s: float = 10.0) -> None:
        self.window_s, self.warmup_s = window_s, warmup_s
        self.reset()

    def reset(self) -> None:
        self._events: deque[float] = deque()
        self._start: float | None = None

    def update(self, ts: float, blink_event: bool) -> float | None:
        """Return blinks/min, or None while there is too little history to say."""
        if self._start is None:
            self._start = ts
        if blink_event:
            self._events.append(ts)
        while self._events and ts - self._events[0] > self.window_s:
            self._events.popleft()
        span = min(ts - self._start, self.window_s)
        # A rate from 2 s of video is noise, not a measurement.
        return None if span < self.warmup_s else len(self._events) * 60.0 / span


def alert_active(eye: EyeResult, alert_s: float) -> bool:
    """Demo alarm: eyes continuously closed for at least ``alert_s`` seconds."""
    return eye.valid and eye.eye_state is EyeState.CLOSED and eye.closure_duration_s >= alert_s


def check_mediapipe() -> str | None:
    """Return a fix-it message if MediaPipe is missing or lacks the Solutions API."""
    try:
        import mediapipe as mp
    except ImportError as exc:
        return f"mediapipe is not importable ({exc}).\n  Fix: pip install -r requirements.txt"
    if not hasattr(mp, "solutions"):
        # The two real causes on Windows: a mediapipe build without the legacy
        # Solutions API (newer wheels / unsupported Python), or a local file or
        # folder called "mediapipe" shadowing the package.
        return (
            f"this mediapipe ({getattr(mp, '__version__', '?')}, loaded from "
            f"{getattr(mp, '__file__', None) or 'a namespace folder'}) has no 'solutions' API.\n"
            "  Fix: use a Python 3.10-3.12 venv and  pip install mediapipe==0.10.14\n"
            "       and make sure no file or folder named 'mediapipe' sits next to your script."
        )
    return None


# --------------------------------------------------------------------------- #
# Drawing
# --------------------------------------------------------------------------- #
def _view_pt(p: tuple[float, float], w: int, mirror: bool) -> tuple[int, int]:
    # SG-1 always sees the un-mirrored frame (contract rule); only the display flips.
    return (int(w - 1 - p[0]) if mirror else int(p[0]), int(p[1]))


def draw_eyes(cv2, view, face: FaceResult, eye: EyeResult, mirror: bool) -> None:
    if not face.valid or len(face.landmarks) < 48:
        return
    w = view.shape[1]
    colour = RED if eye.eye_state is EyeState.CLOSED else GREEN
    for idx in (RIGHT_EYE_IDX, LEFT_EYE_IDX):
        pts = [_view_pt(face.landmarks[i], w, mirror) for i in idx]
        for a, b in zip(pts, pts[1:] + pts[:1], strict=True):
            cv2.line(view, a, b, colour, 1, cv2.LINE_AA)
        # The three distances EAR is built from: two lid heights, one eye width.
        for a, b in ((1, 5), (2, 4), (0, 3)):
            cv2.line(view, pts[a], pts[b], YELLOW, 1, cv2.LINE_AA)
        for p in pts:
            cv2.circle(view, p, 2, colour, -1, cv2.LINE_AA)


def _panel(cv2, view, x: int, y: int, w: int, h: int, alpha: float = 0.55) -> None:
    roi = view[y:y + h, x:x + w]
    roi[:] = cv2.addWeighted(roi, 1 - alpha, roi * 0, alpha, 0)


def _text(cv2, view, s: str, org: tuple[int, int], colour=WHITE, scale: float = 0.55,
          thick: int = 1) -> None:
    cv2.putText(view, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, colour, thick, cv2.LINE_AA)


def draw_hud(cv2, view, eye: EyeResult, analyser: EyeStateAnalyser,
             rate: float | None, fps: float, violations: int, alert_s: float) -> None:
    _panel(cv2, view, 8, 8, 330, 182)
    _text(cv2, view, "SG-2 Eye / Blink  (EAR baseline)", (18, 32), YELLOW, 0.58, 2)
    if eye.valid:
        _text(cv2, view, f"EAR  avg {eye.ear:.3f}   R {eye.ear_right or 0:.3f}  "
                         f"L {eye.ear_left or 0:.3f}", (18, 58))
        closed = eye.eye_state is EyeState.CLOSED
        _text(cv2, view, f"Eyes {eye.eye_state.value}", (18, 84), RED if closed else GREEN, 0.6, 2)
    else:
        _text(cv2, view, "EAR  --", (18, 58), GREY)
        _text(cv2, view, f"NO FACE  ({eye.reason})", (18, 84), YELLOW, 0.6, 2)
    rate_s = "warming up" if rate is None else f"{rate:.1f} /min"
    _text(cv2, view, f"Blinks {analyser.blink_count}   ({rate_s})", (18, 110))
    _text(cv2, view, f"Closed {eye.closure_duration_s:.2f} s   (alert at {alert_s:.1f} s)", (18, 136))
    _text(cv2, view, f"Thresh {analyser.ear_threshold:.2f} +/- {analyser.hysteresis:.2f}"
                     f"   FPS {fps:.1f}", (18, 162))
    _text(cv2, view, f"Contract violations {violations}", (18, 182),
          GREEN if violations == 0 else RED, 0.45)

    h, w = view.shape[:2]
    _text(cv2, view, "q quit  r reset  [ ] threshold  m mirror", (w - 330, h - 12), GREY, 0.45)


def draw_ear_graph(cv2, view, history: deque, analyser: EyeStateAnalyser) -> None:
    """Rolling EAR trace with the open/close thresholds, bottom-left."""
    h = view.shape[0]
    gx, gy, gw, gh, ymax = 8, h - 108, 330, 80, 0.45
    _panel(cv2, view, gx, gy, gw, gh)

    def to_y(v: float) -> int:
        return int(gy + gh - min(max(v, 0.0), ymax) / ymax * gh)

    lo = analyser.ear_threshold - analyser.hysteresis
    hi = analyser.ear_threshold + analyser.hysteresis
    for v, c in ((lo, RED), (hi, GREEN)):
        cv2.line(view, (gx, to_y(v)), (gx + gw, to_y(v)), c, 1)
    step = gw / max(1, history.maxlen - 1)
    prev = None
    for i, v in enumerate(history):
        cur = None if v is None else (int(gx + i * step), to_y(v))
        if cur and prev:
            cv2.line(view, prev, cur, YELLOW, 2, cv2.LINE_AA)
        prev = cur
    _text(cv2, view, "EAR (last 5 s)", (gx + 6, gy + 16), GREY, 0.42)


def draw_alert(cv2, view, eye: EyeResult) -> None:
    h, w = view.shape[:2]
    cv2.rectangle(view, (0, 0), (w - 1, h - 1), RED, 14)
    msg = f"DROWSINESS ALERT  -  eyes closed {eye.closure_duration_s:.1f} s"
    (tw, th), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
    x, y = (w - tw) // 2, h // 2
    cv2.rectangle(view, (x - 16, y - th - 16), (x + tw + 16, y + 16), RED, -1)
    _text(cv2, view, msg, (x, y), WHITE, 0.9, 2)


def make_beeper(enabled: bool):
    """Non-blocking alarm sound on Windows; silent elsewhere or with --no-sound."""
    if not enabled or sys.platform != "win32":
        return lambda: None
    import winsound

    return lambda: winsound.PlaySound("SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SG-2 live eye/blink demo (webcam or clip).")
    ap.add_argument("--source", default="0", help="camera index (0, 1, ...) or a video file path")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="SG-2 YAML config")
    ap.add_argument("--alert-s", type=float, default=1.5,
                    help="demo alarm: continuous closure in seconds (default 1.5)")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--dump", type=Path, help="write every EyeResult to this JSON file")
    ap.add_argument("--no-mirror", action="store_true", help="show the raw (un-mirrored) frame")
    ap.add_argument("--no-sound", action="store_true", help="disable the alarm beep")
    ap.add_argument("--headless", action="store_true", help="no window (smoke tests / CI)")
    ap.add_argument("--max-frames", type=int, default=0, help="stop after N frames (0 = no limit)")
    args = ap.parse_args(argv)

    err = check_mediapipe()
    if err:
        print(f"[SG-2] {err}", file=sys.stderr)
        return 2

    import cv2

    from common.jsonio import write_sequence
    from common.video import VideoFileSource, WebcamSource
    from module_sg1.src.face_landmarks import FaceLandmarkDetector

    detector = FaceLandmarkDetector(load_config(SG1_CONFIG) if SG1_CONFIG.exists() else None)
    analyser = EyeStateAnalyser(load_config(args.config))
    source = (WebcamSource(args.source, args.width, args.height) if args.source.isdigit()
              else VideoFileSource(args.source))

    mirror = not args.no_mirror
    beep, last_beep = make_beeper(not args.no_sound), 0.0
    rate_meter = BlinkRate()
    history: deque[float | None] = deque(maxlen=150)        # ~5 s at 30 FPS
    ticks: deque[float] = deque(maxlen=30)
    results: list[EyeResult] = []
    n_frames = n_valid = violations = 0
    longest_closure = latency_sum = 0.0

    print(f"[SG-2] source={args.source}  config={args.config.name}  alert>={args.alert_s}s")
    try:
        for frame in source:
            t0 = time.perf_counter()
            face = detector.process(frame)
            eye = analyser.process(face)
            latency_sum += time.perf_counter() - t0

            n_frames += 1
            n_valid += eye.valid
            violations += bool(validate(eye))
            longest_closure = max(longest_closure, eye.closure_duration_s)
            if args.dump:
                results.append(eye)
            rate = rate_meter.update(eye.timestamp, eye.blink_event)
            history.append(eye.ear if eye.valid else None)
            ticks.append(time.perf_counter())
            fps = (len(ticks) - 1) / (ticks[-1] - ticks[0]) if len(ticks) > 1 else 0.0

            alarm = alert_active(eye, args.alert_s)
            if alarm and time.monotonic() - last_beep > 1.0:
                beep()
                last_beep = time.monotonic()

            if not args.headless:
                view = cv2.flip(frame.image, 1) if mirror else frame.image.copy()
                draw_eyes(cv2, view, face, eye, mirror)
                draw_hud(cv2, view, eye, analyser, rate, fps, violations, args.alert_s)
                draw_ear_graph(cv2, view, history, analyser)
                if alarm:
                    draw_alert(cv2, view, eye)
                cv2.imshow(WINDOW, view)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
                if key == ord("r"):
                    analyser.reset()
                    rate_meter.reset()
                elif key == ord("["):
                    analyser.ear_threshold = round(max(0.05, analyser.ear_threshold - 0.01), 2)
                elif key == ord("]"):
                    analyser.ear_threshold = round(min(0.40, analyser.ear_threshold + 0.01), 2)
                elif key == ord("m"):
                    mirror = not mirror

            if args.max_frames and n_frames >= args.max_frames:
                break
    except RuntimeError as exc:
        print(f"[SG-2] {exc}\n  Close other apps using the camera (Teams, Zoom, Camera), "
              "try --source 1, and check Windows Settings > Privacy & security > Camera.",
              file=sys.stderr)
        return 1
    finally:
        detector.close()
        if not args.headless:
            cv2.destroyAllWindows()

    if args.dump:
        print(f"[SG-2] wrote {len(results)} EyeResults -> {write_sequence(args.dump, results)}")
    mean_ms = latency_sum / n_frames * 1000 if n_frames else 0.0
    print(f"[SG-2] frames {n_frames}  valid {n_valid}  blinks {analyser.blink_count}  "
          f"longest closure {longest_closure:.2f}s  SG1+SG2 latency {mean_ms:.1f} ms/frame  "
          f"contract violations {violations}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
