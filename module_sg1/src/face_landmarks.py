"""SG-1 Driver Face & Landmark Detection -- baseline: MediaPipe FaceMesh.

Contract
--------
    IN   interfaces.contracts.Frame        (uint8 BGR image)
    OUT  interfaces.contracts.FaceResult   (face_box + 68 landmarks + ROIs)

Decision matrix (Figma section 3)
---------------------------------
    MediaPipe FaceMesh   weighted 55   BASELINE          <- implemented here
    RetinaFace + PFLD    weighted 50   carry as comparison
    YOLOv8-face          weighted 48   rejected, memory cost

Your job this semester (Labs 4-7) is NOT to accept this file as finished. It is a
working baseline so SG-2/SG-3 stop waiting. You still owe:
  * the RetinaFace+PFLD comparison on the same clips, same metrics;
  * a measured accuracy/FPS/memory table in results/;
  * failure analysis on glasses, night lighting and large head yaw (risk R1).

IMPORTANT -- the 468 -> 68 mapping below is the standard community mapping and
has NOT been verified on this project's data. Verify it before Lab 4:
    python module_sg1/run.py --source 0 --verify-landmarks
and fix any index that lands in the wrong place. SG-2 and SG-3 trust these
indices completely, so an error here is silently wrong EAR/MAR everywhere.
"""

from __future__ import annotations

from typing import Any

from interfaces.contracts import (
    LANDMARK_COUNT,
    BBox,
    FaceResult,
    Frame,
)

# MediaPipe FaceMesh (468 pts) -> iBUG 68 ordering. 17 jaw, 5+5 brows, 4+5 nose,
# 6+6 eyes, 12 outer lip, 8 inner lip = 68.
FACEMESH_TO_IBUG68: tuple[int, ...] = (
    # 0-16  jaw line, left to right across the image
    162, 234, 93, 58, 172, 136, 149, 148, 152, 377, 378, 365, 397, 288, 323, 454, 389,
    # 17-21 driver's right eyebrow          22-26 driver's left eyebrow
    71, 63, 105, 66, 107,
    336, 296, 334, 293, 301,
    # 27-30 nose bridge                      31-35 nose base
    168, 197, 5, 4,
    75, 97, 2, 326, 305,
    # 36-41 driver's RIGHT eye               42-47 driver's LEFT eye
    33, 160, 158, 133, 153, 144,
    362, 385, 387, 263, 373, 380,
    # 48-59 outer lip
    61, 39, 37, 0, 267, 269, 291, 405, 314, 17, 84, 181,
    # 60-67 inner lip
    78, 82, 13, 312, 308, 317, 14, 87,
)
assert len(FACEMESH_TO_IBUG68) == LANDMARK_COUNT


class FaceLandmarkDetector:
    """Stateful detector. One instance per pipeline; call ``process`` per frame.

    Kept stateful (not a bare function) because MediaPipe holds a graph and a
    tracking state across frames -- re-creating it per frame costs ~10x.
    """

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self.min_detection_confidence = float(cfg.get("min_detection_confidence", 0.5))
        self.min_tracking_confidence = float(cfg.get("min_tracking_confidence", 0.5))
        self.roi_padding = float(cfg.get("roi_padding", 0.15))   # fraction of ROI size
        self.refine_landmarks = bool(cfg.get("refine_landmarks", True))
        self._mesh: Any = None

    # -- lifecycle ---------------------------------------------------------- #
    def _lazy_init(self) -> Any:
        if self._mesh is None:
            import mediapipe as mp

            self._mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,                       # driver only, per contract
                refine_landmarks=self.refine_landmarks,
                min_detection_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence,
            )
        return self._mesh

    def reset(self) -> None:
        """Drop tracking state. Call between clips so one clip cannot leak into the next."""
        if self._mesh is not None:
            self._mesh.close()
            self._mesh = None

    def close(self) -> None:
        self.reset()

    # -- the contract ------------------------------------------------------- #
    def process(self, frame: Frame) -> FaceResult:
        """Frame -> FaceResult. Never raises on a missing face; returns valid=False."""
        if frame.image is None:
            return FaceResult.empty(frame.frame_id, frame.timestamp, reason="no_image")

        import cv2

        h, w = frame.image.shape[:2]
        try:
            mesh = self._lazy_init()
            res = mesh.process(cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB))
        except Exception as exc:                       # noqa: BLE001 -- must not kill the pipeline
            return FaceResult.empty(frame.frame_id, frame.timestamp,
                                    reason=f"detector_error:{type(exc).__name__}")

        if not res.multi_face_landmarks:
            return FaceResult.empty(frame.frame_id, frame.timestamp, reason="no_face")

        mesh_pts = res.multi_face_landmarks[0].landmark
        lm: list[tuple[float, float]] = [
            (mesh_pts[i].x * w, mesh_pts[i].y * h) for i in FACEMESH_TO_IBUG68
        ]

        face_box = self._box_from(lm, pad_frac=0.08, w=w, h=h)
        if not face_box.is_valid():
            return FaceResult.empty(frame.frame_id, frame.timestamp, reason="degenerate_face_box")

        return FaceResult(
            frame_id=frame.frame_id,
            timestamp=frame.timestamp,
            valid=True,
            reason="",
            face_box=face_box,
            landmarks=lm,
            right_eye_roi=self._box_from(lm[36:42], self.roi_padding, w, h),
            left_eye_roi=self._box_from(lm[42:48], self.roi_padding, w, h),
            mouth_roi=self._box_from(lm[48:60], self.roi_padding, w, h),
            # FaceMesh gives no detection score when tracking; a landmark set that
            # survived min_tracking_confidence is reported at that floor rather
            # than a made-up 1.0, so downstream confidence gating stays honest.
            confidence=self.min_tracking_confidence,
            # TODO(SG-1, Lab 7): solvePnP head pose. None means "unknown" and
            # SG-4/SG-5 already handle it -- do not emit 0.0 as a placeholder.
            yaw_deg=None, pitch_deg=None, roll_deg=None,
        )

    # -- helpers ------------------------------------------------------------ #
    @staticmethod
    def _box_from(points: list[tuple[float, float]], pad_frac: float,
                  w: int, h: int) -> BBox:
        """Tight bounding box over ``points``, grown by ``pad_frac`` of its size."""
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        px, py = (x1 - x0) * pad_frac, (y1 - y0) * pad_frac
        # Eye ROIs are very wide and flat; a purely proportional pad leaves them
        # 2-3 px tall, which breaks any CNN fallback. Enforce a floor.
        py = max(py, 4.0)
        return BBox(int(x0 - px), int(y0 - py),
                    int((x1 - x0) + 2 * px), int((y1 - y0) + 2 * py)).clip(w, h)
