"""Contract tests -- the Lab 3 Interface Gate, automated.

These guard the agreement between sub-groups. If one of these fails, somebody has
changed a contract without telling the team, and integration will break later in
a much more expensive way.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interfaces.contracts import (
    LANDMARK_COUNT,
    SCHEMA_VERSION,
    BBox,
    DecisionResult,
    DrowsinessState,
    EyeResult,
    EyeState,
    FaceResult,
    TemporalResult,
    YawnResult,
    from_dict,
    to_dict,
    validate,
)

MOCK = Path(__file__).resolve().parents[1] / "mock"


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
def test_bbox_clips_to_frame():
    assert BBox(-5, -5, 50, 50).clip(1280, 720).to_list() == [0, 0, 45, 45]
    assert BBox(1270, 710, 100, 100).clip(1280, 720).to_list() == [1270, 710, 10, 10]


def test_bbox_fully_outside_frame_is_invalid():
    assert not BBox(2000, 2000, 10, 10).clip(1280, 720).is_valid()


# --------------------------------------------------------------------------- #
# The empty-behaviour rule: never None, never an exception, always a reason.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cls", [FaceResult, EyeResult, YawnResult, TemporalResult,
                                DecisionResult])
def test_empty_payload_is_contract_compliant(cls):
    p = cls.empty(7, 0.233)
    assert p.frame_id == 7
    assert p.valid is False
    assert p.reason, "valid=False must carry a non-empty reason"
    assert validate(p) == []


@pytest.mark.parametrize("cls", [FaceResult, EyeResult, YawnResult, TemporalResult])
def test_valid_false_without_reason_is_rejected(cls):
    p = cls(frame_id=0, timestamp=0.0, valid=False, reason="")
    assert any("reason" in e for e in validate(p))


# --------------------------------------------------------------------------- #
# Round-trip: anything written to disk must come back identical.
# --------------------------------------------------------------------------- #
def test_face_result_roundtrip_preserves_geometry():
    f = FaceResult(
        frame_id=3, timestamp=0.1, valid=True, reason="",
        face_box=BBox(100, 50, 220, 300),
        landmarks=[(float(i), float(i * 2)) for i in range(LANDMARK_COUNT)],
        right_eye_roi=BBox(120, 90, 60, 24), left_eye_roi=BBox(240, 90, 60, 24),
        mouth_roi=BBox(170, 230, 90, 50), confidence=0.91,
    )
    back = from_dict(to_dict(f))
    assert back.face_box.to_list() == [100, 50, 220, 300]
    assert back.landmarks == f.landmarks
    assert back.right_eye_roi.to_list() == [120, 90, 60, 24]
    assert validate(back) == []


def test_enums_roundtrip_as_strings():
    d = to_dict(DecisionResult(1, 0.0, state=DrowsinessState.ALERT, alert=True))
    assert d["state"] == "ALERT", "enums must serialise as their string value"
    assert from_dict(d).state is DrowsinessState.ALERT

    e = to_dict(EyeResult(1, 0.0, valid=True, reason="", ear=0.3,
                          eye_state=EyeState.CLOSED))
    assert e["eye_state"] == "CLOSED"
    assert from_dict(e).eye_state is EyeState.CLOSED


def test_schema_version_mismatch_is_loud():
    d = to_dict(EyeResult.empty(0, 0.0))
    d["_schema_version"] = "0.0.1-ancient"
    with pytest.raises(ValueError, match="schema version"):
        from_dict(d)


def test_unknown_payload_type_is_rejected():
    with pytest.raises(ValueError, match="unknown payload"):
        from_dict({"_type": "NotAThing", "_schema_version": SCHEMA_VERSION})


# --------------------------------------------------------------------------- #
# Validation must actually reject bad values -- a checker that passes everything
# is worse than no checker, because it manufactures false confidence.
# --------------------------------------------------------------------------- #
def test_alert_flag_must_agree_with_state():
    assert validate(DecisionResult(0, 0.0, state=DrowsinessState.ALERT, alert=False))
    assert validate(DecisionResult(0, 0.0, state=DrowsinessState.OK, alert=True))
    assert validate(DecisionResult(0, 0.0, state=DrowsinessState.ALERT, alert=True)) == []


def test_out_of_range_scores_are_rejected():
    assert validate(TemporalResult(0, 0.0, valid=True, reason="", perclos=1.4))
    assert validate(TemporalResult(0, 0.0, valid=True, reason="", drowsy_score=-0.1))
    assert validate(EyeResult(0, 0.0, valid=True, reason="", ear=0.3,
                              eye_state=EyeState.OPEN, confidence=1.5))


def test_valid_face_needs_the_full_landmark_set():
    f = FaceResult(0, 0.0, valid=True, reason="", face_box=BBox(0, 0, 10, 10),
                   landmarks=[(1.0, 1.0)] * 12)
    assert any("landmarks" in e for e in validate(f))


def test_valid_eye_result_may_not_report_unknown():
    e = EyeResult(0, 0.0, valid=True, reason="", ear=0.3, eye_state=EyeState.UNKNOWN)
    assert any("UNKNOWN" in err for err in validate(e))


# --------------------------------------------------------------------------- #
# Every mock file on disk must satisfy the contract it claims to implement.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["mock_face.json", "mock_eye.json",
                                  "mock_yawn.json", "mock_temporal.json"])
def test_mock_files_are_contract_compliant(name):
    path = MOCK / name
    if not path.exists():
        pytest.skip(f"{name} not generated; run interfaces/mock/generate_mocks.py")
    payloads = [from_dict(x) for x in json.loads(path.read_text(encoding="utf-8"))]
    assert payloads, f"{name} is empty"
    for p in payloads:
        errs = validate(p)
        assert errs == [], f"{name} frame {p.frame_id}: {errs}"


def test_mock_frame_ids_are_contiguous_and_aligned():
    """SG-4 pairs eye and yawn by frame_id, so the sequences must line up exactly."""
    files = {n: MOCK / n for n in ("mock_face.json", "mock_eye.json", "mock_yawn.json")}
    if not all(p.exists() for p in files.values()):
        pytest.skip("mock data not generated")
    seqs = {n: [from_dict(x) for x in json.loads(p.read_text(encoding="utf-8"))]
            for n, p in files.items()}
    lengths = {n: len(s) for n, s in seqs.items()}
    assert len(set(lengths.values())) == 1, f"mock sequences differ in length: {lengths}"
    for n, s in seqs.items():
        assert [p.frame_id for p in s] == list(range(len(s))), f"{n} frame_ids not contiguous"
