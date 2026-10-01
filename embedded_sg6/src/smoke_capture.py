"""SG-6: smoke-test camera capture ON ITS OWN, before wiring the pipeline to it.

    python3 -m embedded_sg6.src.smoke_capture                  # Jetson GStreamer, USB
    python3 -m embedded_sg6.src.smoke_capture --camera csi
    python3 -m embedded_sg6.src.smoke_capture --plain          # cv2.VideoCapture, for comparison

Why this exists as its own step: risk R7 is "camera or capture pipeline unstable on
Jetson". If capture is dropping frames, every downstream number is wrong in a way that
looks like an algorithm problem. Establish that the camera works and holds frame rate
BEFORE anything is attached to it, so you never debug SG-1 for a capture fault.

Reports achieved FPS and frame-interval jitter. Jitter matters as much as the mean: a
camera averaging 30 FPS while stalling for 200 ms every second will break SG-4's
timing-based windows even though the average looks fine.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Smoke-test camera capture.")
    ap.add_argument("--frames", type=int, default=150, help="frames to grab (default 150)")
    ap.add_argument("--camera", choices=["usb", "csi"], default="usb")
    ap.add_argument("--plain", action="store_true",
                    help="use cv2.VideoCapture instead of the GStreamer pipeline")
    ap.add_argument("--device", default="0",
                    help="with --plain: camera index or path (default 0)")
    args = ap.parse_args(argv)

    if args.plain:
        from common.video import WebcamSource
        source = WebcamSource(args.device)
        label = f"cv2.VideoCapture({args.device})"
    else:
        from embedded_sg6.src.capture_jetson import JetsonCameraSource
        source = JetsonCameraSource(camera=args.camera)
        label = f"GStreamer ({args.camera})"

    print(f"capturing {args.frames} frames via {label} ...")

    stamps: list[float] = []
    sizes: set[tuple[int, int]] = set()
    try:
        for i, frame in enumerate(source):
            stamps.append(time.perf_counter())
            if frame.image is not None:
                sizes.add((frame.image.shape[1], frame.image.shape[0]))
            if i + 1 >= args.frames:
                break
    except Exception as exc:  # noqa: BLE001
        print(f"\nCAPTURE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if len(stamps) < 2:
        print(f"\nonly {len(stamps)} frame(s) captured -- the camera is not delivering",
              file=sys.stderr)
        return 2

    intervals_ms = [(b - a) * 1000.0 for a, b in zip(stamps, stamps[1:], strict=False)]
    span = stamps[-1] - stamps[0]
    fps = (len(stamps) - 1) / span

    print(f"  frames captured : {len(stamps)}")
    print(f"  resolution(s)   : {sorted(sizes) if sizes else 'no image data'}")
    print(f"  achieved FPS    : {fps:.2f}")
    print(f"  interval mean   : {statistics.mean(intervals_ms):.2f} ms")
    print(f"  interval median : {statistics.median(intervals_ms):.2f} ms")
    print(f"  interval max    : {max(intervals_ms):.2f} ms   <-- the stall to worry about")
    if len(intervals_ms) > 1:
        print(f"  interval stdev  : {statistics.stdev(intervals_ms):.2f} ms")

    # A frame interval over ~3x the median means a stall, not jitter.
    med = statistics.median(intervals_ms)
    stalls = [x for x in intervals_ms if x > 3 * med]
    if stalls:
        print(f"  STALLS          : {len(stalls)} interval(s) over 3x median "
              f"(worst {max(stalls):.0f} ms)")
        print("                    SG-4's windows are time-based, so stalls distort PERCLOS.")

    if len(sizes) > 1:
        print("  WARNING: resolution changed mid-capture -- the camera is renegotiating.")

    ok = fps >= 25.0 and not stalls
    print(f"\n  verdict: {'OK' if ok else 'NEEDS ATTENTION'}")
    if not ok:
        print("  If FPS is low: check the format the camera actually supports with")
        print("    v4l2-ctl --list-formats-ext -d /dev/video0")
        print("  and consider the R2 mitigation: drop to 480p.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
