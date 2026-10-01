"""SG-1 tests. Most require MediaPipe, so they skip cleanly on a bare machine --
CI still checks the parts that do not need a model."""

from __future__ import annotations

import pytest

from interfaces.contracts import LANDMARK_COUNT, Frame
from module_sg1.src.face_landmarks import FACEMESH_TO_IBUG68, FaceLandmarkDetector


def test_mapping_has_exactly_68_entries():
    assert len(FACEMESH_TO_IBUG68) == LANDMARK_COUNT


def test_mapping_has_no_duplicate_indices():
    """A duplicate means two iBUG points read the same FaceMesh vertex, which
    silently collapses an eye or lip and produces a constant EAR/MAR."""
    dupes = {i for i in FACEMESH_TO_IBUG68 if list(FACEMESH_TO_IBUG68).count(i) > 1}
    assert not dupes, f"duplicated FaceMesh indices: {sorted(dupes)}"


def test_mapping_indices_are_within_facemesh_range():
    # FaceMesh emits 468 landmarks (478 with iris refinement).
    assert all(0 <= i < 468 for i in FACEMESH_TO_IBUG68)


def test_no_image_returns_invalid_not_an_exception():
    det = FaceLandmarkDetector()
    r = det.process(Frame(frame_id=0, timestamp=0.0, image=None))
    assert r.valid is False
    assert r.reason == "no_image"


@pytest.mark.needs_model
def test_detects_a_face_in_a_real_frame():
    """Requires MediaPipe and a sample image. This is the test that would actually
    validate the 468->68 mapping -- it is NOT a substitute for looking at the
    overlay with your own eyes (run: python module_sg1/run.py --verify-landmarks)."""
    pytest.importorskip("mediapipe")
    pytest.importorskip("cv2")
    pytest.skip("add datasets/samples/face01.jpg and assert landmark positions here")
