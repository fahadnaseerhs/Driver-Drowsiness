"""SG-1 live landmark demo: webcam preview + a side console of live coordinates.

The window has two halves:

    LEFT   the camera feed with the 68 landmarks drawn, colour-coded per facial
           region, connected into their shapes, plus the face/eye/mouth ROI boxes.
    RIGHT  a console that updates every frame with the pixel coordinates of each
           landmark, grouped into jaw / brows / nose / eyes / lips.

Coordinates are FULL-FRAME pixels, origin top-left (the contract convention), and
eye sides are SUBJECT-relative: 36-41 is the driver's RIGHT eye, which appears on
the image's LEFT. The preview is deliberately NOT mirrored -- per the contract,
only a display may ever be mirrored, never the frame, and a mirrored preview with
un-mirrored coordinates would be confusing in a demo about coordinates.

    python module_sg1/demo_landmarks.py                 # default camera
    python module_sg1/demo_landmarks.py --source 1      # another camera index
    python module_sg1/demo_landmarks.py --source clip.mp4

Keys:  q quits.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.config import load_config  # noqa: E402
from common.timing import FPSMeter  # noqa: E402
from common.video import make_source  # noqa: E402
from module_sg1.src.face_landmarks import FaceLandmarkDetector  # noqa: E402

# The iBUG-68 regions. (name, index range, BGR colour, close the polyline?)
# Eye naming is subject-relative -- see interfaces/contracts.py.
GROUPS: tuple[tuple[str, range, tuple[int, int, int], bool], ...] = (
    ("JAW", range(0, 17), (180, 180, 180), False),
    ("RIGHT BROW", range(17, 22), (0, 165, 255), False),
    ("LEFT BROW", range(22, 27), (0, 165, 255), False),
    ("NOSE BRIDGE", range(27, 31), (0, 220, 220), False),
    ("NOSE BASE", range(31, 36), (0, 220, 220), False),
    ("RIGHT EYE (img-left)", range(36, 42), (255, 255, 0), True),
    ("LEFT EYE (img-right)", range(42, 48), (0, 255, 0), True),
    ("OUTER LIP", range(48, 60), (255, 0, 255), True),
    ("INNER LIP", range(60, 68), (180, 105, 255), True),
)

PANEL_W = 400
PANEL_BG = (24, 20, 16)


def draw_overlay(img, res) -> None:
    """Landmarks + region shapes + ROI boxes onto the camera frame, in place."""
    import cv2
    import numpy as np

    if not res.valid:
        cv2.putText(img, f"NO FACE: {res.reason}", (20, 44),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        return

    pts = np.array(res.landmarks, dtype=np.int32)
    for _, idx, colour, closed in GROUPS:
        cv2.polylines(img, [pts[idx.start:idx.stop]], closed, colour, 1, cv2.LINE_AA)
        for x, y in pts[idx.start:idx.stop]:
            cv2.circle(img, (x, y), 2, colour, -1, cv2.LINE_AA)

    for box, colour in ((res.face_box, (255, 255, 255)),
                        (res.right_eye_roi, (255, 255, 0)),
                        (res.left_eye_roi, (0, 255, 0)),
                        (res.mouth_roi, (255, 0, 255))):
        if box is not None:
            cv2.rectangle(img, (box.x, box.y), (box.x + box.w, box.y + box.h), colour, 1)


def draw_console(h: int, res, fps: float) -> "object":
    """Render the side console: per-group coordinates, two landmarks per row."""
    import cv2
    import numpy as np

    panel = np.full((h, PANEL_W, 3), PANEL_BG, dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX

    # Everything below must fit whatever height the camera delivers, including a
    # 480p fallback: 34 coordinate rows + 9 headers + the status block = 45 lines.
    line_h = max(9, h // 47)
    scale = line_h / 34.0
    y = line_h

    def put(text: str, colour=(200, 200, 200), bold=False) -> None:
        nonlocal y
        cv2.putText(panel, text, (10, y), font, scale, colour, 2 if bold else 1, cv2.LINE_AA)
        y += line_h

    put(f"SG-1 LANDMARK CONSOLE   {fps:5.1f} FPS", (255, 255, 255), bold=True)
    if not res.valid:
        put(f"frame {res.frame_id}: INVALID ({res.reason})", (0, 0, 255), bold=True)
        put("empty-behaviour rule: valid=False,")
        put("payload still delivered, nothing crashes.")
        return panel

    fb = res.face_box
    put(f"f {res.frame_id}  conf {res.confidence:.2f}  face {fb.x},{fb.y} {fb.w}x{fb.h}")

    for name, idx, colour, _ in GROUPS:
        put(f"{name}  [{idx.start}-{idx.stop - 1}]", colour, bold=True)
        for row_start in range(idx.start, idx.stop, 2):
            cells = []
            for i in range(row_start, min(row_start + 2, idx.stop)):
                x, yv = res.landmarks[i]
                cells.append(f"{i:2d} ({x:6.1f},{yv:6.1f})")
            put("   ".join(cells), colour)

    return panel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SG-1 live landmark demo with coordinate console.")
    ap.add_argument("--source", default="0", help='camera index like "0", or a video path')
    ap.add_argument("--config", type=Path,
                    default=Path(__file__).parent / "configs" / "default.yaml")
    args = ap.parse_args(argv)

    try:
        import cv2
        import numpy as np
    except ImportError:
        print("OpenCV is required: pip install -r requirements.txt", file=sys.stderr)
        return 2

    cfg = load_config(args.config) if args.config.exists() else {}
    det = FaceLandmarkDetector(cfg)
    fps = FPSMeter()

    try:
        source = make_source(args.source)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot open source {args.source!r}: {exc}", file=sys.stderr)
        return 2

    window = "SG-1 landmarks + live coordinates (q to quit)"
    try:
        for frame in source:
            if frame.image is None:
                print("source has no pixels (mock?) -- this demo needs a camera or a clip",
                      file=sys.stderr)
                return 2
            res = det.process(frame)
            img = frame.image.copy()
            draw_overlay(img, res)
            panel = draw_console(img.shape[0], res, fps.tick())
            cv2.imshow(window, np.hstack((img, panel)))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cv2.destroyAllWindows()
        det.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
