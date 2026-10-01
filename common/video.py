"""Frame sources. One place that knows how pixels enter the system.

Three sources, all yielding ``interfaces.contracts.Frame``:

    WebcamSource("0")           live USB-UVC camera (the demo path)
    VideoFileSource("clip.mp4") a recorded clip (the evaluation path)
    MockFaceSource(...)         no pixels at all -- replays mock_face.json so a
                                downstream pair can run before SG-1 exists

SG-6 owns the Jetson capture path. On Jetson, prefer the GStreamer pipeline in
``embedded_sg6/src/capture_jetson.py`` over cv2.VideoCapture(0).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

from interfaces.contracts import TARGET_FPS, TARGET_HEIGHT, TARGET_WIDTH, Frame


class WebcamSource:
    """Live camera. ``device`` is an OpenCV index ("0") or a device path."""

    def __init__(self, device: str = "0", width: int = TARGET_WIDTH,
                 height: int = TARGET_HEIGHT, fps: int = TARGET_FPS) -> None:
        self.device, self.width, self.height, self.fps = device, width, height, fps

    def __iter__(self) -> Iterator[Frame]:
        import cv2

        dev: int | str = int(self.device) if str(self.device).isdigit() else self.device
        cap = cv2.VideoCapture(dev)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        if not cap.isOpened():
            raise RuntimeError(f"cannot open camera {self.device!r}")
        try:
            i = 0
            while True:
                ok, img = cap.read()
                if not ok:
                    break
                yield Frame(i, time.monotonic(), img, img.shape[1], img.shape[0])
                i += 1
        finally:
            cap.release()


class VideoFileSource:
    """A recorded clip. Timestamps come from the file, not the wall clock, so
    evaluation runs are reproducible regardless of how fast the machine is."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def __iter__(self) -> Iterator[Frame]:
        import cv2

        if not self.path.exists():
            raise FileNotFoundError(self.path)
        cap = cv2.VideoCapture(str(self.path))
        fps = cap.get(cv2.CAP_PROP_FPS) or TARGET_FPS
        try:
            i = 0
            while True:
                ok, img = cap.read()
                if not ok:
                    break
                yield Frame(i, i / fps, img, img.shape[1], img.shape[0])
                i += 1
        finally:
            cap.release()


class MockFaceSource:
    """Replay ``interfaces/mock/mock_face.json`` as SG-1 output.

    There are no pixels, so ``Frame.image`` is None. Modules that only consume
    landmarks (SG-2, SG-3) work fine against this; anything that needs pixels
    must handle ``image is None`` rather than crash.
    """

    DEFAULT = Path(__file__).resolve().parents[1] / "interfaces" / "mock" / "mock_face.json"

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else self.DEFAULT

    def load(self) -> list:
        from interfaces.contracts import from_dict

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [from_dict(x) for x in raw]

    def __iter__(self) -> Iterator[Frame]:
        for f in self.load():
            yield Frame(f.frame_id, f.timestamp, None, TARGET_WIDTH, TARGET_HEIGHT)


def make_source(spec: str):
    """Build a source from a CLI string: "mock", "0" (webcam index), or a file path."""
    if spec == "mock":
        return MockFaceSource()
    if spec.isdigit():
        return WebcamSource(spec)
    return VideoFileSource(spec)
