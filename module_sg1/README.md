# SG-1 — Driver Face & Landmark Detection

**Owners:** NUST 466391, 464775 — *confirm names, see `documentation/team.md`*
**Status:** 🔴 **RED — never executed.** OpenCV and MediaPipe are not installed, and
the 468→68 landmark mapping is unverified. Everything downstream depends on this.

## 1. Purpose

Find the driver's face in each frame and emit a stable geometric front-end for every
downstream cue: 68 facial landmarks plus eye and mouth regions of interest.

This is the only module that touches pixels. SG-2 and SG-3 never see an image — they
work from the landmarks this module produces, which is what makes them testable
against mock data.

Scope per the guide: *"Reliable face localization and relevant eye/mouth regions
under realistic driver pose and lighting."*

## 2. Dependencies

| Package | Version | Note |
|---|---|---|
| `mediapipe` | 0.10.14 | the baseline model |
| `opencv-python` | 4.10.0.84 | colour conversion, I/O |
| `numpy` | 1.26.4 | pinned `<2.0` — MediaPipe is not numpy-2 safe |

```bash
pip install -r requirements.txt
```

> **aarch64 is the problem.** MediaPipe has no official Jetson wheel. Options are in
> `embedded_sg6/requirements-jetson.txt`. **Resolve this at Lab 9, not Lab 11** — if
> it slips, it becomes the thing that stops Integration Gate 2. If no wheel works,
> the fallback is to deploy the RetinaFace + PFLD comparison path through TensorRT,
> which means that comparison stops being optional.

## 3. Input / output interface

```
Frame  ->  FaceResult
```

**In** — `interfaces.contracts.Frame`: `image` (uint8, H×W×3, **BGR**), `frame_id`,
`timestamp` (seconds, monotonic).

**Out** — `interfaces.contracts.FaceResult`:

| Field | Units | Meaning |
|---|---|---|
| `face_box` | px, `BBox` | driver's face. If several faces, **the largest** |
| `landmarks` | px, 68 × (x, y) float | iBUG/300-W ordering, full-frame coords |
| `right_eye_roi` | px | from landmarks 36:42 — the driver's **right** eye |
| `left_eye_roi` | px | from landmarks 42:48 — the driver's **left** eye |
| `mouth_roi` | px | from landmarks 48:60 |
| `confidence` | [0, 1] | detector confidence |
| `yaw/pitch/roll_deg` | degrees or `None` | head pose; `None` = unknown, **not** 0 |

Coordinates are pixels, origin **top-left of the full frame**, x right, y down.

> **Eye sides are subject-relative.** iBUG 36–41 is the driver's *right* eye, which
> appears on the *left* of a non-mirrored image. Getting this backwards is the classic
> silent bug here — it never crashes, it just mislabels every ROI. If SG-6 mirrors the
> preview for the driver, it must mirror **only the display**, never the frame handed
> to this module.

**Empty behaviour:** no face returns `FaceResult.empty(...)` with `valid=False` and a
reason (`no_face`, `no_image`, `detector_error:*`, `degenerate_face_box`). Never
`None`, never an exception.

## 4. How to run

```bash
# Verify the landmark mapping on your own face — DO THIS BEFORE LAB 4
python module_sg1/run.py --source 0 --verify-landmarks

# A recorded clip; saves the FaceResult sequence for downstream groups
python module_sg1/run.py --source clip.mp4 --dump module_sg1/results/clip01.json

# The full pipeline with the real detector
python integration/run_pipeline.py --source 0 --display
```

Config: `configs/default.yaml`.

### ⚠ The one thing to do first

`FACEMESH_TO_IBUG68` in `src/face_landmarks.py` maps MediaPipe's 468 mesh vertices
onto the 68-point layout. It is the widely used community mapping, written from
memory, **verified by nobody**.

If one index is wrong, SG-2's EAR and SG-3's MAR are quietly wrong on every frame and
nothing crashes to tell you. The unit tests check the table has 68 unique in-range
entries — that catches a typo, not a misplacement.

Run `--verify-landmarks` and check with your own eyes that **36** and **39** sit on
the corners of your right eye, **42**/**45** on your left, **48**/**54** on your mouth
corners, and **51**/**57** on the top and bottom of your lips. Then record below that
you did it, and who.

| Verified by | Date | Result |
|---|---|---|
| *nobody yet* | — | — |

## 5. Test data

- `interfaces/mock/mock_face.json` — this module's **reference output**, not its
  input. Generated synthetically so downstream groups can work before this module
  exists.
- Real clips: none yet. See `datasets/README.md`.
- `tests/test_face_landmarks.py` — mapping sanity plus the no-image path. The
  meaningful test is marked `needs_model` and is still a placeholder.

## 6. Current performance

**None measured.** This module has not run.

| Metric | Target | Measured | Hardware |
|---|---|---|---|
| Detection rate | > 95% frontal | — | — |
| Detection rate, glasses | > 90% | — | — |
| Detection rate, night | > 85% | — | — |
| FPS | ≥ 30 | — | — |
| Memory | — | — | — |

Fill this in at Lab 4 and keep the hardware column honest — a number without the
device it came from is not a result.

## Still owed

- [ ] **Verify the 468→68 mapping** (before Lab 4)
- [ ] Baseline measured on real clips (Lab 4)
- [ ] RetinaFace + PFLD comparison, same clips, same metrics (Labs 5–6)
- [ ] Failure analysis: glasses, night, large yaw, partial occlusion (Lab 7)
- [ ] Head pose via `solvePnP` — currently `None` (Lab 7)
- [ ] aarch64 deployment decision (Lab 9)
