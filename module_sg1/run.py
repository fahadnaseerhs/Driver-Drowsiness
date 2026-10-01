"""Run SG-1 Driver Face & Landmark Detection standalone.

    # live camera, draw the 68 landmarks with their index numbers
    python module_sg1/run.py --source 0 --verify-landmarks

    # a recorded clip, save the FaceResult sequence for downstream groups
    python module_sg1/run.py --source clip.mp4 --dump module_sg1/results/clip01.json

--verify-landmarks is the one that matters before Lab 4. The 468->68 mapping in
src/face_landmarks.py is unverified. Look at your own face and check that index 36
and 39 sit on the corners of your RIGHT eye, 48 and 54 on your mouth corners, and
51/57 on the top and bottom of your upper/lower lip. If any are wrong, SG-2's EAR
and SG-3's MAR are silently wrong and nothing will crash to tell you.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.config import load_config  # noqa: E402
from common.jsonio import write_sequence  # noqa: E402
from common.timing import Stopwatch  # noqa: E402
from common.video import make_source  # noqa: E402
from interfaces.contracts import validate  # noqa: E402
from module_sg1.src.face_landmarks import FaceLandmarkDetector  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run SG-1 face/landmark detection.")
    ap.add_argument("--source", default="0", help='camera index like "0", or a video path')
    ap.add_argument("--config", type=Path,
                    default=Path(__file__).parent / "configs" / "default.yaml")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dump", type=Path, default=None)
    ap.add_argument("--verify-landmarks", action="store_true",
                    help="draw every landmark with its index -- USE THIS BEFORE LAB 4")
    args = ap.parse_args(argv)

    try:
        import cv2
    except ImportError:
        print("OpenCV is required: pip install -r requirements.txt", file=sys.stderr)
        return 2

    cfg = load_config(args.config) if args.config.exists() else {}
    det = FaceLandmarkDetector(cfg)
    timer = Stopwatch("sg1")
    outputs, violations = [], 0

    try:
        source = make_source(args.source)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot open source {args.source!r}: {exc}", file=sys.stderr)
        return 2

    for i, frame in enumerate(source):
        if args.limit and i >= args.limit:
            break
        with timer:
            res = det.process(frame)
        outputs.append(res)
        if validate(res):
            violations += 1

        if args.verify_landmarks and frame.image is not None:
            img = frame.image.copy()
            if res.valid:
                for idx, (x, y) in enumerate(res.landmarks):
                    cv2.circle(img, (int(x), int(y)), 1, (0, 255, 0), -1)
                    if idx in (36, 39, 42, 45, 48, 54, 51, 57):
                        cv2.putText(img, str(idx), (int(x) + 3, int(y) - 3),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
                for box, colour in ((res.face_box, (255, 255, 0)),
                                    (res.right_eye_roi, (0, 255, 255)),
                                    (res.left_eye_roi, (0, 255, 255)),
                                    (res.mouth_roi, (255, 0, 255))):
                    if box is not None:
                        cv2.rectangle(img, (box.x, box.y),
                                      (box.x + box.w, box.y + box.h), colour, 1)
            else:
                cv2.putText(img, res.reason, (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, (0, 0, 255), 2)
            cv2.imshow("SG-1 landmark verification (q to quit)", img)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    if args.verify_landmarks:
        cv2.destroyAllWindows()
    det.close()

    valid = sum(1 for r in outputs if r.valid)
    print("SG-1 Driver Face & Landmark Detection (MediaPipe FaceMesh baseline)")
    print(f"  source   : {args.source}")
    print(f"  frames   : {len(outputs)}  valid: {valid}  invalid: {len(outputs) - valid}")
    print(f"  detection rate: {valid / max(len(outputs), 1):.1%}")
    print(f"  timing   : {timer.summary()}")
    print(f"  contract : {'OK' if violations == 0 else f'{violations} VIOLATIONS'}")
    if args.dump:
        write_sequence(args.dump, outputs)
        print(f"  wrote    : {args.dump}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
