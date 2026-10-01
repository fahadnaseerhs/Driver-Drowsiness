"""Debug overlay for the live demo (--display).

Shows what the system is thinking, which is what the Face-Off audience and the
examiner actually see. The ``evidence`` string from SG-5 is drawn verbatim -- if
it reads badly on screen, fix the string in SG-5, not here.
"""

from __future__ import annotations

from interfaces.contracts import DrowsinessState

STATE_COLOUR = {
    DrowsinessState.OK: (0, 200, 0),
    DrowsinessState.WARN: (0, 200, 255),
    DrowsinessState.ALERT: (0, 0, 255),
}


class OverlayRenderer:
    """Draws the pipeline output onto the frame and shows it in a window."""

    def __init__(self, window: str = "Driver Drowsiness Monitor (q to quit)") -> None:
        import cv2  # fail fast if OpenCV is absent

        self._cv2 = cv2
        self.window = window
        self.stop = False

    def show(self, fo) -> None:
        cv2 = self._cv2
        if self.stop or fo.frame.image is None:
            return
        img = fo.frame.image.copy()
        colour = STATE_COLOUR[fo.decision.state]

        if fo.face.valid and fo.face.face_box is not None:
            b = fo.face.face_box
            cv2.rectangle(img, (b.x, b.y), (b.x + b.w, b.y + b.h), colour, 2)
            for x, y in fo.face.landmarks:
                cv2.circle(img, (int(x), int(y)), 1, (200, 200, 200), -1)
        else:
            cv2.putText(img, f"NO FACE: {fo.face.reason}", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.putText(img, fo.decision.state.value, (20, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, colour, 3)

        lines = [
            f"score {fo.temporal.drowsy_score:.2f}   PERCLOS {fo.temporal.perclos:.2f}",
            f"EAR {fo.eye.ear if fo.eye.ear is not None else float('nan'):.3f}"
            f"   MAR {fo.yawn.mar if fo.yawn.mar is not None else float('nan'):.3f}",
            f"closure {fo.eye.closure_duration_s:.2f}s"
            f"   blinks {fo.temporal.blink_rate_per_min:.0f}/min",
            f"latency {fo.decision.latency_ms or 0:.1f} ms",
            fo.decision.evidence,
        ]
        for i, line in enumerate(lines):
            cv2.putText(img, line, (20, 110 + i * 24), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (255, 255, 255), 1)

        cv2.imshow(self.window, img)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            self.stop = True

    def close(self) -> None:
        try:
            self._cv2.destroyAllWindows()
        except Exception:  # noqa: BLE001
            pass
