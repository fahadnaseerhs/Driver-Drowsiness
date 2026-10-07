---
tags: [driver-drowsiness, pipeline, implementation]
---
# 1 - Pipeline SG-1 → SG-5 (Detection → Alert)

Part of [[Driver Drowsiness Index]]. Deployment: [[2 - Jetson SG-6 Deploy]]. Diagram: [[3 - Process Flow Map]].

Source of truth: `interfaces/contracts.py` (frozen V1 schema `1.0.0`). Home: [[Welcome]].

## Module responsibilities

| Module | Input | Output (contract) | Job |
|---|---|---|---|
| Camera | USB-UVC 30 FPS 1280x720 | `Frame` (BGR, by reference) | Capture, `frame_id`, monotonic timestamp |
| SG-1 | `Frame` | `FaceResult` | Largest face = driver, 68 landmarks, face/eye/mouth ROIs, optional head pose |
| SG-2 | `FaceResult` | `EyeResult` | EAR per eye + fused, `eye_state`, `blink_event`, `closure_duration_s` |
| SG-3 | `FaceResult` | `YawnResult` | MAR, `yawn_flag`, `yawn_event`, `yawn_duration_s` |
| SG-4 | `EyeResult` + `YawnResult` | `TemporalResult` | Sliding window: PERCLOS, blink/yawn rate, longest closure, `drowsy_score` 0-1 |
| SG-5 | `TemporalResult` | `DecisionResult` | State `OK / WARN / ALERT`, `alert` flag, `evidence` text, `latency_ms` |

## Contract rules (every module must obey)
1. Always return the payload; never `None`, never raise on "no face".
2. Failure = `valid=False` + non-empty `reason` (use `X.empty(frame_id, ts, reason)`).
3. Coordinates: pixels, origin top-left of the FULL frame.
4. `confidence` in [0, 1].
5. Contracts import no numpy/OpenCV/MediaPipe.
6. Any field change needs team agreement and a `SCHEMA_VERSION` bump.
7. `alert == True` if and only if `state == ALERT`.

## How to implement

### Step 0 - Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
pytest   # contract tests must pass before you start
```

### Step 1 - Code against mocks first
Use `interfaces/mock/*.json` (`mock_face`, `mock_eye`, `mock_yawn`, `mock_temporal`, `scenario.json`). Load with `from_dict()`. Regenerate with `python interfaces/mock/generate_mocks.py`. Each team can then work without waiting for upstream modules.

### Step 2 - Implement each module in `module_sgN/src/`
Expose one function/class with a per-frame method, e.g. `process(upstream) -> Result`.

- **SG-1:** MediaPipe FaceMesh (468 pts) mapped to the 68-pt layout; pick the largest face; clip ROIs to the frame; otherwise `FaceResult.empty(..., "no_face")`.
- **SG-2:** `EAR = (|p2-p6| + |p3-p5|) / (2·|p1-p4|)` using `LEFT_EYE_IDX` / `RIGHT_EYE_IDX`; threshold gives `OPEN/CLOSED`; track consecutive closed time for `closure_duration_s`; fire `blink_event` when a short closure ends.
- **SG-3:** `MAR` from `MOUTH_INNER_IDX` (60-67); `yawn_flag` while MAR is above threshold; `yawn_event` when a long-enough opening completes.
- **SG-4:** Ring buffer (e.g. 30-60 s). PERCLOS = closed-time / window. Report `window_filled=False` while warming up. Fuse PERCLOS, longest closure, yawn rate and blink rate into `drowsy_score` (scipy for smoothing/peaks).
- **SG-5:** Threshold the score with hysteresis and a minimum duration (OK → WARN → ALERT, drop back only after a cool-down). Fill `evidence`, e.g. `"PERCLOS 0.42 > 0.30 for 3.1 s"`, and `latency_ms = now - frame.timestamp`.

### Step 3 - Validate every output
Call `validate(result)` in debug mode and in tests; the returned list must be empty. Tolerate `valid=False` from upstream on every frame.

### Step 4 - Integrate (`integration/src/`)
Main loop: `Frame → SG-1 → (SG-2 ∥ SG-3) → SG-4 → SG-5 → alert output`. Config via YAML (thresholds, window length). Log each `DecisionResult` via `to_dict()` for `evaluation/`.

### Step 5 - Evaluate
Run `evaluation/` on `datasets/`: accuracy, false-alert rate, alert latency (Figma KPI), failure analysis from `evidence`.

## Gotchas
- Frame image is BGR (OpenCV); convert to RGB for MediaPipe inside SG-1 only.
- Subject's *left* eye appears on image-right.
- Pin numpy < 2.0 (MediaPipe / JetPack).
- `None` head pose means *unknown*, not 0.
