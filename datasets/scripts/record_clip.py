"""Record a clip from the webcam, for real evaluation data.

    python datasets/scripts/record_clip.py --name s01_awake_day_01 --seconds 30
    python datasets/scripts/record_clip.py --name s01_drowsy_dusk_01 --seconds 45 --device 0
    python datasets/scripts/record_clip.py --list-devices

WHY THIS EXISTS
---------------
Every accuracy number in this project is blocked on one thing: there are no real
clips. ``interfaces/mock`` is synthetic and geometrically perfect, and
``datasets/README.md`` forbids any graded figure coming from it. This script is the
shortest path from "we have no data" to "we have a clip the whole pipeline can run
on", which is risk R1's mitigation and issue #7.

The clip lands in ``datasets/clips/``, which is **gitignored** -- recordings of
people must not go into the repository. What gets committed is the manifest
(``datasets/scripts/make_manifest.py``), not the video.

RECORD THE GROUND TRUTH AS YOU GO
---------------------------------
Labelling from memory a week later does not work. Keep a note open and write down
the start and end second of every eye closure and yawn **while you still remember
the take** -- the script prints elapsed seconds on the preview to make that easy.

CONSENT
-------
Get consent from everyone recorded, every time. These clips show identifiable
faces, so they stay off the repo, off shared drives, and off chat.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLIP_DIR = ROOT / "datasets" / "clips"

# Match the capture format agreed with SG-6 (interfaces/contracts.py).
TARGET_FPS = 30
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720


def list_devices(max_index: int = 5) -> int:
    """Probe camera indices so you can find the right --device without guessing.

    This opens each camera briefly, so the capture light will blink.
    """
    import cv2

    found = 0
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                h, w = frame.shape[:2]
                print(f"  device {idx}: opened, delivers {w}x{h}")
                found += 1
            else:
                print(f"  device {idx}: opened but delivered no frame")
        cap.release()
    if not found:
        print("  no usable camera found")
    return 0 if found else 2


def record(name: str, seconds: float, device: int, width: int, height: int,
           fps: float, preview: bool) -> int:
    import cv2

    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLIP_DIR / f"{name}.mp4"
    if out_path.exists():
        print(f"error: {out_path} already exists -- pick another --name", file=sys.stderr)
        return 2

    # CAP_DSHOW: on Windows the default backend can take seconds to open and
    # sometimes ignores the requested resolution.
    cap = cv2.VideoCapture(device, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"error: could not open camera {device}. Try --list-devices, and check no "
              "other app (Teams, Zoom, Camera) is holding it.", file=sys.stderr)
        return 2

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or width
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or height
    print(f"camera {device} open at {actual_w}x{actual_h}")
    if (actual_w, actual_h) != (width, height):
        print(f"  note: asked for {width}x{height}, got {actual_w}x{actual_h}. Record the "
              "demo with the SAME settings you evaluate with.")

    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (actual_w, actual_h))
    if not writer.isOpened():
        cap.release()
        print("error: could not open the video writer (mp4v codec unavailable)",
              file=sys.stderr)
        return 2

    print(f"recording {seconds:.0f} s to {out_path}")
    print("  write down the start/end second of every eye closure and yawn AS YOU GO")
    print("  press q in the preview window to stop early\n")

    frames = 0
    started = time.perf_counter()
    try:
        while True:
            elapsed = time.perf_counter() - started
            if elapsed >= seconds:
                break
            ok, frame = cap.read()
            if not ok or frame is None:
                print("warning: dropped frame from the camera", file=sys.stderr)
                continue
            writer.write(frame)
            frames += 1
            if preview:
                shown = frame.copy()
                cv2.putText(shown, f"{elapsed:5.1f}s / {seconds:.0f}s  q=stop",
                            (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                cv2.imshow("recording -- note your closures and yawns", shown)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    print("stopped early")
                    break
            print(f"\r  {elapsed:5.1f}s  {frames} frames", end="", flush=True)
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        duration = time.perf_counter() - started
        cap.release()
        writer.release()
        if preview:
            cv2.destroyAllWindows()

    effective_fps = frames / duration if duration > 0 else 0.0
    print(f"\n\nwrote {out_path}")
    print(f"  {frames} frames, {duration:.2f} s, {effective_fps:.1f} fps effective")
    if effective_fps < fps * 0.8:
        print(f"  WARNING: effective fps is well under the requested {fps:.0f}. The clip is "
              "written\n  at the requested rate, so playback timing will be wrong. Close other "
              "apps and\n  re-record, or pass --fps close to the effective rate above.")

    print("\nNext:")
    print("  1. Label it (the seconds you noted while recording):")
    print(f"     python datasets/scripts/make_manifest.py --clip datasets/clips/{name}.mp4 \\")
    print(f"            --name {name} --split train --subject s01 \\")
    print('            --closed "12.4-14.1,28.0-28.3" --yawn "19.2-21.0" --drowsy "12.4-14.1"')
    print("  2. Run the REAL pipeline on it:")
    print(f"     python integration/run_pipeline.py --source datasets/clips/{name}.mp4")
    print("  3. Score it:")
    print(f"     python evaluation/run_eval.py --manifest datasets/manifests/{name}.json \\")
    print(f"            --out module_sg5/results/{name}_eval.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record a webcam clip for evaluation data.")
    ap.add_argument("--name", help="clip name, e.g. s01_awake_day_01 (no extension)")
    ap.add_argument("--seconds", type=float, default=30.0, help="how long to record")
    ap.add_argument("--device", type=int, default=0, help="camera index")
    ap.add_argument("--width", type=int, default=TARGET_WIDTH)
    ap.add_argument("--height", type=int, default=TARGET_HEIGHT)
    ap.add_argument("--fps", type=float, default=TARGET_FPS)
    ap.add_argument("--no-preview", action="store_true", help="do not open a preview window")
    ap.add_argument("--list-devices", action="store_true", help="probe camera indices and exit")
    args = ap.parse_args(argv)

    try:
        import cv2  # noqa: F401
    except ImportError:
        print("error: OpenCV is missing. pip install -r requirements.txt", file=sys.stderr)
        return 2

    if args.list_devices:
        return list_devices()
    if not args.name:
        ap.error("--name is required (or pass --list-devices)")

    print("Consent: everyone recorded must have agreed. Clips stay in datasets/clips/, "
          "which is gitignored.\n")
    return record(args.name, args.seconds, args.device, args.width, args.height,
                  args.fps, not args.no_preview)


if __name__ == "__main__":
    raise SystemExit(main())
