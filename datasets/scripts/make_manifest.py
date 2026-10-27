"""Turn a recorded clip plus the seconds you noted into a committable manifest.

    python datasets/scripts/make_manifest.py --clip datasets/clips/s01_awake_day_01.mp4 \
        --name s01_awake_day_01 --split train --subject s01 \
        --closed "12.4-14.1,28.0-28.3" --yawn "19.2-21.0" --drowsy "12.4-14.1"

    # An awake-driver clip: no episodes at all. This is the most valuable kind.
    python datasets/scripts/make_manifest.py --clip datasets/clips/s01_awake_day_01.mp4 \
        --name s01_awake_day_01 --split train --subject s01 --glasses

WHY A MANIFEST
--------------
The clips are gitignored -- recordings of people stay off the repository. The
manifest is what gets committed: which clip, which split, and the ground truth the
evaluation harness scores against. Someone cloning the repo can see exactly what
was measured even without the video.

``drowsy_episodes_s`` is the field that matters. It is **not** every eye closure: a
normal blink is a closure and must NOT produce an alarm. An episode is a stretch
where a correct system is required to alarm. Getting this distinction wrong is the
quickest way to produce meaningless metrics -- it would score a blink-detector as a
perfect drowsiness detector.

APPENDING
---------
Re-running with an existing --name adds the clip to that manifest (or replaces the
entry for the same file), so you can build a split up one take at a time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = ROOT / "datasets" / "manifests"


def parse_intervals(spec: str | None, label: str, duration_s: float | None) -> list[list[float]]:
    """Parse "12.4-14.1,28.0-28.3" into [[12.4, 14.1], [28.0, 28.3]].

    Validates rather than trusting: a typo in a label silently corrupts every
    metric computed from it, and the error surfaces weeks later as a mysterious
    recall figure.
    """
    if not spec:
        return []
    out: list[list[float]] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" not in chunk:
            raise ValueError(f"{label}: '{chunk}' is not a range; use start-end, e.g. 12.4-14.1")
        a, _, b = chunk.partition("-")
        try:
            start, end = float(a), float(b)
        except ValueError as exc:
            raise ValueError(f"{label}: '{chunk}' is not a pair of numbers") from exc
        if end <= start:
            raise ValueError(f"{label}: '{chunk}' ends at or before it starts")
        if start < 0:
            raise ValueError(f"{label}: '{chunk}' starts before the clip does")
        if duration_s is not None and end > duration_s + 0.5:
            raise ValueError(
                f"{label}: '{chunk}' ends at {end:.2f}s but the clip is only "
                f"{duration_s:.2f}s long")
        out.append([round(start, 3), round(end, 3)])
    out.sort()
    for (a_start, a_end), (b_start, _) in zip(out, out[1:], strict=False):
        if b_start < a_end:
            raise ValueError(f"{label}: intervals overlap ({a_start}-{a_end} and {b_start}-...)")
    return out


def probe_duration(clip: Path) -> float | None:
    """Read the clip's duration with OpenCV. Returns None if it cannot be read,
    in which case --duration must be supplied."""
    try:
        import cv2
    except ImportError:
        return None
    cap = cv2.VideoCapture(str(clip))
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()
    if fps <= 0 or frames <= 0:
        return None
    return round(frames / fps, 3)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write/extend an evaluation manifest for a clip.")
    ap.add_argument("--clip", type=Path, required=True, help="path to the recorded video")
    ap.add_argument("--name", required=True, help="manifest name, e.g. dusk_glasses_v1")
    ap.add_argument("--split", choices=("train", "val", "test", "sample"), required=True,
                    help="test is SEALED until final validation (risk R5)")
    ap.add_argument("--subject", required=True, help="subject id, e.g. s01 -- split by SUBJECT")
    ap.add_argument("--glasses", action="store_true")
    ap.add_argument("--lighting", default="day", help="day / dusk / night / indoor ...")
    ap.add_argument("--camera", default="HP HD Camera, 1280x720 @30, laptop-mounted",
                    help="exact camera and mounting -- it must match the demo rig")
    ap.add_argument("--closed", help='eye closures, "12.4-14.1,28.0-28.3"')
    ap.add_argument("--yawn", help='yawns, "19.2-21.0"')
    ap.add_argument("--drowsy", help='drowsy episodes a correct system MUST alarm on')
    ap.add_argument("--duration", type=float, default=None,
                    help="clip length in seconds (default: read from the file)")
    ap.add_argument("--notes", default="")
    args = ap.parse_args(argv)

    if not args.clip.exists():
        print(f"error: {args.clip} does not exist", file=sys.stderr)
        return 2

    duration = args.duration if args.duration is not None else probe_duration(args.clip)
    if duration is None:
        print("error: could not read the clip duration; pass --duration", file=sys.stderr)
        return 2

    try:
        closed = parse_intervals(args.closed, "--closed", duration)
        yawns = parse_intervals(args.yawn, "--yawn", duration)
        drowsy = parse_intervals(args.drowsy, "--drowsy", duration)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Every drowsy episode should correspond to a closure you also labelled. Warn
    # rather than fail -- a long slow blink sequence is a legitimate episode too.
    for start, end in drowsy:
        if not any(c_start <= end and c_end >= start for c_start, c_end in closed):
            print(f"warning: drowsy episode {start}-{end}s overlaps no labelled eye closure. "
                  "Intended?", file=sys.stderr)
    if drowsy and not closed:
        print("warning: drowsy episodes but no closures labelled at all", file=sys.stderr)

    try:
        rel_clip = args.clip.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        rel_clip = args.clip.as_posix()

    entry = {
        "file": rel_clip,
        "sha256": sha256(args.clip),
        "duration_s": duration,
        "subject": args.subject,
        "glasses": bool(args.glasses),
        "lighting": args.lighting,
        "ground_truth": {
            "eyes_closed_s": closed,
            "yawn_s": yawns,
            "drowsy_episodes_s": drowsy,
        },
    }

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = MANIFEST_DIR / f"{args.name}.json"
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["clips"] = [c for c in manifest.get("clips", []) if c.get("file") != rel_clip]
        manifest["clips"].append(entry)
        action = "updated"
    else:
        manifest = {
            "name": args.name,
            "split": args.split,
            "created": date.today().isoformat(),
            "source": "self-recorded",
            "camera": args.camera,
            "notes": args.notes,
            "clips": [entry],
        }
        action = "wrote"
    manifest["clips"].sort(key=lambda c: c["file"])

    path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")

    n_drowsy = sum(len(c["ground_truth"]["drowsy_episodes_s"]) for c in manifest["clips"])
    total_s = sum(c["duration_s"] for c in manifest["clips"])
    print(f"{action} {path}")
    print(f"  clips: {len(manifest['clips'])}, {total_s:.1f} s total, "
          f"{n_drowsy} drowsy episode(s)")
    if args.split == "test":
        print("  SPLIT=test: this is sealed until final validation. Record the sealing date "
              "in\n  datasets/README.md, and if anyone tunes against it, say so in the report.")
    print("\nNext:")
    print(f"  python evaluation/run_eval.py --manifest {path.relative_to(ROOT).as_posix()} \\")
    print(f"         --out module_sg5/results/{args.name}_eval.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
