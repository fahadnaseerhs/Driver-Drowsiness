"""SG-6: Jetson capture path.

cv2.VideoCapture(0) works on the Jetson but goes through a slow path and often will
not hold 30 FPS at 720p. Use a GStreamer pipeline instead, which keeps buffers on
the hardware path.

Two camera families, two pipelines -- know which one you have:
  * USB-UVC webcam    -> v4l2src            (what the Figma plan specifies)
  * CSI / IMX219 etc.  -> nvarguscamerasrc

STATUS: scaffolding. Nothing here has run on real hardware, so treat every
pipeline string as a hypothesis to test, not a working configuration. Risk R7
(unstable capture on Jetson) is owned by SG-6 and its mitigation is to smoke-test
capture on its own, before anything is wired to it.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from interfaces.contracts import TARGET_FPS, TARGET_HEIGHT, TARGET_WIDTH, Frame


def usb_pipeline(device: str = "/dev/video0", width: int = TARGET_WIDTH,
                 height: int = TARGET_HEIGHT, fps: int = TARGET_FPS) -> str:
    """GStreamer pipeline for a USB-UVC camera, MJPEG decoded off the CPU.

    If the camera cannot do MJPEG at this size, check what it actually supports:
        v4l2-ctl --list-formats-ext -d /dev/video0
    and fall back to a smaller size. Risk R2's mitigation is exactly this:
    "Reduce to 480p, TensorRT FP16, ROI-only crops".
    """
    return (
        f"v4l2src device={device} ! "
        f"image/jpeg, width={width}, height={height}, framerate={fps}/1 ! "
        "jpegdec ! videoconvert ! video/x-raw, format=BGR ! "
        "appsink drop=true max-buffers=1"
    )


def csi_pipeline(sensor_id: int = 0, width: int = TARGET_WIDTH,
                 height: int = TARGET_HEIGHT, fps: int = TARGET_FPS) -> str:
    """GStreamer pipeline for a CSI camera via the Argus daemon."""
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"framerate={fps}/1, format=NV12 ! "
        "nvvidconv ! video/x-raw, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! "
        "appsink drop=true max-buffers=1"
    )


class JetsonCameraSource:
    """Frame source backed by a GStreamer pipeline.

    ``drop=true max-buffers=1`` on the appsink is deliberate: if the pipeline cannot
    keep up we want the NEWEST frame, not a growing backlog of stale ones. A
    drowsiness alert computed from a two-second-old frame is worse than useless --
    it is an alarm about a hazard that has already happened.
    """

    def __init__(self, pipeline: str | None = None, camera: str = "usb") -> None:
        self.pipeline = pipeline or (usb_pipeline() if camera == "usb" else csi_pipeline())

    def __iter__(self) -> Iterator[Frame]:
        import cv2

        cap = cv2.VideoCapture(self.pipeline, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            debug = self.pipeline.replace("appsink drop=true max-buffers=1", "fakesink")
            raise RuntimeError(
                "GStreamer pipeline failed to open. Test it on the command line first:\n"
                f"  gst-launch-1.0 {debug}"
            )
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
